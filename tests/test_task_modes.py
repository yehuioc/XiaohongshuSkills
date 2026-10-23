import json
from pathlib import Path
from unittest.mock import patch
import unittest
import test_operator
from xhs_operator.engine import Engine
from xhs_operator.store import Store, Problem


class TaskModeTests(unittest.TestCase):
    setUp = test_operator.OperatorTests.setUp
    tearDown = test_operator.OperatorTests.tearDown
    artifact = test_operator.OperatorTests.artifact
    def mode_task(self, mode):
        t = self.engine.create_task({"topic": "帮学生练习讲清课件概念", "source_ids": [self.sid], "mode": mode, "max_sources": 2, "writing_prompt": "用三步和一句具体提示词，不说空话", "reference_copy": "打开课件，选一页。", "style": "swiss"})
        self.engine.run(t["id"], background=False)
        return t["id"]

    def test_text_package_revision_and_restart(self):
        tid = self.mode_task("text")
        packet = self.engine.packet(tid)
        self.assertIn("native_text", packet["schema"]["required"])
        self.assertIn("用三步和一句具体提示词", packet["prompt"])
        self.store.configure({"writing_prompt": "设置后来改变", "style": "editorial"})
        self.assertNotIn("设置后来改变", self.engine.packet(tid)["prompt"])
        raw = self.artifact() | {"cards": [], "native_text": "打开课件，选一个讲不清的概念。让AI先问三个问题，再按课件纠错。"}
        draft = self.engine.complete(tid, raw)
        self.engine.verify_package(draft)
        self.assertEqual(draft["body"]["style"], "swiss")
        self.assertEqual(draft["body"]["rendered"]["pages"], 0)
        directory = self.store.home / draft["body"]["package"]
        self.assertFalse(list((directory / "images").glob("*.png")))
        self.assertEqual((directory / "native-text.txt").read_text(encoding="utf-8"), raw["native_text"])
        revised = self.engine.revise(draft["id"], draft["revision"], raw | {"native_text": "改成另一份具体短文。"})
        self.engine.verify_package(revised)
        self.assertNotEqual(revised["revision"], draft["revision"])
        self.assertEqual(Store(self.temp.name).get("drafts", draft["id"])["body"]["artifact"]["native_text"], "改成另一份具体短文。")
        with patch.object(self.engine, "native_preview", return_value={"ready": True}) as native:
            self.assertTrue(self.engine.extension_preview(draft["id"])["ready"])
            native.assert_called_once_with(draft["id"])

    def test_research_empty_and_opportunity_evidence(self):
        tid = self.mode_task("opportunities")
        self.assertNotIn("cards", self.engine.packet(tid)["schema"]["properties"])
        raw = {"summary": "测试候选，需要核实", "items": [{"source_id": self.sid, "quote": "先确定读者的问题", "need": "测试需求", "published_at": "未注明", "budget": "未注明", "location": "未注明", "skills": "未注明", "uncertainties": "合成测试，不是真实岗位"}], "limitations": "合成测试来源"}
        bad = json.loads(json.dumps(raw)); bad["items"][0]["quote"] = "伪造的招募信息"
        with self.assertRaisesRegex(Problem, "真实原文"):
            self.engine.complete(tid, bad)
        result = self.engine.complete(tid, raw)
        self.assertEqual(result["body"]["research_result"]["items"][0]["url"], "https://example.org/source")
        self.assertEqual(self.store.rows("drafts"), [])
        with self.assertRaises(Problem):
            self.engine.complete(tid, raw)
        tid2 = self.mode_task("research")
        result = self.engine.complete(tid2, {"summary": "没有匹配需求", "items": [], "limitations": "样本有限"})
        self.assertEqual(Store(self.temp.name).get("tasks", tid2)["body"]["research_result"]["items"], [])

    def test_mode_limits_and_cancelled_result(self):
        for value in (0, 31, True, "8"):
            with self.assertRaises(Problem):
                self.engine.create_task({"topic": "边界", "max_sources": value})
        tid = self.mode_task("research")
        self.store.transition(tid, "cancelled")
        with self.assertRaises(Problem):
            self.engine.complete(tid, {"summary": "迟到", "items": []})

    def test_round_source_limit_reaches_collector(self):
        task = self.engine.create_task({"topic": "具体检索", "mode": "research", "max_sources": 1, "keywords": ["具体关键词"]})
        self.store.transition(task["id"], "running")
        note = {"note_id": "a" * 24, "title": "真实需求"}
        raw = {"note_id": note["note_id"], "title": "真实需求", "text": "本测试合成需求，不能当作实际招聘。", "comments": [], "image_data": [], "published_at": "2026-10-23T00:00:00Z"}
        with patch.object(self.engine.bridge, "search", return_value={"cards": [note, {"note_id": "b" * 24}]}), patch.object(self.engine.bridge, "request", side_effect=lambda action, *a, **k: raw if action == "read_note" else {}):
            result = self.engine.bridge.research(task["id"])
        self.assertEqual(len(result["source_ids"]), 1)
        captured = self.store.get("sources", result["source_ids"][0])
        self.assertEqual(captured["body"]["published_at"], "2026-10-23T00:00:00Z")

    def test_actual_provider_prompt_is_preserved(self):
        tid = self.mode_task("text")
        raw = self.artifact() | {"cards": [], "native_text": "实际提示词留存测试。"}
        draft = self.engine.complete(tid, raw, {"driver": "cli", "generation_prompt": "这就是实际执行输入，包括修复内容"})
        self.assertEqual(draft["body"]["generation_prompt"], "这就是实际执行输入，包括修复内容")
        self.assertNotIn("generation_prompt", draft["body"]["producer"])

    def test_native_receipt_validates_account_content_and_preserves_actual_image(self):
        import io
        from PIL import Image
        from xhs_operator.store import encode
        tid = self.mode_task("text")
        raw = self.artifact() | {"cards": [], "native_text": "实际原生文字。"}
        draft = self.engine.complete(tid, raw)
        self.store.configure({"account_id": "a" * 24})
        image = io.BytesIO(); Image.new("RGB", (40, 60), "blue").save(image, format="PNG")
        result = {"ready": True, "title": raw["title"], "body": raw["body"] + "\n\n" + " ".join("#"+t for t in raw["tags"]), "account": {"user_id": "a" * 24}, "image_count": 1, "image_urls": ["https://test.xhscdn.com/generated.png"], "template": "简约"}
        def request(action, args=None, **kwargs):
            return {"user_id": "a" * 24} if action == "identity" else result
        class Opener:
            def open(self, *args, **kwargs): return io.BytesIO(image.getvalue())
        with patch.object(self.engine.bridge, "request", side_effect=request), patch("urllib.request.build_opener", return_value=Opener()):
            receipt = self.engine.native_preview(draft["id"], "简约")
            self.assertTrue(receipt["ready"])
            self.assertEqual(len(receipt["asset_files"]), 1)
            self.assertEqual((self.store.home / receipt["asset_files"][0]["path"]).read_bytes(), image.getvalue())
            self.assertEqual(Engine(Store(self.temp.name)).native_preview_record()["revision"], draft["revision"])
            result["account"] = {"user_id": "b" * 24}
            with self.assertRaisesRegex(Problem, "最终账号"):
                self.engine.native_preview(draft["id"])
            result["account"] = {"user_id": "a" * 24}; result["image_urls"] = ["http://127.0.0.1/private"]
            with self.assertRaisesRegex(Problem, "域名"):
                self.engine.native_preview(draft["id"])

    def test_research_date_uses_collected_field_not_model_invention(self):
        tid = self.mode_task("research")
        raw = {"summary": "核对日期", "items": [{"source_id": self.sid, "quote": "先确定读者的问题", "need": "需求", "published_at": "模型捏造的日期"}], "limitations": "合成测试"}
        result = self.engine.complete(tid, raw)
        self.assertEqual(result["body"]["research_result"]["items"][0]["published_at"], "未注明")

    def test_native_limit_rejects_oversize_without_truncating_the_body(self):
        tid = self.mode_task("text")
        raw = self.artifact() | {"cards": [], "native_text": "字" * 501}
        with self.assertRaises(Problem):
            self.engine.complete(tid, raw)
        raw["native_text"] = "字" * 500
        draft = self.engine.complete(tid, raw)
        self.assertEqual(draft["body"]["artifact"]["body"], raw["body"])
        self.assertEqual(len(draft["body"]["artifact"]["native_text"]), 500)
        self.assertEqual(self.engine.packet(tid)["schema"]["properties"]["native_text"]["maxLength"], 500)
