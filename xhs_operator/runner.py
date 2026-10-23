from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time

from .store import PROJECT, Problem

NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
ACTIVE_PROCESSES = {}


def active_processes():
    return {task_id: {"pid": process.pid, "alive": process.poll() is None} for task_id, process in list(ACTIVE_PROCESSES.items())}


def codex_binary():
    found = shutil.which("codex")
    if not found:
        raise Problem("找不到 Codex CLI，请先安装或将桌面版 CLI 加入 PATH")
    return found


def subscription_environment():
    env = os.environ.copy()
    for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN", "OPENAI_BASE_URL", "OPENAI_FEDERATION_RULE_ID", "OPENAI_IDENTITY_TOKEN_FILE", "OPENAI_WORKLOAD_IDENTITY_CONTEXT"):
        env.pop(key, None)
    env["PYTHONUTF8"] = "1"
    return env


def auth_status():
    try:
        result = subprocess.run([codex_binary(), "login", "status"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15, env=subscription_environment(), creationflags=NO_WINDOW)
        text = result.stdout + result.stderr
        okay = result.returncode == 0 and "chatgpt" in text.lower() and "api key" not in text.lower()
        return {"available": True, "subscription_ready": okay,
                "message": "Codex CLI 已使用 ChatGPT 登录" if okay else "本执行环境未确认订阅登录；请在启动工作台的宿主终端核对 codex login status，或使用当前 Codex 聊天"}
    except (Problem, OSError, subprocess.TimeoutExpired):
        return {"available": False, "subscription_ready": False, "message": "CLI 不可用；可在当前 Codex 聊天中执行任务"}


class SubscriptionLogin:
    """User-initiated official device login. Credentials stay in Codex's own store."""
    def __init__(self):
        self.process = None
        self.code = None
        self.started = None
        self.lock = threading.Lock()

    def start(self):
        with self.lock:
            if self.process and self.process.poll() is None:
                return self.status()
            self.code = None
            self.started = time.monotonic()
            self.process = subprocess.Popen([codex_binary(), "login", "--device-auth"], stdout=subprocess.PIPE,
                                            stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                            env=subscription_environment(), creationflags=NO_WINDOW)
            process = self.process
            def read():
                for raw in iter(process.stdout.readline, b""):
                    text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", raw.decode("utf-8", "replace"))
                    match = re.search(r"\b[A-Z0-9]{4,6}-[A-Z0-9]{4,6}\b", text)
                    if match and process is self.process:
                        self.code = match[0]
                process.stdout.close()
            threading.Thread(target=read, daemon=True).start()
            return self.status()

    def status(self):
        if not self.process:
            return {"state": "idle"}
        code = self.process.poll()
        if code is not None:
            return {"state": "completed" if code == 0 else "expired", "message": "登录结束，请检查 CLI 订阅状态" if code == 0 else "本次登录未完成或已过期；可由你主动重新发起"}
        if time.monotonic() - self.started > 960:
            self.process.kill()
            return {"state": "expired", "message": "本次设备登录超时"}
        return {"state": "waiting", "code": self.code, "url": "https://auth.openai.com/codex/device", "message": "在 OpenAI 官方页面完成登录确认；验证码约15分钟有效。"}

    def close(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()




def run_codex(store, task_id, prompt, schema, images, stop_event=None, deadline=None, attempt=None):
    if not auth_status()["subscription_ready"]:
        raise Problem("SUBSCRIPTION_LOGIN_REQUIRED")
    task_dir = store.home / "tasks" / task_id
    if attempt is not None:
        task_dir = task_dir / f"attempt-{attempt:02d}"
    task_dir.mkdir(parents=True, exist_ok=True)
    schema_file, output = task_dir / "schema.json", task_dir / "result.json"
    schema_file.write_text(json.dumps(schema, ensure_ascii=False), encoding="utf-8")
    if output.exists():
        output.unlink()
    settings = store.settings()
    args = [codex_binary(), "exec", "--ignore-user-config", "--ephemeral", "--json", "--sandbox", "read-only",
            "-c", 'forced_login_method="chatgpt"', "-c", 'model_provider="openai_http"',
            "-c", 'model_providers.openai_http.name="OpenAI"',
            "-c", 'model_providers.openai_http.wire_api="responses"',
            "-c", "model_providers.openai_http.requires_openai_auth=true",
            "-c", "model_providers.openai_http.supports_websockets=false",
            "-c", "model_providers.openai_http.request_max_retries=1",
            "-c", "model_providers.openai_http.stream_max_retries=1",
            "-c", "project_doc_max_bytes=0", "-c", 'web_search="disabled"',
            "--output-schema", str(schema_file), "-o", str(output), "-C", str(PROJECT)]
    # Content generation receives all evidence and image inputs. It needs no executable tools.
    for feature in ("shell_tool", "unified_exec", "code_mode", "code_mode_host", "apps", "plugins", "hooks", "multi_agent_v2", "browser_use", "computer_use", "view_image", "image_generation"):
        args += ["--disable", feature]
    if settings["model"]:
        args += ["--model", settings["model"]]
    for path in images[:12]:
        args += ["--image", path]
    args += ["-"]
    process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=subscription_environment(), creationflags=NO_WINDOW)
    ACTIVE_PROCESSES[task_id] = process
    try:
        store.transition(task_id, "running", {"worker_pid": process.pid, "phase": "codex_generation"})
        store.event(task_id, "codex_started", "Codex 订阅任务已启动，正在生成完整图文")
    except BaseException:
        process.kill()
        process.wait(timeout=10)
        ACTIVE_PROCESSES.pop(task_id, None)
        raise
    events, errors, complete, usage, failed = [], [], False, None, False
    lines = queue.Queue()

    def consume(stream, kind):
        for raw in iter(stream.readline, b""):
            lines.put((kind, raw.decode("utf-8", "replace")))
        stream.close()
        lines.put((kind, None))

    for kind, stream in (("event", process.stdout), ("stderr", process.stderr)):
        threading.Thread(target=consume, args=(stream, kind), daemon=True).start()
    def send_input():
        try:
            process.stdin.write(prompt.encode("utf-8"))
        except (OSError, BrokenPipeError) as error:
            lines.put(("stderr", "任务输入未完成：" + str(error)))
        finally:
            try:
                process.stdin.close()
            except OSError:
                pass
    input_thread = threading.Thread(target=send_input, daemon=True)
    input_thread.start()
    deadline = min(deadline or float("inf"), time.monotonic() + settings["max_seconds"])
    streams = 2
    try:
        event_log = (task_dir / "events.jsonl").open("w", encoding="utf-8")
        diagnostic_log = (task_dir / "stderr.log").open("w", encoding="utf-8")
    except BaseException:
        process.kill()
        process.wait(timeout=10)
        ACTIVE_PROCESSES.pop(task_id, None)
        raise
    try:
        while streams or process.poll() is None or not lines.empty():
            if stop_event and stop_event.is_set():
                raise Problem("工作台正在停止，本轮中断")
            if store.get("tasks", task_id)["state"] == "cancelled":
                raise Problem("任务已取消")
            if time.monotonic() >= deadline:
                raise Problem("Codex 本轮达到时间上限，结果未计为完成")
            try:
                kind, text = lines.get(timeout=0.2)
            except queue.Empty:
                continue
            if text is None:
                streams -= 1
                continue
            if kind == "stderr":
                diagnostic_log.write(text)
                diagnostic_log.flush()
                errors.append(text[-2000:])
                errors = errors[-15:]
                continue
            try:
                event = json.loads(text)
            except json.JSONDecodeError:
                continue
            events.append(event)
            event_log.write(json.dumps(event, ensure_ascii=False) + "\n")
            event_log.flush()
            if len(events) > 2000:
                raise Problem("Codex 事件超出本轮上限")
            if event.get("type") == "turn.completed":
                complete, usage = True, event.get("usage")
            if event.get("type") in ("error", "turn.failed"):
                failed = True
                errors.append(json.dumps(event, ensure_ascii=False))
        if process.returncode != 0 or failed or not complete or not output.is_file():
            raise Problem("Codex 未完成：" + "\n".join(errors)[-2000:])
        artifact = json.loads(output.read_text(encoding="utf-8"))
        return artifact, {"driver": "codex_cli", "auth": "chatgpt", "usage": usage, "images_attached": len(images[:12])}
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)
        ACTIVE_PROCESSES.pop(task_id, None)
        input_thread.join(timeout=1)
        event_log.close()
        diagnostic_log.close()
        (task_dir / "events.json").write_text(json.dumps(events, ensure_ascii=False), encoding="utf-8")
