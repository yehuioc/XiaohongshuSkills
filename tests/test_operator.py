import concurrent.futures
import hashlib
import json
import os
import tempfile
import subprocess
import sys
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from xhs_operator.content import normalize_source, balanced_heading, font_path, validate_artifact, cover_heading
from xhs_operator.engine import Engine
from xhs_operator.runner import subscription_environment, run_codex
from xhs_operator.store import PROJECT, Problem, Store
from xhs_operator.web import make_server


class OperatorTests(unittest.TestCase):
    def setUp(self):
        root = PROJECT / "data" / "operator-tests"
        root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=root)
        self.store = Store(self.temp.name)
        self.engine = Engine(self.store)
        self.sid = self.store.source(normalize_source({"title": "研究原文", "url": "https://example.org/source", "text": "先确定读者的问题，再选择能够支持判断的材料。不能把空正文当成已经精读。", "author": "合成测试来源", "observed_at": "2026-10-22"}))

    def tearDown(self):
        self.temp.cleanup()

    def task(self):
        task = self.engine.create_task({"topic": "从读者问题开始做内容", "source_ids": [self.sid]})
        self.engine.run(task["id"], background=False)
        self.assertEqual(self.store.get("tasks", task["id"])["state"], "awaiting_codex")
        return task["id"]

    def artifact(self):
        return {"title": "先想清楚为谁写", "body": "写一篇内容前，可以先记下读者真正遇到的问题。例如，对方已经有了素材，却不知道怎样整理成一篇图文。这时先说明场景，再给出可操作的方法，比堆积工具名称更容易理解。找到原文后，也要区分已经读到的内容和仍然缺失的部分。最后再核对图片与正文是否表达同一个判断。", "tags": ["内容创作", "图文笔记"], "cards": [
            {"title": "先想清楚\n为谁写", "eyebrow": "写作札记", "points": ["从一个具体的读者问题开始。", "再让材料、正文与图片共同回答它。"]},
            {"title": "问题先于工具", "eyebrow": "方法", "points": ["写下读者已经知道什么，又卡在哪里。", "找能支持判断的原始材料，缺失的部分如实保留。"]},
            {"title": "发布前，读一遍", "eyebrow": "检查", "points": ["只看图片，方法是否仍然清楚？", "回到原文，主张是否有依据？"]}],
            "evidence": [{"source_id": self.sid, "quote": "先确定读者的问题", "claim": "先明确读者问题再组织材料"}], "insights": ["本样例用于验证完整图文链路，不证明传播效果。"], "limitations": "合成来源，仅用于离线接口验收。"}

    def draft(self):
        return self.engine.complete(self.task(), self.artifact())

    def test_real_package_and_restart(self):
        draft = self.draft()
        self.engine.verify_package(draft)
        self.assertEqual(draft["state"], "awaiting_review")
        self.assertEqual(draft["body"]["rendered"]["pages"], 3)
        reopened = Store(self.temp.name)
        self.assertEqual(reopened.get("drafts", draft["id"])["revision"], draft["revision"])

    def test_cover_avoids_orphan_character_and_keeps_explicit_breaks(self):
        from PIL import ImageFont
        font = ImageFont.truetype(font_path(True), 118)
        lines = balanced_heading("它说能做，证据呢", font.getlength, 910)
        self.assertEqual("".join(lines), "它说能做，证据呢")
        self.assertTrue(all(len(line) >= 3 and font.getlength(line) <= 910 for line in lines))
        self.assertEqual(balanced_heading("先想清楚\n为谁写", font.getlength, 910), ["先想清楚", "为谁写"])
        heading, size = cover_heading('复杂主题，写成能做的步骤', lambda text,size: ImageFont.truetype(font_path(True),size).getlength(text))
        self.assertEqual(heading, '复杂主题，\n写成能做的步骤')
        self.assertGreaterEqual(size, 106)
        for title in ("研究来源与证据：先核对，再表达", "Codex 帮你整理素材", "一张卡片，回答一个问题"):
            wrapped = balanced_heading(title, font.getlength, 910)
            self.assertEqual("".join(wrapped).replace(" ", ""), title.replace(" ", ""))
            self.assertTrue(all(font.getlength(line) <= 910 and line[0] not in "，。！？：；" for line in wrapped))

    def test_reject_fabricated_quote_and_out_of_scope_source(self):
        tid = self.task()
        artifact = self.artifact()
        artifact["evidence"][0]["quote"] = "原文并没有说过的统计数据"
        with self.assertRaises(Problem):
            self.engine.complete(tid, artifact)
        self.assertEqual(len(self.store.rows("drafts")), 0)
        artifact = self.artifact()
        artifact["evidence"][0]["source_id"] = "other-task-source"
        with self.assertRaises(Problem):
            self.engine.complete(tid, artifact)

    def test_empty_sources_and_missing_graphics_do_not_pass(self):
        with self.assertRaises(Problem):
            normalize_source({"title": "只有标题", "url": "https://example.org", "text": ""})
        artifact = self.artifact()
        artifact["cards"] = []
        with self.assertRaises(Problem):
            self.engine.complete(self.task(), artifact)

    def test_image_evidence_preserves_original_without_claiming_text_match(self):
        from PIL import Image
        image = Path(self.temp.name) / 'source.png'
        Image.new('RGB', (64, 64), '#cc2222').save(image)
        source = self.store.get('sources', self.sid)
        source['body']['images'] = [str(image.relative_to(PROJECT))] * 13
        source['body']['observed_at'] = '2026-10-22T01:00:00Z'
        self.sid = self.store.source(source['body'])
        artifact = self.artifact()
        artifact['evidence'] = [{'source_id':self.sid,'quote':'合成图片中的红色底色','claim':'测试图片证据与文字匹配分开标记','medium':'image','image_index':1}]
        draft = self.engine.complete(self.task(), artifact)
        entry = draft['body']['artifact']['evidence'][0]
        self.assertEqual(entry['verification'], 'image_requires_review')
        directory = self.store.home / draft['body']['package']
        preserved = directory / 'evidence' / (self.sid+'-01.png')
        self.assertEqual(preserved.read_bytes(), image.read_bytes())
        self.engine.verify_package(draft)
        artifact['evidence'][0]['image_index'] = 13
        with self.assertRaisesRegex(Problem, '实际附件范围'):
            validate_artifact(artifact, [self.store.get('sources', self.sid)])
        preserved.write_bytes(b'changed')
        with self.assertRaises(Problem):
            self.engine.verify_package(draft)

    def test_feedback_is_in_next_task_packet_without_becoming_account_preferences(self):
        earlier = self.draft()
        feedback = {'account':{'user_id':'fixture'},'observed_at':'2026-07-03','coverage':'历史测试样本','rows':[{'标题':'观察样本','观看量':120}]}
        with self.store.db() as db:
            db.execute('INSERT INTO feedback VALUES(?,?,?)',('fixture-feedback',json.dumps(feedback),'2026-07-03'))
        tid = self.task()
        prompt = self.engine.packet(tid)['prompt']
        self.assertIn('历史测试样本', prompt)
        self.assertIn('观看量', prompt)
        self.assertIn(earlier['id'], prompt)
        self.assertIn(earlier['body']['artifact']['insights'][0], prompt)
        self.assertEqual(self.store.settings()['mission'], '')

    def test_cancel_cannot_be_completed(self):
        tid = self.task()
        self.store.transition(tid, "cancelled")
        with self.assertRaises(Problem):
            self.engine.complete(tid, self.artifact())

    def test_approval_revision_and_single_send_reservation(self):
        draft = self.draft()
        with self.assertRaises(Problem):
            self.store.reserve_publication(draft["id"], draft["revision"])
        self.store.approval(draft["id"], draft["revision"])
        def reserve():
            try:
                return self.store.reserve_publication(draft["id"], draft["revision"])
            except Problem:
                return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            values = list(executor.map(lambda _: reserve(), range(2)))
        self.assertEqual(sum(x is not None for x in values), 1)
        self.store.recover()
        self.assertEqual(self.store.rows("publications")[0]["state"], "unknown")
        with self.assertRaises(Problem):
            reserve_id = self.store.reserve_publication(draft["id"], draft["revision"])

    def test_edit_revokes_approval_and_stale_approval_fails(self):
        draft = self.draft()
        self.store.approval(draft["id"], draft["revision"])
        artifact = self.artifact()
        artifact["body"] += "每次改稿后，重新核对整篇内容。"
        revised = self.engine.revise(draft["id"], draft["revision"], artifact)
        self.assertIsNone(revised["approved_revision"])
        self.assertEqual(revised["state"], "awaiting_review")
        with self.assertRaises(Problem):
            self.store.approval(draft["id"], draft["revision"])

    def test_tampered_png_and_missing_file_block_publication(self):
        draft = self.draft()
        image = self.store.home / draft["body"]["package"] / "images/01.png"
        image.write_bytes(image.read_bytes() + b"tamper")
        with self.assertRaises(Problem):
            self.engine.verify_package(draft)
        image.unlink()
        with self.assertRaises(Problem):
            self.engine.verify_package(draft)

    def test_recovery_and_real_worker_mutex(self):
        first = self.engine.create_task({"topic": "第一轮", "source_ids": [self.sid]})
        second = self.engine.create_task({"topic": "第二轮", "source_ids": [self.sid]})
        self.store.transition(first["id"], "running")
        with self.assertRaises(Problem):
            self.store.transition(second["id"], "running")
        self.store.recover()
        self.assertEqual(self.store.get("tasks", first["id"])["state"], "interrupted")

    def test_no_api_key_or_federation_fallback(self):
        with patch.dict(os.environ, {"CODEX_API_KEY": "test-secret", "OPENAI_API_KEY": "other", "OPENAI_FEDERATION_RULE_ID": "x", "CODEX_ACCESS_TOKEN": "y"}):
            env = subscription_environment()
            self.assertNotIn("CODEX_API_KEY", env)
            self.assertNotIn("OPENAI_API_KEY", env)
            self.assertNotIn("OPENAI_FEDERATION_RULE_ID", env)
            self.assertNotIn("CODEX_ACCESS_TOKEN", env)

    def test_cli_terminal_event_not_exit_code_proves_completion(self):
        tid = self.task()
        real_popen = subprocess.Popen
        failure = [False]

        def launch(args, **kwargs):
            self.assertIn('forced_login_method="chatgpt"', args)
            self.assertIn('--ignore-user-config', args)
            self.assertIn('shell_tool', args)
            path = args[args.index('-o') + 1]
            code = ("import sys,json;from pathlib import Path;sys.stdin.read();"
                    "Path(sys.argv[1]).write_text(json.dumps({'fixture':'transport-only'}));"
                    "print(json.dumps({'type':'turn.completed','usage':{'input_tokens':10,'output_tokens':5}}),flush=True);")
            if failure[0]:
                code += "print(json.dumps({'type':'turn.failed','error':'fixture failure'}),flush=True);"
            return real_popen([sys.executable, '-u', '-c', code, path], **kwargs)

        with patch('xhs_operator.runner.auth_status', return_value={'subscription_ready':True}), patch('xhs_operator.runner.codex_binary', return_value='codex'), patch('xhs_operator.runner.subprocess.Popen', side_effect=launch):
            result, receipt = run_codex(self.store, tid, 'synthetic transport fixture', {}, [])
            self.assertEqual(result['fixture'], 'transport-only')
            self.assertEqual(receipt['usage']['input_tokens'], 10)
            failure[0] = True
            with self.assertRaises(Problem):
                run_codex(self.store, tid, 'synthetic failed turn', {}, [])

    def test_platform_pause_and_unapproved_publish_never_open_browser(self):
        from xhs_operator.platform import Platform
        self.store.platform_pause('fixture platform restriction')
        with patch.object(Platform, 'acquire') as acquire:
            with self.assertRaises(Problem):
                with Platform(self.store):
                    pass
            acquire.assert_not_called()
        draft = self.draft()
        with patch.object(Platform, '__enter__') as enter:
            with self.assertRaises(Problem):
                self.engine.publish(draft['id'], draft['revision'], '发布这篇已审阅图文')
            enter.assert_not_called()

    def test_cli_repairs_invalid_content_once_within_same_task(self):
        self.store.configure({'driver':'cli'})
        task = self.engine.create_task({'topic':'修复测试','source_ids':[self.sid]})
        bad = self.artifact();bad['evidence'][0]['quote']='这句话不在来源中'
        receipt = {'driver':'codex_cli','auth':'chatgpt','usage':{'input_tokens':100,'output_tokens':50}}
        with patch('xhs_operator.engine.auth_status',return_value={'subscription_ready':True}),patch('xhs_operator.engine.run_codex',side_effect=[(bad,receipt),(self.artifact(),receipt)]) as runner:
            draft = self.engine.run(task['id'],background=False)
            self.assertEqual(draft['state'],'awaiting_review')
            self.assertEqual(runner.call_count,2)
            self.assertIn('未在来源中找到',runner.call_args_list[1].args[2])
            self.assertEqual(len(draft['body']['producer']['attempts']),2)

    def test_publication_readback_matches_account_id_and_title(self):
        self.store.configure({'account_id':'a'*24})
        draft = self.draft()
        self.store.approval(draft['id'], draft['revision'])
        pid = self.store.reserve_publication(draft['id'], draft['revision'])
        with self.store.db() as db:
            db.execute("UPDATE publications SET state='submitted',body=? WHERE id=?", (json.dumps({'url':'https://www.xiaohongshu.com/explore/'+'b'*24}), pid))
        feedback = {'account':{'user_id':'a'*24},'observed_at':'2026-10-22','rows':[{'_id':'b'*24,'标题':'其他笔记'}]}
        self.assertEqual(self.engine.reconcile_publications(feedback), [])
        feedback['rows'][0]['标题'] = draft['body']['artifact']['title']
        self.engine.link_publication(pid, 'https://www.xiaohongshu.com/explore/'+'c'*24)
        self.assertEqual(self.engine.reconcile_publications(feedback), [])
        feedback['rows'][0]['_id'] = 'c'*24
        self.assertEqual(self.engine.reconcile_publications(feedback), [pid])
        self.assertEqual(self.store.get('publications',pid)['state'], 'verified')

    def test_http_is_local_and_protects_writes(self):
        server = make_server(self.store, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}"
        try:
            data = json.load(urllib.request.urlopen(url + "/api/state"))
            payload = json.dumps({"action": "settings", "args": {"account_name": "测试"}}).encode()
            for headers in ({"Content-Type": "application/json"}, {"Content-Type": "application/json", "X-XHS-Token": data["csrf"], "Origin": "https://attacker.example"}):
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(urllib.request.Request(url + "/api/action", data=payload, headers=headers))
                self.assertEqual(error.exception.code, 400)
            headers = {"Content-Type": "application/json", "X-XHS-Token": data["csrf"]}
            response = json.load(urllib.request.urlopen(urllib.request.Request(url + "/api/action", data=payload, headers=headers)))
            self.assertEqual(response["result"]["account_name"], "测试")
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(urllib.request.Request(url + "/api/state", headers={"Host": "attacker.example"}))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(3)


if __name__ == "__main__":
    unittest.main()
