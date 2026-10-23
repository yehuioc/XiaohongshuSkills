"""小红书工作台的本地命令入口。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from xhs_operator.content import import_combined, normalize_source
from xhs_operator.engine import Engine
from xhs_operator.store import PROJECT, DEFAULT_HOME, Problem, Store
from xhs_operator.web import serve

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def read_json(value):
    path = Path(value).resolve()
    if not path.is_relative_to(PROJECT) or not path.is_file() or path.stat().st_size > 2_000_000:
        raise Problem("JSON 输入必须是本项目内的有界文件")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main():
    ap = argparse.ArgumentParser(description="扩展连接、模型中立的小红书创作工作台")
    ap.add_argument("--home", help="本项目内的数据目录")
    sub = ap.add_subparsers(dest="command", required=True)
    start = sub.add_parser("serve")
    start.add_argument("--port", type=int, default=8914)
    mcp = sub.add_parser("mcp")
    mcp.add_argument("--port", type=int, default=8914)
    sub.add_parser("status")
    sub.add_parser("doctor")
    config = sub.add_parser("configure")
    config.add_argument("--input", required=True)
    source = sub.add_parser("source")
    source.add_argument("--input", required=True)
    legacy = sub.add_parser("import")
    legacy.add_argument("path")
    task = sub.add_parser("task")
    task.add_argument("--topic", required=True)
    task.add_argument("--mode", choices=("cards", "text", "research", "opportunities"), default="cards")
    task.add_argument("--max-sources", type=int)
    task.add_argument("--sources", nargs="*", default=[])
    task.add_argument("--keywords", nargs="*")
    for command in ("run", "packet", "cancel", "preview"):
        command_ap = sub.add_parser(command)
        command_ap.add_argument("id")
    complete = sub.add_parser("complete")
    complete.add_argument("id")
    complete.add_argument("--input", required=True)
    for command in ("approve", "publish"):
        command_ap = sub.add_parser(command)
        command_ap.add_argument("id")
        command_ap.add_argument("--revision", required=True)
        command_ap.add_argument("--confirm", required=True)
    for command in ("identity", "login", "feedback"):
        sub.add_parser(command)
    args = ap.parse_args()
    if args.command == "mcp":
        from xhs_operator.mcp import serve_stdio
        home = Path(args.home).resolve() if args.home else DEFAULT_HOME
        if not home.is_relative_to(PROJECT):
            raise Problem("MCP 数据目录必须位于本项目内")
        return serve_stdio(home, args.port)
    store = Store(args.home) if args.home else Store()
    engine = Engine(store)
    if args.command == "serve":
        return serve(store, args.port)
    if args.command == "status":
        result = engine.status()
    elif args.command == "doctor":
        from xhs_operator.runner import auth_status
        from xhs_operator.content import font_path
        import PIL
        result = {"subscription": auth_status(), "chinese_font": font_path(), "pillow": PIL.__version__, "data_home": str(store.home), "browser": store.settings()["browser"], "platform_login": store.platform_pause() or "本次尚未检查平台；运行 identity 检查"}
    elif args.command == "configure":
        result = store.configure(read_json(args.input))
    elif args.command == "source":
        result = {"id": store.source(normalize_source(read_json(args.input)))}
    elif args.command == "import":
        result = import_combined(store, args.path)
    elif args.command == "task":
        raw = {"topic": args.topic, "source_ids": args.sources, "mode": args.mode}
        if args.max_sources is not None:
            raw["max_sources"] = args.max_sources
        if args.keywords is not None:
            raw["keywords"] = args.keywords
        result = engine.create_task(raw)
    elif args.command == "run":
        result = engine.run(args.id, background=False)
    elif args.command == "packet":
        result = engine.packet(args.id)
    elif args.command == "cancel":
        result = store.transition(args.id, "cancelled")
    elif args.command == "complete":
        result = engine.complete(args.id, read_json(args.input))
    elif args.command == "approve":
        if args.confirm != "我已审阅完整图文":
            raise Problem("请明确确认已审阅本篇完整图文")
        result = store.approval(args.id, args.revision) or {"approved": True}
    elif args.command == "publish":
        result = engine.publish(args.id, args.revision, args.confirm)
    else:
        result = engine.platform_action(args.command, **({"draft_id": args.id} if args.command == "preview" else {}))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Problem as error:
        raise SystemExit(str(error))
