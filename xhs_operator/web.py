from __future__ import annotations

import io
import json
import secrets
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from .content import import_combined, normalize_source
from .engine import Engine
from .store import PROJECT, Problem, Store
from .service import dispatch

STATIC = PROJECT / "xhs_operator" / "static"


def make_server(store, port=8914):
    engine, csrf = Engine(store), secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def same_origin(self):
            expected = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            if self.headers.get("Host") not in expected:
                raise Problem("拒绝未知 Host")
            origin = self.headers.get("Origin")
            if origin and origin not in {"http://" + x for x in expected}:
                raise Problem("拒绝跨站请求")

        def send(self, data, mime="application/json; charset=utf-8", code=200, extra=None):
            if not isinstance(data, bytes):
                data = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(data)

        def read_body(self, maximum=2_000_000):
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                raise Problem("仅接受 JSON 请求")
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= maximum:
                raise Problem("请求过大或为空")
            return json.loads(self.rfile.read(length))

        def bridge_origin(self):
            import re
            host = self.headers.get("Host")
            if host != f"127.0.0.1:{self.server.server_port}":
                raise Problem("拒绝未知 Host")
            origin = self.headers.get("Origin", "")
            if not re.fullmatch(r"chrome-extension://[a-p]{32}", origin):
                raise Problem("拒绝非扩展来源")
            return origin

        def do_OPTIONS(self):
            try:
                origin = self.bridge_origin()
                if not urlsplit(self.path).path.startswith("/bridge/"):
                    raise Problem("不开放跨站接口")
                return self.send({}, extra={"Access-Control-Allow-Origin": origin,
                    "Access-Control-Allow-Methods": "POST, OPTIONS", "Access-Control-Allow-Headers": "Content-Type, Authorization", "Vary": "Origin"})
            except Problem as error:
                self.send({"error": str(error)}, code=403)

        def do_GET(self):
            try:
                self.same_origin()
                path = urlsplit(self.path).path
                if path == "/api/state":
                    return self.send(engine.status() | {"csrf": csrf})
                if path.startswith("/api/packet/"):
                    return self.send(engine.packet(path.rsplit("/", 1)[1]))
                if path.startswith("/api/download/"):
                    draft = store.get("drafts", path.rsplit("/", 1)[1])
                    engine.verify_package(draft)
                    directory = store.home / draft["body"]["package"]
                    output = io.BytesIO()
                    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
                        for name in draft["body"]["rendered"]["files"]:
                            file = directory / name
                            archive.write(file, name)
                    return self.send(output.getvalue(), "application/zip", extra={"Content-Disposition": f'attachment; filename="xhs-{draft["id"][:8]}.zip"'})
                if path.startswith("/files/"):
                    parts = path.split("/")
                    if len(parts) < 5:
                        raise Problem("图片路径无效")
                    draft = store.get("drafts", parts[2])
                    if parts[3] != draft["revision"]:
                        raise Problem("稿件版本改变")
                    directory = (store.home / draft["body"]["package"]).resolve()
                    file = directory.joinpath(*parts[4:]).resolve()
                    name = "/".join(parts[4:])
                    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(file.suffix.lower())
                    if not file.is_relative_to(directory) or not file.is_file() or not mime or name not in draft["body"]["rendered"]["files"]:
                        raise Problem("图片不存在")
                    return self.send(file.read_bytes(), mime)
                if path.startswith("/native-preview-image/"):
                    import hashlib
                    parts = path.split("/")
                    if len(parts) != 5:
                        raise Problem("原生图片路径无效")
                    record = engine.native_preview_record()
                    if not record or record["draft_id"] != parts[2] or record["revision"] != parts[3]:
                        raise Problem("原生预览已改变")
                    draft = store.get("drafts", parts[2])
                    if draft["revision"] != parts[3]:
                        raise Problem("稿件已改变，原生预览不是当前版本")
                    index = int(parts[4])
                    if not 0 <= index < len(record["asset_files"]):
                        raise Problem("原生图片不存在")
                    entry = record["asset_files"][index]
                    file = (store.home / entry["path"]).resolve()
                    if not file.is_relative_to(store.home) or not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != entry["sha256"]:
                        raise Problem("原生图片文件改变或越界")
                    return self.send(file.read_bytes(), "image/png" if file.suffix == ".png" else "image/webp" if file.suffix == ".webp" else "image/jpeg")
                if path.startswith("/source-image/"):
                    parts = path.split("/")
                    if len(parts) != 4:
                        raise Problem("来源图片路径无效")
                    source = store.get("sources", parts[2])
                    index = int(parts[3])
                    if not 0 <= index < len(source["body"]["images"]):
                        raise Problem("来源图片不存在")
                    file = (PROJECT / source["body"]["images"][index]).resolve()
                    if not file.is_relative_to(PROJECT):
                        raise Problem("来源图片路径越界")
                    mime = "image/png" if file.suffix == ".png" else "image/webp" if file.suffix == ".webp" else "image/jpeg"
                    return self.send(file.read_bytes(), mime)
                if path == "/api/extension.zip":
                    output = io.BytesIO()
                    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
                        for file in (PROJECT / "extension").glob("*"):
                            if file.is_file():
                                archive.write(file, file.name)
                    return self.send(output.getvalue(), "application/zip", extra={"Content-Disposition": 'attachment; filename="xhs-research-extension.zip"'})
                name = {"/": "index.html", "/app.js": "app.js", "/app.css": "app.css"}.get(path)
                if name:
                    mime = {"html": "text/html", "js": "text/javascript", "css": "text/css"}[name.split(".")[-1]]
                    return self.send((STATIC / name).read_bytes(), mime + "; charset=utf-8")
                self.send({"error": "入口不存在"}, code=404)
            except (Problem, ValueError, KeyError, OSError) as error:
                self.send({"error": str(error)}, code=400)

        def do_POST(self):
            try:
                path = urlsplit(self.path).path
                if path.startswith("/bridge/"):
                    origin = self.bridge_origin()
                    extra = {"Access-Control-Allow-Origin": origin, "Vary": "Origin"}
                    try:
                        body = self.read_body(32_000_000)
                        if path == "/bridge/pair":
                            result = engine.bridge.pair(origin, body.get("code"))
                        else:
                            key = engine.bridge.authenticate(origin, self.headers.get("Authorization", "").removeprefix("Bearer "))
                            if path == "/bridge/poll":
                                result = engine.bridge.poll(key, body)
                            elif path == "/bridge/result":
                                result = engine.bridge.result(key, body)
                            elif path == "/bridge/capture":
                                result = engine.bridge.capture(body)
                            elif path == "/bridge/pause":
                                result = engine.bridge.pause(body.get("reason", "平台限制"))
                            else:
                                raise Problem("桥接入口不存在")
                        return self.send({"result": result}, extra=extra)
                    except (Problem, ValueError, KeyError, OSError) as error:
                        return self.send({"error": str(error)}, code=400, extra=extra)
                self.same_origin()
                if path == "/api/v1":
                    token_path = store.home / "api-token.txt"
                    supplied = self.headers.get("Authorization", "").removeprefix("Bearer ")
                    if not token_path.is_file() or not secrets.compare_digest(token_path.read_text(encoding="utf-8"), supplied):
                        return self.send({"error": "本机 API 凭据无效，请在工作台生成连接凭据"}, code=401)
                    body = self.read_body()
                    return self.send({"result": dispatch(engine, body.get("action"), body.get("args", {}), external=True)})
                if path != "/api/action":
                    return self.send({"error": "入口不存在"}, code=404)
                if self.headers.get("X-XHS-Token") != csrf:
                    raise Problem("请求凭据失效，请刷新页面")
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise Problem("仅接受 JSON 请求")
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 2_000_000:
                    raise Problem("请求过大或为空")
                request = json.loads(self.rfile.read(length))
                action, args = request.get("action"), request.get("args", {})
                if not isinstance(args, dict):
                    raise Problem("参数格式无效")
                result = dispatch(engine, action, args)
                self.send({"result": result})
            except (Problem, ValueError, KeyError, OSError) as error:
                self.send({"error": str(error)}, code=400)
            except Exception:
                self.send({"error": "操作失败，未将本轮计为完成；请检查终端或任务事件"}, code=500)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.engine = engine
    return server


def serve(store=None, port=8914):
    store = store or Store()
    server = make_server(store, port)
    # The bound port is the single server ownership point. Recover only after bind succeeds.
    store.recover()
    stopped = threading.Event()

    def scheduler():
        while not stopped.wait(30):
            try:
                server.engine.schedule_tick()
            except Exception as error:
                store.event(None, "scheduler_error", str(error)[:1000])

    threading.Thread(target=scheduler, daemon=True).start()
    print(f"小红书创作工作台 http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    finally:
        stopped.set()
        server.engine.close()
        server.server_close()
