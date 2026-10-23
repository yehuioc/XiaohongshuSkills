from __future__ import annotations

import contextlib
import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_HOME = PROJECT / "data" / "operator"


def now():
    return datetime.now(timezone.utc).isoformat()


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def identifier():
    return uuid.uuid4().hex


class Problem(ValueError):
    pass


class Store:
    def __init__(self, home=DEFAULT_HOME):
        self.home = Path(home).resolve()
        if not self.home.is_relative_to(PROJECT):
            raise Problem("运行数据必须位于本项目内")
        self.home.mkdir(parents=True, exist_ok=True)
        self.path = self.home / "operator.sqlite"
        with self.db() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS control(key TEXT PRIMARY KEY, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY, fingerprint TEXT UNIQUE,
                body TEXT NOT NULL, created TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, state TEXT NOT NULL,
                body TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS drafts(id TEXT PRIMARY KEY, task_id TEXT UNIQUE,
                state TEXT NOT NULL, body TEXT NOT NULL, revision TEXT NOT NULL,
                approved_revision TEXT, created TEXT NOT NULL, updated TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS publications(id TEXT PRIMARY KEY, draft_id TEXT NOT NULL,
                revision TEXT NOT NULL, state TEXT NOT NULL, body TEXT NOT NULL,
                created TEXT NOT NULL, UNIQUE(draft_id, revision));
            CREATE TABLE IF NOT EXISTS feedback(id TEXT PRIMARY KEY, body TEXT NOT NULL, created TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, task_id TEXT,
                kind TEXT NOT NULL, message TEXT NOT NULL, created TEXT NOT NULL);
            """)
            defaults = {
                "account_name": "", "account_id": "", "audience": "", "mission": "",
                "voice": "具体、自然、有依据；不编造亲身经历。", "keywords": [],
                "driver": "desktop", "model": "", "style": "editorial",
                "writing_prompt": "先用具体场景说明读者卡在哪里，再给可直接照做的步骤、输入示例和判断结果的方法。用自然口语，删去空泛口号、内部调研过程和自我免责声明。不要写这批资料、编辑提出、赋能、重塑、底层逻辑等套话。不编造亲历或效果。重要限制放在对应主张旁，研究缺口放依据面板。", "reference_copy": "",
                "browser": "extension", "max_sources": 8, "max_seconds": 600,
                "api_base_url": "", "api_key_env": "XHS_MODEL_API_KEY",
                "schedule_enabled": False, "schedule_time": "09:00",
            }
            for key, value in defaults.items():
                db.execute("INSERT OR IGNORE INTO settings VALUES(?,?)", (key, encode(value)))

    @contextlib.contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def settings(self):
        with self.db() as db:
            return {r["key"]: json.loads(r["body"]) for r in db.execute("SELECT * FROM settings")}

    def platform_pause(self, reason=None):
        with self.db() as db:
            if reason is not None:
                db.execute("INSERT OR REPLACE INTO control VALUES('platform_pause',?)", (encode({"reason": reason, "at": now()}),))
            row = db.execute("SELECT body FROM control WHERE key='platform_pause'").fetchone()
            return json.loads(row[0]) if row else None

    def resume_platform(self):
        with self.db() as db:
            db.execute("DELETE FROM control WHERE key='platform_pause'")

    def configure(self, patch):
        current = self.settings()
        if set(patch) - set(current):
            raise Problem("存在未知配置项")
        value = current | patch
        if value["driver"] not in ("desktop", "cli", "api") or value["style"] not in ("editorial", "swiss"):
            raise Problem("执行方式或视觉风格无效")
        if value["browser"] not in ("extension", "cdp", "iab"):
            raise Problem("浏览器方式无效")
        if not isinstance(value["keywords"], list) or not all(isinstance(x, str) and 0 < len(x) <= 100 for x in value["keywords"]) or len(value["keywords"]) > 10:
            raise Problem("最多设置 10 个关注关键词")
        for k, upper in (("max_sources", 30), ("max_seconds", 3600)):
            if type(value[k]) is not int or not 1 <= value[k] <= upper:
                raise Problem(f"{k} 超出允许范围")
        import re
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value["schedule_time"]):
            raise Problem("定时时间格式为 HH:MM（北京时间）")
        if type(value["schedule_enabled"]) is not bool:
            raise Problem("定时开关无效")
        for k in ("account_name", "account_id", "audience", "mission", "voice", "writing_prompt", "reference_copy", "model", "api_base_url", "api_key_env"):
            if not isinstance(value[k], str) or len(value[k]) > 5000:
                raise Problem(f"{k} 过长或类型错误")
        with self.db() as db:
            for key, item in patch.items():
                db.execute("UPDATE settings SET body=? WHERE key=?", (encode(item), key))
        return value

    def event(self, task_id, kind, message):
        with self.db() as db:
            db.execute("INSERT INTO events(task_id,kind,message,created) VALUES(?,?,?,?)", (task_id, kind, message, now()))

    def rows(self, table, limit=100):
        if table not in {"sources", "tasks", "drafts", "publications", "feedback", "events"}:
            raise Problem("未知数据类型")
        with self.db() as db:
            rows = db.execute(f"SELECT * FROM {table} ORDER BY {'id' if table == 'events' else 'created'} DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) | ({"body": json.loads(r["body"])} if "body" in r.keys() else {}) for r in rows]

    def get(self, table, item_id):
        if table not in {"sources", "tasks", "drafts", "publications"}:
            raise Problem("未知数据类型")
        with self.db() as db:
            r = db.execute(f"SELECT * FROM {table} WHERE id=?", (item_id,)).fetchone()
        if not r:
            raise Problem("记录不存在")
        return dict(r) | {"body": json.loads(r["body"])}

    def source(self, body):
        fingerprint = digest({k: body.get(k) for k in ("url", "text", "comments", "observed_at")})
        with self.db() as db:
            old = db.execute("SELECT id FROM sources WHERE fingerprint=?", (fingerprint,)).fetchone()
            if old:
                return old[0]
            item_id = identifier()
            db.execute("INSERT INTO sources VALUES(?,?,?,?)", (item_id, fingerprint, encode(body), now()))
            return item_id

    def create_task(self, body):
        item_id, timestamp = identifier(), now()
        with self.db() as db:
            db.execute("INSERT INTO tasks VALUES(?,?,?,?,?)", (item_id, "queued", encode(body), timestamp, timestamp))
        self.event(item_id, "queued", "任务已加入队列")
        return self.get("tasks", item_id)

    def transition(self, item_id, state, patch=None, expected=None):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM tasks WHERE id=?", (item_id,)).fetchone()
            if not row:
                raise Problem("任务不存在")
            if expected and row["state"] not in expected:
                raise Problem("任务状态已改变，请刷新后重试")
            if row["state"] == "cancelled" and state != "cancelled":
                raise Problem("任务已取消")
            if state == "running":
                busy = db.execute("SELECT id FROM tasks WHERE state='running' AND id<>?", (item_id,)).fetchone()
                if busy:
                    raise Problem("另一个任务正在运行")
            body = json.loads(row["body"]) | (patch or {})
            db.execute("UPDATE tasks SET state=?,body=?,updated=? WHERE id=?", (state, encode(body), now(), item_id))
        return self.get("tasks", item_id)

    def recover(self):
        import os
        with self.db() as db:
            for row in db.execute("SELECT * FROM tasks WHERE state='running'").fetchall():
                pid = json.loads(row["body"]).get("owner_pid")
                alive = False
                if type(pid) is int and pid > 0:
                    try:
                        os.kill(pid, 0)
                        alive = True
                    except ProcessLookupError:
                        pass
                    except PermissionError:
                        alive = True
                if not alive:
                    db.execute("UPDATE tasks SET state='interrupted',updated=? WHERE id=?", (now(), row["id"]))
            db.execute("UPDATE publications SET state='unknown' WHERE state='sending'")

    def approval(self, draft_id, revision):
        with self.db() as db:
            row = db.execute("SELECT revision,state FROM drafts WHERE id=?", (draft_id,)).fetchone()
            if not row or row[0] != revision or row[1] not in ("awaiting_review", "approved"):
                raise Problem("稿件已改变或不可批准，请重新审阅")
            db.execute("UPDATE drafts SET state='approved',approved_revision=?,updated=? WHERE id=?", (revision, now(), draft_id))

    def reserve_publication(self, draft_id, revision):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            draft = db.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone()
            if not draft or draft["state"] != "approved" or draft["revision"] != revision or draft["approved_revision"] != revision:
                raise Problem("必须先批准当前版本的完整图文")
            existing = db.execute("SELECT state FROM publications WHERE draft_id=? AND revision=?", (draft_id, revision)).fetchone()
            if existing:
                raise Problem("该版本已有发布记录；结果不明时禁止重复发送")
            if db.execute("SELECT 1 FROM publications WHERE state IN ('sending','unknown','submitted')").fetchone():
                raise Problem("存在尚未核实的发布，请先核对结果")
            item_id = identifier()
            db.execute("INSERT INTO publications VALUES(?,?,?,?,?,?)", (item_id, draft_id, revision, "sending", "{}", now()))
        return item_id
