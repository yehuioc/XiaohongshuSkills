"""One business interface shared by the workbench, local API and MCP."""
from __future__ import annotations

import secrets

from .content import import_combined, normalize_source
from .store import PROJECT, Problem

EXTERNAL_ACTIONS = {"status", "list", "get", "source_image", "source", "create_task", "run", "cancel", "attach_sources", "packet", "complete", "revise", "browser", "preview", "feedback"}


def dispatch(engine, action, args=None, external=False):
    args = args or {}
    if not isinstance(args, dict):
        raise Problem("参数必须是 JSON 对象")
    if external and action not in EXTERNAL_ACTIONS:
        raise Problem("外部 AI 接口不开放设置、批准、正式发布、配对或权限修改")
    store = engine.store
    if action == "status":
        if external:
            return {"connections": engine.bridge.status(), "pause": engine.bridge.pause(), "provider": store.settings()["driver"], "browser": store.settings()["browser"]}
        return engine.status()
    if action == "list":
        return store.rows(args["table"], min(100, max(1, int(args.get("limit", 30)))))
    if action == "get":
        return store.get(args["table"], args["id"])
    if action == "packet":
        return engine.packet(args["id"])
    if action == "source_image":
        import base64
        source = store.get("sources", args["id"])
        index = args.get("index")
        if type(index) is not int or not 1 <= index <= len(source["body"]["images"]):
            raise Problem("来源图片页码无效（从1开始）")
        path = (PROJECT / source["body"]["images"][index-1]).resolve()
        if not path.is_relative_to(PROJECT) or not path.is_file() or path.stat().st_size > 6_000_000:
            raise Problem("来源图片不可读取")
        mime = {".webp": "image/webp", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(path.suffix.lower())
        if not mime:
            raise Problem("不支持的来源图片格式")
        return {"type": "image", "mimeType": mime, "data": base64.b64encode(path.read_bytes()).decode()}
    if action == "native_entry":
        return engine.native_preview(args["draft_id"], args.get("template", ""), args.get("resume_images"), args.get("resume_writing"))
    if action == "settings":
        return store.configure(args)
    if action == "pairing_code":
        return engine.bridge.pairing_code()
    if action == "revoke_extension":
        return engine.bridge.revoke()
    if action == "stop_browser":
        return engine.bridge.stop()
    if action == "api_token":
        token = secrets.token_urlsafe(32)
        (store.home / "api-token.txt").write_text(token, encoding="utf-8")
        return {"token": token, "message": "仅本机 AI 接口；旋转后旧凭据立即失效"}
    if action == "browser":
        operation = args.get("operation")
        if operation == "creator_fixture":
            from .creator_fixture import fixture_args
            payload = fixture_args(args.get("fixture")) | {"phase": args.get("phase", "upload")}
            with engine.browser_lock:
                return engine.bridge.request("creator_fixture", payload, timeout=70)
        if operation not in {"snapshot", "search", "open_note", "read_note", "close_note", "scroll", "identity", "preview_status", "creator_inspect", "creator_navigate"}:
            raise Problem("浏览器只开放研究、预览检查与受限创作者导航；不开放提交或任意点击")
        with engine.browser_lock:
            result = engine.bridge.search(args.get("keyword")) if operation == "search" else engine.bridge.request(operation, {k: v for k, v in args.items() if k != "operation"})
            if operation == "read_note":
                saved = engine.bridge.capture(result)
                return {"source_id": saved["id"], "coverage": saved["coverage"], "source": store.get("sources", saved["id"])}
            return result
    if action == "subscription_login":
        engine.auth_cache = None
        return engine.subscription_login.start()
    if action == "resume_platform":
        if args.get("confirmation") != "我已处理平台限制，允许再次检查":
            raise Problem("恢复在线操作需要明确确认平台条件已经处理")
        if store.settings()["browser"] == "extension":
            return engine.bridge.resume()
        store.resume_platform()
        return {"resumed": True}
    if action == "source":
        return {"id": store.source(normalize_source(args))}
    if action == "import":
        return import_combined(store, PROJECT / args["path"])
    if action == "create_task":
        return engine.create_task(args)
    if action == "run":
        return engine.run(args["id"])
    if action == "cancel":
        return store.transition(args["id"], "cancelled", expected=("queued", "running", "waiting_auth", "awaiting_codex", "waiting_browser", "failed", "interrupted"))
    if action == "attach_sources":
        return engine.attach_sources(args["id"], args["source_ids"])
    if action == "complete":
        return engine.complete(args["id"], args["artifact"], {"driver": "external_client"} if external else None)
    if action == "revise":
        return engine.revise(args["id"], args["revision"], args["artifact"])
    if action == "approve":
        store.approval(args["id"], args["revision"])
        return {"approved": True}
    if action == "publish":
        return engine.publish(args["id"], args["revision"], args.get("confirmation"))
    if action == "link_publication":
        return engine.link_publication(args["id"], args["url"])
    if action in ("identity", "login", "feedback", "preview"):
        return engine.platform_action(action, **args)
    raise Problem("未知操作")
