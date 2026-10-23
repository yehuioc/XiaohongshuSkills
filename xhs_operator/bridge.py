"""Paired extension transport. No browser credentials or arbitrary JavaScript RPC."""
from __future__ import annotations

import base64
import hashlib
import io
import re
import secrets
import threading
import time

from PIL import Image

from .content import normalize_source
from .store import PROJECT, Problem, encode, identifier, now

BROWSER_ACTIONS = {"snapshot", "search", "open_note", "read_note", "close_note", "scroll", "identity", "preview", "preview_status", "native_entry", "open_editor", "creator_inspect", "creator_navigate", "creator_fixture"}


class Bridge:
    def __init__(self, store):
        self.store = store
        self.condition = threading.Condition()
        self.clients = {}
        self.commands = {}
        self.stopped_sessions = set()
        self.pairing = None
        with store.db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS bridge_keys(hash TEXT PRIMARY KEY, origin TEXT NOT NULL, created TEXT NOT NULL)")
            stopped = db.execute("SELECT body FROM control WHERE key='extension_stop_at'").fetchone()
        self.stop_at = float(stopped[0]) if stopped else 0

    def pairing_code(self):
        with self.condition:
            code = secrets.token_hex(5).upper()
            self.pairing = (code, time.monotonic() + 600)
        return {"code": code, "expires_in": 600}

    def pair(self, origin, code):
        if not re.fullmatch(r"chrome-extension://[a-p]{32}", origin or ""):
            raise Problem("仅接受 Chrome 扩展配对")
        with self.condition:
            if not self.pairing or time.monotonic() > self.pairing[1] or not secrets.compare_digest(str(code), self.pairing[0]):
                raise Problem("配对码无效或已过期")
            self.pairing = None
            token = secrets.token_urlsafe(32)
            with self.store.db() as db:
                db.execute("INSERT INTO bridge_keys VALUES(?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), origin, now()))
        return {"token": token}

    def authenticate(self, origin, token):
        key = hashlib.sha256(str(token).encode()).hexdigest()
        with self.store.db() as db:
            row = db.execute("SELECT origin FROM bridge_keys WHERE hash=?", (key,)).fetchone()
        if not row or row[0] != origin:
            raise Problem("扩展未配对或连接已撤销")
        return key

    def revoke(self):
        with self.condition:
            with self.store.db() as db:
                db.execute("DELETE FROM bridge_keys")
            self.clients.clear()
            for command in self.commands.values():
                command["error"] = "连接已撤销"
            self.condition.notify_all()
        return {"revoked": True}

    def status(self):
        with self.condition:
            return [{k: v for k, v in client.items() if k not in ("seen", "auth_key")} | {"online": time.monotonic() - client["seen"] < 10}
                    for client in self.clients.values()]

    def poll(self, key, body):
        binding = body.get("binding")
        if not isinstance(binding, dict) or not re.fullmatch(r"[a-f0-9-]{36}", str(binding.get("session", ""))):
            raise Problem("标签页绑定无效")
        if type(binding.get("tab_id")) is not int or binding["tab_id"] <= 0:
            raise Problem("标签页无效")
        instance = str(binding.get("instance", "legacy"))
        if instance != "legacy" and not re.fullmatch(r"[a-f0-9-]{36}", instance):
            raise Problem("侧栏实例无效")
        client_id = key + ":" + instance
        revision = binding.get("revision", 0)
        if type(revision) is not int or not 0 <= revision <= 9_000_000_000_000_000:
            raise Problem("接管版本无效")
        granted = binding.get("grant_at", 0)
        if type(granted) not in (float, int) or granted > time.time() + 5:
            raise Problem("接管授权时间无效")
        safe = {"session": binding["session"], "tab_id": binding["tab_id"],
                "control": binding.get("control") is True, "url": str(binding.get("url", ""))[:500],
                "title": str(binding.get("title", ""))[:200],
                "account_id": str(binding.get("account_id", ""))[:100], "seen": time.monotonic(),
                "instance": instance, "grant_at": granted, "auth_key": key, "revision": revision,
                "runner": "background" if binding.get("runner") == "background" else "panel",
                "version": str(binding.get("version", "unknown"))[:30],
                "visibility": binding.get("visibility") if binding.get("visibility") in ("selected", "background") else "unknown",
                "window_state": binding.get("window_state") if binding.get("window_state") in ("normal", "minimized", "maximized", "fullscreen") else "unknown",
                "busy": body.get("busy") is True, "message": str(body.get("status", ""))[:300]}
        with self.condition:
            # A stop/rebind can overtake an in-flight heartbeat. Never let that
            # older request restore its previous grant or cancel a newer command.
            previous = self.clients.get(client_id)
            if previous and revision < previous.get("revision", 0):
                return {"stale": True}
            rejected = safe["session"] in self.stopped_sessions or (self.stop_at > 0 and granted <= self.stop_at)
            if rejected:
                safe["control"] = False
            self.clients[client_id] = safe
            for command in self.commands.values():
                if command["client_id"] == client_id and (not safe["control"] or command["session"] != safe["session"]):
                    command["error"] = "用户停止接管或重新绑定标签页"
            self.condition.notify_all()
            executing = body.get("executing")
            if isinstance(executing, dict) and safe["control"]:
                current = self.commands.get(executing.get("id"))
                if (not current or current["client_id"] != client_id or current["session"] != executing.get("session")
                        or current.get("error") or current["expires"] <= time.time()):
                    return {"cancel": executing.get("id")}
            pending = next((c for c in self.commands.values() if c["client_id"] == client_id and c["session"] == safe["session"]
                            and not c.get("sent") and not c.get("error") and c["expires"] > time.time()), None)
            if pending and safe["control"] and not safe["busy"]:
                pending["sent"] = True
                return {k: pending[k] for k in ("id", "action", "args", "session", "expires")}
        return {"stop": True} if rejected and binding.get("control") is True else None

    def stop(self):
        with self.condition:
            self.stop_at = time.time()
            with self.store.db() as db:
                db.execute("INSERT OR REPLACE INTO control VALUES('extension_stop_at',?)", (str(self.stop_at),))
            for client in self.clients.values():
                client["control"] = False
                self.stopped_sessions.add(client["session"])
            for command in self.commands.values():
                command["error"] = "工作台停止接管"
            self.condition.notify_all()
        return {"stopped": True}

    def result(self, key, body):
        with self.condition:
            command = self.commands.get(body.get("id"))
            if not command or command["key"] != key or body.get("session") != command["session"]:
                raise Problem("操作已过期或属于另一标签页")
            if command.get("error") or time.time() > command["expires"]:
                raise Problem("操作已停止或过期，结果未接入")
            command["error"] = str(body["error"])[:1000] if body.get("error") else None
            command["result"] = body.get("result")
            command["done"] = True
            self.condition.notify_all()
        return {"accepted": True}

    def request(self, action, args=None, cancelled=None, timeout=40):
        if action not in BROWSER_ACTIONS:
            raise Problem("该浏览器操作未开放")
        if self.pause():
            raise Problem("扩展在线操作已暂停：" + self.pause()["reason"])
        with self.condition:
            ready = [(key, c) for key, c in self.clients.items() if c["control"] and time.monotonic() - c["seen"] < 10]
            if len(ready) != 1:
                raise Problem("请在一个 Chrome 扩展侧栏绑定标签页并开启 AI 接管；同时只能接管一个连接")
            client_id, client = ready[0]
            command = {"id": identifier(), "key": client["auth_key"], "client_id": client_id, "session": client["session"], "action": action,
                       "args": args or {}, "expires": time.time() + timeout}
            self.commands[command["id"]] = command
            try:
                while not command.get("done") and not command.get("error"):
                    if cancelled and cancelled():
                        raise Problem("任务已停止")
                    if time.time() >= command["expires"]:
                        raise Problem("扩展未在时限内完成操作；未自动重试")
                    self.condition.wait(.25)
                if command.get("error"):
                    raise Problem(command["error"])
                result = command.get("result")
                if isinstance(result, dict) and result.get("blocked"):
                    self.pause(result["blocked"])
                    raise Problem("平台提示：" + result["blocked"])
                return result
            finally:
                self.commands.pop(command["id"], None)

    def pause(self, reason=None):
        with self.store.db() as db:
            if reason is not None:
                db.execute("INSERT OR REPLACE INTO control VALUES('extension_pause',?)", (encode({"reason": str(reason)[:1000], "at": now()}),))
            row = db.execute("SELECT body FROM control WHERE key='extension_pause'").fetchone()
        import json
        return json.loads(row[0]) if row else None

    def resume(self):
        with self.store.db() as db:
            db.execute("DELETE FROM control WHERE key='extension_pause'")
        return {"resumed": True}

    def search(self, keyword, cancelled=None):
        if not isinstance(keyword, str) or not keyword.strip() or len(keyword) > 100:
            raise Problem("关键词无效")
        keyword = keyword.strip()
        current = self.request("snapshot", cancelled=cancelled)
        if current.get("keyword") == keyword and current.get("cards"):
            return current
        try:
            return self.request("search", {"keyword": keyword}, cancelled)
        except Problem as error:
            if not any(value in str(error) for value in ("搜索页未在时限内加载", "网页未返回可读取结果")):
                raise
        # A slow navigation may outlive the panel's initial wait. Observe that same
        # navigation for a bounded period; never navigate or retry the search again.
        for _ in range(10):
            if cancelled and cancelled():
                raise Problem("任务已停止")
            with self.condition:
                self.condition.wait(1)
            current = self.request("snapshot", cancelled=cancelled)
            if current.get("keyword") == keyword and current.get("cards"):
                return current
        raise Problem("搜索页仍未就绪；未再次导航，未读取旧列表")

    def capture(self, raw):
        if not isinstance(raw, dict) or not re.fullmatch(r"[a-f0-9]{24}", str(raw.get("note_id", ""))):
            raise Problem("缺少已核对的笔记 ID")
        if raw.get("blocked"):
            self.pause(raw["blocked"])
            raise Problem("平台提示，已停止采集")
        assets = raw.get("image_data", [])
        if not isinstance(assets, list) or len(assets) > 12:
            raise Problem("每篇最多保存12张研究图片")
        images = []
        for data in assets:
            if not isinstance(data, str) or len(data) > 6_000_000:
                raise Problem("图片过大")
            try:
                payload = base64.b64decode(data, validate=True)
                with Image.open(io.BytesIO(payload)) as img:
                    if img.width * img.height > 30_000_000 or img.format not in ("PNG", "JPEG", "WEBP"):
                        raise Problem("图片格式或尺寸无效")
                    img.verify()
                    ext = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}[img.format]
            except (ValueError, OSError) as error:
                raise Problem("图片无法校验") from error
            path = self.store.home / "sources" / "images" / (hashlib.sha256(payload).hexdigest() + ext)
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_bytes(payload)
            images.append(str(path.relative_to(PROJECT)))
        source = normalize_source(raw | {"url": "https://www.xiaohongshu.com/explore/" + raw["note_id"],
                                        "images": images, "transport": "chrome_extension"})
        source["coverage"] |= {"images_reported": raw.get("images_reported", len(images)),
                               "image_errors": raw.get("image_errors", []), "extraction": raw.get("extraction", {}),
                               "comments_scope": "当前详情中已加载的评论样本，非全量"}
        return {"id": self.store.source(source), "coverage": source["coverage"]}

    def research(self, task_id, deadline=None, stopping=None):
        task = self.store.get("tasks", task_id)
        stopped = lambda: (self.store.get("tasks", task_id)["state"] != "running"
                           or (deadline is not None and time.monotonic() >= deadline)
                           or (stopping is not None and stopping.is_set()))
        ids, failures = [], []
        seen_notes = set()
        maximum = task["body"].get("max_sources", self.store.settings()["max_sources"])
        try:
            for keyword in task["body"]["keywords"] or [None]:
                self.store.event(task_id, "search", "正在搜索：" + (keyword or "当前列表"))
                listing = self.search(keyword, stopped) if keyword else self.request("snapshot", cancelled=stopped)
                for card in listing.get("cards", [])[:maximum]:
                    if len(ids) >= maximum:
                        break
                    if card["note_id"] in seen_notes:
                        continue
                    seen_notes.add(card["note_id"])
                    self.store.event(task_id, "reading", "正在精读：" + card.get("title", card["note_id"]))
                    self.request("open_note", {"note_id": card["note_id"]}, stopped)
                    raw = self.request("read_note", {"note_id": card["note_id"]}, stopped)
                    captured = self.capture(raw)
                    ids.append(captured["id"])
                    # Persist after every note; cancellation never discards successful reading.
                    self.store.transition(task_id, "running", {"source_ids": ids, "collection_failures": failures}, expected=("running",))
                    self.store.event(task_id, "source", "已精读并保存：" + raw.get("title", card["note_id"]))
                    self.request("close_note", {"note_id": card["note_id"]}, stopped)
                if len(ids) >= maximum:
                    break
        except Problem as error:
            failures.append(str(error))
        if not ids:
            raise Problem(failures[0] if failures else "当前列表没有可精读的笔记")
        return {"source_ids": ids, "collection_failures": failures}
