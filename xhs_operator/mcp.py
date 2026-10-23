"""Dependency-free MCP stdio adapter to the running, authenticated local API."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

from .store import DEFAULT_HOME, Problem
from . import __version__


TOOLS = [
    ("xhs_feedback", "通过已接管扩展读取笔记管理列表、审核标签和指标快照；拒绝离开有内容的编辑器，不发布；返回实际覆盖范围", "feedback", {}),
    ("xhs_status", "读取本机连接与运行状态", "status", {}),
    ("xhs_list", "列出素材、任务、稿件或反馈", "list", {"table": {"type": "string", "enum": ["sources", "tasks", "drafts", "feedback", "publications"]}}),
    ("xhs_get", "读取完整素材、任务或稿件", "get", {"table": {"type": "string", "enum": ["sources", "tasks", "drafts"]}, "id": {"type": "string"}}),
    ("xhs_browser", "操作用户已允许接管的标签页。creator_inspect 检查页面，creator_navigate 固定导航；creator_fixture 仅上传项目自制测试素材、填写明确标记的测试稿和存草稿，须用户授权测试；绝不提交发布、接受协议或任意脚本", "browser", {"operation": {"type": "string", "enum": ["snapshot", "search", "open_note", "read_note", "close_note", "scroll", "identity", "creator_inspect", "creator_navigate", "creator_fixture"]}}),
    ("xhs_create_task", "创建研究与图文生产任务", "create_task", {"topic": {"type": "string"}}),
    ("xhs_run", "启动或继续本地生产任务", "run", {"id": {"type": "string"}}),
    ("xhs_cancel", "停止生产任务", "cancel", {"id": {"type": "string"}}),
    ("xhs_packet", "获取任务资料、图片映射和完整输出 schema", "packet", {"id": {"type": "string"}}),
    ("xhs_source_image", "读取实际来源图片供视觉模型核对（index 从1开始）", "source_image", {"id": {"type": "string"}, "index": {"type": "integer", "minimum": 1}}),
    ("xhs_complete", "将客户端按任务 schema 生成的完整图文接回待审稿", "complete", {"id": {"type": "string"}, "artifact": {"type": "object"}}),
    ("xhs_preview", "把稿件填写到用户已打开的创作者图文编辑器，绝不点击发布", "preview", {"draft_id": {"type": "string"}}),
]
OPTIONAL = {
    "xhs_browser": {"note_id": {"type": "string"}, "keyword": {"type": "string"}, "draft_id": {"type": "string"}, "fixture": {"enum": ["image", "video", "audio", "longform"]}, "phase": {"enum": ["upload", "resume", "fill", "save", "layout", "next", "cover", "visibility", "visibility_self", "visibility_public", "declaration", "declaration_ai", "declaration_clear", "collection", "preview_cover", "dismiss", "chapters", "video_cover", "close_modal", "cover_crop", "cover_templates", "cover_stickers", "cover_text", "cover_filters"]}, "direction": {"enum": ["up", "down"]}, "index": {"type": "integer", "minimum": 0, "maximum": 30}, "target": {"type": "string", "enum": ["notes", "publish_entry", "video", "images", "longform", "podcast", "drafts", "all", "published", "reviewing", "rejected", "draft_video", "draft_images", "draft_longform", "draft_podcast", "draft_close", "modal_close", "new_longform", "import_link", "rss", "back", "note_search", "note_action_hint", "note_permissions", "resume_test", "toolbar_hint"]}},
    "xhs_create_task": {"mode": {"enum": ["cards", "text", "research", "opportunities"]}, "max_sources": {"type": "integer", "minimum": 1, "maximum": 30}, "style": {"enum": ["editorial", "swiss"]}, "writing_prompt": {"type": "string"}, "reference_copy": {"type": "string"}, "source_ids": {"type": "array", "items": {"type": "string"}}, "keywords": {"type": "array", "items": {"type": "string"}}},
}


def call_api(action, args, home=DEFAULT_HOME, port=8914):
    token_path = home / "api-token.txt"
    if not token_path.is_file():
        raise Problem("请先在工作台的浏览器连接页生成本机 AI 接口凭据")
    request = urllib.request.Request(f"http://127.0.0.1:{port}/api/v1", data=json.dumps({"action": action, "args": args}, ensure_ascii=False).encode(),
                                     headers={"Content-Type": "application/json", "Authorization": "Bearer " + token_path.read_text(encoding="utf-8")})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=240 if action == "feedback" else 150 if action == "preview" else 80) as response:
            return json.load(response)["result"]
    except urllib.error.HTTPError as error:
        raise Problem(json.load(error).get("error", "本地接口拒绝请求")) from error
    except urllib.error.URLError as error:
        raise Problem("本地工作台未连接，请先启动 serve") from error


def response(message, home=DEFAULT_HOME, port=8914):
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}
    if "id" not in message:
        return None
    base = {"jsonrpc": "2.0", "id": message["id"]}
    method = message.get("method")
    if method == "initialize":
        version = message.get("params", {}).get("protocolVersion")
        return base | {"result": {"protocolVersion": version if version in ("2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25") else "2025-11-25",
                                  "capabilities": {"tools": {}}, "serverInfo": {"name": "xhs-research-workbench", "version": __version__}}}
    if method == "ping":
        return base | {"result": {}}
    if method == "tools/list":
        return base | {"result": {"tools": [{"name": name, "description": description,
                  "inputSchema": {"type": "object", "properties": properties | OPTIONAL.get(name, {}), "required": list(properties), "additionalProperties": False}}
                  for name, description, action, properties in TOOLS]}}
    if method == "tools/call":
        try:
            params = message.get("params", {})
            tool = next((t for t in TOOLS if t[0] == params.get("name")), None)
            if not tool:
                raise Problem("未知工具")
            result = call_api(tool[2], params.get("arguments", {}), home, port)
            content = [result] if tool[2] == "source_image" else [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]
            return base | {"result": {"content": content, "isError": False}}
        except (Problem, KeyError, TypeError, ValueError) as error:
            return base | {"result": {"content": [{"type": "text", "text": str(error)}], "isError": True}}
    return base | {"error": {"code": -32601, "message": "Method not found"}}


def serve_stdio(home=DEFAULT_HOME, port=8914):
    for line in sys.stdin:
        try:
            if len(line) > 2_000_000:
                raise ValueError("request too large")
            result = response(json.loads(line), home, port)
        except (ValueError, TypeError):
            result = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        if result is not None:
            print(json.dumps(result, ensure_ascii=False), flush=True)
