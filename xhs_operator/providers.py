"""Content providers are independent of browser actions and publication authority."""
from __future__ import annotations

import base64
import json
import os
import re
import time
from urllib.parse import urlsplit

import requests

from .runner import run_codex
from .store import Problem


def run_provider(store, task_id, prompt, schema, images, stopping, deadline, attempt):
    settings = store.settings()
    driver = store.get("tasks", task_id)["body"].get("driver", settings["driver"])
    if driver == "cli":
        return run_codex(store, task_id, prompt, schema, images, stopping, deadline, attempt)
    if driver != "api":
        raise Problem("未选择可自动运行的内容提供器")
    url = settings["api_base_url"].rstrip("/")
    parsed = urlsplit(url)
    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost")):
        raise Problem("API 地址必须是 HTTPS 或本机 HTTP")
    if parsed.username or parsed.password or parsed.query or parsed.fragment or not settings["model"]:
        raise Problem("API 地址不能带凭据/参数，且必须指定模型")
    env_name = settings["api_key_env"]
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,99}", env_name):
        raise Problem("API 密钥环境变量名称无效")
    key = os.environ.get(env_name, "")
    if not key:
        raise Problem("工作台进程缺少指定 API 环境变量；不会改用其他密钥或订阅")
    if stopping.is_set() or store.get("tasks", task_id)["state"] != "running" or time.monotonic() >= deadline:
        raise Problem("任务已停止或到期")
    content = [{"type": "text", "text": prompt}]
    from pathlib import Path
    for name in images:
        path = Path(name)
        mime = {".webp": "image/webp", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(path.suffix.lower())
        if not mime:
            raise Problem("不支持的模型图片输入格式")
        content.append({"type": "image_url", "image_url": {"url": "data:" + mime + ";base64," + base64.b64encode(path.read_bytes()).decode()}})
    store.event(task_id, "provider", "调用用户配置的兼容 API；本轮资料与附图发送到指定提供商")
    # One bounded request, no automatic provider fallback or HTTP retries. Cancelling
    # prevents accepting a late result; an already submitted provider request may bill.
    session = requests.Session()
    session.trust_env = False
    with session:
        response = session.post(url + "/chat/completions", headers={"Authorization": "Bearer " + key},
                                json={"model": settings["model"], "messages": [{"role": "user", "content": content}],
                                      "response_format": {"type": "json_schema", "json_schema": {"name": "xhs_post", "strict": True, "schema": schema}}},
                                timeout=(10, max(1, min(180, deadline - time.monotonic()))), allow_redirects=False)
    if response.status_code != 200:
        raise Problem(f"配置的 API 返回 HTTP {response.status_code}；未自动切换提供商")
    if stopping.is_set() or store.get("tasks", task_id)["state"] != "running" or time.monotonic() >= deadline:
        raise Problem("任务已停止或到期，未接入迟到的 API 结果")
    if len(response.content) > 2_000_000:
        raise Problem("API 结果过大")
    result = response.json()
    try:
        artifact = json.loads(result["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise Problem("API 未返回完整 JSON 图文，未将本轮记为完成") from error
    return artifact, {"driver": "compatible_api", "endpoint": url, "model": settings["model"], "usage": result.get("usage"), "attempt": attempt, "images_attached": len(images)}
