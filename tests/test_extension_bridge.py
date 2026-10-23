import base64
import concurrent.futures
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from xhs_operator.bridge import Bridge
from xhs_operator.mcp import response
from xhs_operator.providers import run_provider
from xhs_operator.service import dispatch
from xhs_operator.store import PROJECT, Problem, Store
from xhs_operator.web import make_server


class ExtensionBoundaryTests(unittest.TestCase):
    def setUp(self):
        parent = PROJECT / "data" / "operator-tests"
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.store = Store(self.temp.name)
        self.server = make_server(self.store, 0)
        self.server.engine.auth_cache = (time.monotonic(), {"subscription_ready": False})
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = "chrome-extension://" + "a" * 32

    def tearDown(self):
        self.server.engine.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        self.temp.cleanup()

    def http(self, path, data=None, headers=None):
        request = urllib.request.Request(f"http://127.0.0.1:{self.server.server_port}" + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers={"Content-Type": "application/json"} | (headers or {}))
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=5) as r:
            return json.load(r)

    def pair(self):
        code = self.server.engine.bridge.pairing_code()["code"]
        token = self.http("/bridge/pair", {"code": code}, {"Origin": self.origin})["result"]["token"]
        return {"Origin": self.origin, "Authorization": "Bearer " + token}

    def test_pair_origin_one_use_csrf_and_external_publication_denial(self):
        code = self.server.engine.bridge.pairing_code()["code"]
        with self.assertRaises(urllib.error.HTTPError):
            self.http("/bridge/pair", {"code": code}, {"Origin": "https://evil.invalid"})
        headers = self.pair()
        with self.assertRaises(urllib.error.HTTPError):
            self.http("/bridge/pair", {"code": code}, {"Origin": self.origin})
        with self.assertRaises(urllib.error.HTTPError):
            self.http("/api/action", {"action": "settings", "args": {"browser": "cdp"}})
        token = dispatch(self.server.engine, "api_token")["token"]
        for action in ("approve", "publish", "settings", "api_token", "pairing_code", "resume_platform"):
            with self.assertRaises(urllib.error.HTTPError):
                self.http("/api/v1", {"action": action}, {"Authorization": "Bearer " + token})
        self.assertEqual(self.http("/api/v1", {"action": "status"}, {"Authorization": "Bearer " + token})["result"]["browser"], "extension")
        dispatch(self.server.engine, "api_token")
        with self.assertRaises(urllib.error.HTTPError) as denied:
            self.http("/api/v1", {"action": "status"}, {"Authorization": "Bearer " + token})
        self.assertEqual(denied.exception.code, 401)
        self.server.engine.bridge.revoke()
        with self.assertRaises(urllib.error.HTTPError):
            self.http("/bridge/poll", {}, headers)

    def test_stop_invalidates_sent_command_and_cannot_be_reasserted(self):
        headers = self.pair()
        binding = {"tab_id": 123, "session": str(uuid.uuid4()), "control": True, "account_id": "test", "url": "https://www.xiaohongshu.com/explore"}
        self.http("/bridge/poll", {"binding": binding}, headers)
        bridge = self.server.engine.bridge
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(bridge.request, "snapshot", {}, None, 3)
            for _ in range(50):
                if bridge.commands:
                    break
                time.sleep(.01)
            command = self.http("/bridge/poll", {"binding": binding}, headers)["result"]
            self.assertEqual(command["action"], "snapshot")
            bridge.stop()
            with self.assertRaises(Problem):
                future.result(2)
            self.assertTrue(self.http("/bridge/poll", {"binding": binding}, headers)["result"]["stop"])
            with self.assertRaises(urllib.error.HTTPError):
                self.http("/bridge/result", {"id": command["id"], "session": binding["session"], "result": {"cards": []}}, headers)
        with self.assertRaises(Problem):
            bridge.request("snapshot", timeout=.05)
        with self.assertRaises(Problem):
            bridge.request("evaluate", {"script": "anything"})

    def test_background_busy_heartbeats_cancel_and_out_of_order_stop(self):
        headers = self.pair()
        binding = {"tab_id": 123, "instance": str(uuid.uuid4()), "session": str(uuid.uuid4()),
                   "control": True, "grant_at": time.time(), "revision": 5, "runner": "background", "visibility": "background"}
        self.http("/bridge/poll", {"binding": binding}, headers)
        bridge = self.server.engine.bridge
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(bridge.request, "snapshot", {}, None, 4)
            for _ in range(100):
                if bridge.commands:
                    break
                time.sleep(.01)
            self.assertIsNone(self.http("/bridge/poll", {"binding": binding, "busy": True}, headers)["result"])
            command = self.http("/bridge/poll", {"binding": binding}, headers)["result"]
            running = {"id": command["id"], "session": command["session"]}
            self.assertIsNone(self.http("/bridge/poll", {"binding": binding, "busy": True, "executing": running}, headers)["result"])
            self.assertTrue(bridge.status()[0]["online"])
            self.assertEqual(bridge.status()[0]["runner"], "background")
            self.assertEqual(bridge.status()[0]["visibility"], "background")
            stopped = binding | {"control": False, "session": str(uuid.uuid4()), "revision": 6, "grant_at": 0}
            self.http("/bridge/poll", {"binding": stopped}, headers)
            self.assertTrue(self.http("/bridge/poll", {"binding": binding}, headers)["result"]["stale"])
            self.assertFalse(bridge.status()[0]["control"])
            with self.assertRaises(Problem):
                future.result(2)
        fresh = binding | {"session": str(uuid.uuid4()), "revision": 7}
        result = self.http("/bridge/poll", {"binding": fresh, "busy": True, "executing": running}, headers)["result"]
        self.assertEqual(result, {"cancel": command["id"]})

    def test_old_panels_cannot_restore_control_after_stop_and_instances_do_not_cancel_each_other(self):
        headers = self.pair()
        bridge = self.server.engine.bridge
        a = {"tab_id": 123, "instance": str(uuid.uuid4()), "session": str(uuid.uuid4()), "control": True, "grant_at": time.time()-1}
        b = a | {"tab_id": 456, "instance": str(uuid.uuid4()), "session": str(uuid.uuid4())}
        self.http("/bridge/poll", {"binding": a}, headers)
        self.http("/bridge/poll", {"binding": b}, headers)
        with self.assertRaises(Problem):
            bridge.request("snapshot")
        bridge.stop()
        for old in (a, b, b | {"session": str(uuid.uuid4())}):
            self.assertTrue(self.http("/bridge/poll", {"binding": old}, headers)["result"]["stop"])
        self.assertTrue(all(not c["control"] for c in bridge.status()))
        restarted = Bridge(self.store)
        self.assertGreater(restarted.stop_at, 0)
        key = restarted.authenticate(self.origin, headers["Authorization"].removeprefix("Bearer "))
        self.assertTrue(restarted.poll(key, {"binding": a})["stop"])
        a |= {"session": str(uuid.uuid4()), "grant_at": time.time()+.01}
        self.http("/bridge/poll", {"binding": a}, headers)
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(bridge.request, "snapshot", {}, None, 3)
            for _ in range(50):
                if bridge.commands:
                    break
                time.sleep(.01)
            self.assertIsNone(self.http("/bridge/poll", {"binding": b | {"control": False}}, headers)["result"])
            self.assertFalse(future.done())
            command = self.http("/bridge/poll", {"binding": a}, headers)["result"]
            self.http("/bridge/result", {"id": command["id"], "session": a["session"], "result": {"cards": []}}, headers)
            self.assertEqual(future.result(2), {"cards": []})

    def test_command_round_trip_rebind_and_pause_persistence(self):
        headers = self.pair()
        bridge = self.server.engine.bridge
        binding = {"tab_id": 123, "session": str(uuid.uuid4()), "control": True}
        self.http("/bridge/poll", {"binding": binding}, headers)
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(bridge.request, "identity", {}, None, 3)
            for _ in range(50):
                command = self.http("/bridge/poll", {"binding": binding}, headers)["result"]
                if command:
                    break
                time.sleep(.01)
            self.http("/bridge/result", {"id": command["id"], "session": binding["session"], "result": {"user_id": "real-id"}}, headers)
            self.assertEqual(future.result(2), {"user_id": "real-id"})
            future = pool.submit(bridge.request, "snapshot", {}, None, 3)
            time.sleep(.05)
            binding["session"] = str(uuid.uuid4())
            self.http("/bridge/poll", {"binding": binding}, headers)
            with self.assertRaises(Problem):
                future.result(2)
        self.http("/bridge/pause", {"reason": "300012"}, headers)
        self.assertEqual(Bridge(self.store).pause()["reason"], "300012")
        with self.assertRaises(Problem):
            bridge.request("snapshot")
        bridge.resume()
        self.assertIsNone(bridge.pause())

    def test_capture_preserves_images_and_reports_partial_coverage(self):
        headers = self.pair()
        data = io.BytesIO()
        Image.new("RGB", (20, 30), "white").save(data, format="PNG")
        raw = {"note_id": "a" * 24, "title": "测试详情", "text": "这是实际详情读取协议的合成测试，不是真实在线调研。", "comments": ["评论样本"],
               "image_data": [base64.b64encode(data.getvalue()).decode()], "images_reported": 3, "image_errors": ["下载失败两张"]}
        result = self.http("/bridge/capture", raw, headers)["result"]
        source = self.store.get("sources", result["id"])["body"]
        self.assertEqual(source["coverage"]["images_reported"], 3)
        self.assertEqual(source["coverage"]["images_available"], 1)
        self.assertTrue((PROJECT / source["images"][0]).is_file())
        self.assertFalse(source["coverage"]["images_read"])
        image = dispatch(self.server.engine, "source_image", {"id": result["id"], "index": 1}, external=True)
        self.assertEqual(image["mimeType"], "image/png")
        self.assertEqual(source["url"], "https://www.xiaohongshu.com/explore/" + "a" * 24)
        raw["comments"] = []
        raw["text"] = ""
        image_only = self.http("/bridge/capture", raw, headers)["result"]
        self.assertFalse(image_only["coverage"]["text"])
        self.assertEqual(image_only["coverage"]["images_available"], 1)
        raw["image_data"] = [base64.b64encode(b"not an image").decode()]
        with self.assertRaises(urllib.error.HTTPError):
            self.http("/bridge/capture", raw, headers)

    def test_mcp_real_stdio_uses_existing_service_and_never_exposes_approval(self):
        dispatch(self.server.engine, "api_token")
        messages = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}},
                    {"jsonrpc": "2.0", "method": "notifications/initialized"},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                    {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "xhs_status"}}]
        result = subprocess.run([sys.executable, "-X", "utf8", "-B", "run_xhs.py", "--home", str(self.store.home), "mcp", "--port", str(self.server.server_port)],
                                cwd=PROJECT, input="\n".join(json.dumps(m) for m in messages) + "\n", text=True, capture_output=True, encoding="utf-8", timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        replies = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(replies), 3)
        names = [t["name"] for t in replies[1]["result"]["tools"]]
        self.assertNotIn("xhs_publish", names)
        self.assertNotIn("xhs_approve", names)
        self.assertFalse(replies[2]["result"]["isError"])
        self.assertEqual(json.loads(replies[2]["result"]["content"][0]["text"])["browser"], "extension")

    def test_api_provider_is_explicit_and_cannot_fall_back(self):
        task = self.store.create_task({"topic": "合成测试"})
        self.store.transition(task["id"], "running")
        self.store.configure({"driver": "api", "api_base_url": "https://example.invalid/v1", "model": "requested-model"})
        with patch.dict(os.environ, {}, clear=True), patch("requests.Session.post") as post:
            with self.assertRaises(Problem):
                run_provider(self.store, task["id"], "prompt", {}, [], threading.Event(), time.monotonic()+5, 1)
            post.assert_not_called()
        class Reply:
            status_code = 200
            content = b'{}'
            def json(self):
                return {"choices": [{"message": {"content": '{"test":"ok"}'}}], "usage": {"total_tokens": 2}}
        with patch.dict(os.environ, {"XHS_MODEL_API_KEY": "test-key"}, clear=True), patch("requests.Session.post", return_value=Reply()) as post:
            value, producer = run_provider(self.store, task["id"], "prompt", {}, [], threading.Event(), time.monotonic()+5, 1)
            self.assertEqual(value, {"test": "ok"})
            self.assertEqual(producer["model"], "requested-model")
            self.assertEqual(post.call_args.kwargs["json"]["model"], "requested-model")
            self.assertFalse(post.call_args.kwargs["allow_redirects"])

    def test_search_observes_one_slow_navigation_without_navigating_again(self):
        bridge = self.server.engine.bridge
        with patch.object(bridge, "request", side_effect=[{"cards": [], "keyword": ""}, Problem("搜索页未在时限内加载"), {"cards": [{"note_id": "a" * 24}], "keyword": "排版"}]) as request:
            result = bridge.search("排版")
        self.assertEqual(result["keyword"], "排版")
        self.assertEqual([call.args[0] for call in request.call_args_list], ["snapshot", "search", "snapshot"])

    def test_matching_preview_is_verified_without_uploading_again(self):
        engine = self.server.engine
        self.store.configure({"account_id": "account-one"})
        artifact = {"title": "待核对稿件", "body": "完整正文", "tags": ["标签"], "cards": [{}, {}, {}]}
        draft = {"id": "draft", "revision": "revision", "body": {"artifact": artifact, "package": "unused"}}
        status = {"title": artifact["title"], "body": "完整正文\n\n#标签", "image_count": 3, "uploading": False,
                  "upload_failed": False, "account": {"user_id": "account-one"}}
        with patch.object(self.store, "get", return_value=draft), patch.object(engine, "verify_package"), patch.object(engine.bridge, "request", side_effect=[{"user_id": "account-one"}, status]) as request:
            result = engine.extension_preview("draft")
        self.assertTrue(result["ready"])
        self.assertFalse(result["published"])
        self.assertEqual([call.args[0] for call in request.call_args_list], ["identity", "preview_status"])
        with self.store.db() as db:
            self.assertIsNotNone(db.execute("SELECT body FROM control WHERE key='last_extension_preview'").fetchone())
        for changed in (status | {"title": "别人的稿件"}, status | {"body": "另一个正文"}, status | {"image_count": 4}, status | {"account": {"user_id": "different"}}):
            with self.assertRaises(Problem):
                engine.preview_ready(draft, changed)
        self.assertFalse(engine.preview_ready(draft, status | {"image_count": 2}))


if __name__ == "__main__":
    unittest.main()
