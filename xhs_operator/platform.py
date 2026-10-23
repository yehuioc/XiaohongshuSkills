"""Adapter for the existing dedicated CDP implementation; no Playwright."""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

from .content import normalize_source
from .store import PROJECT, Problem, identifier, now, digest

PORT = 9238
sys.path.insert(0, str(PROJECT / "scripts"))


class Platform:
    def __init__(self, store):
        self.store = store
        self.client = None
        self.lock_file = None
        self.preview_account = None
        self.session_digest = None

    def acquire(self):
        self.lock_file = (PROJECT / "data" / "operator-browser.lock").open("a+b")
        self.lock_file.seek(0)
        if not self.lock_file.read(1):
            self.lock_file.write(b"0")
            self.lock_file.flush()
        self.lock_file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.lock_file.close()
            self.lock_file = None
            raise Problem("专用浏览器正在处理另一个操作，请等待完成") from error

    def __enter__(self):
        paused = self.store.platform_pause()
        if paused:
            raise Problem("平台在线操作已暂停：" + paused["reason"])
        if self.store.settings()["browser"] != "cdp":
            raise Problem("当前使用内置浏览器，请在 Codex 聊天执行在线任务")
        from chrome_launcher import ensure_chrome
        from cdp_publish import XiaohongshuPublisher
        from account_manager import get_profile_dir
        profile = Path(get_profile_dir()).resolve()
        if not profile.is_relative_to(PROJECT):
            raise Problem("专用浏览器资料目录须位于本项目内，不能复用日常浏览器")
        self.acquire()
        try:
            if not ensure_chrome(port=PORT, headless=True):
                raise Problem("专用浏览器启动失败")
            self.client = XiaohongshuPublisher(port=PORT)
            self.client.connect(reuse_existing_tab=True)
        except BaseException as error:
            self.__exit__(None, None, None)
            raise Problem("专用浏览器连接失败；请在宿主终端启动工作台，或检查调试端口是否可达") from error
        return self

    def __exit__(self, *args):
        try:
            if self.client:
                self.client.disconnect()
        finally:
            if self.lock_file:
                self.lock_file.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.lock_file, fcntl.LOCK_UN)
                self.lock_file.close()
                self.lock_file = None

    def identity(self):
        self.client._navigate("https://www.xiaohongshu.com/explore")
        self.client._sleep(2, minimum_seconds=1)
        self.check_access()
        result = self.client._evaluate("""(() => {
          const s=window.__INITIAL_STATE__ || {};
          const unwrap=x=>x && (x._value || x.value || x);
          const u=unwrap(s.user); const v=unwrap(u && u.userInfo);
          return v && {user_id:v.userId || v.user_id || '', nickname:v.nickname || v.nickName || ''};
        })()""")
        if not isinstance(result, dict) or not re.fullmatch(r"[a-f0-9]{24}", str(result.get("user_id", ""))):
            raise Problem("未取得当前登录账号身份；请扫码登录后重新检查")
        return result

    def check_access(self):
        current = self.client._evaluate("({url:location.href,text:document.body?.innerText?.slice(0,1200)||''})")
        if isinstance(current, dict) and ("website-login/error" in current.get("url", "") or re.search(r"IP存在风险|安全限制|访问频繁|操作频繁|请完成验证|安全验证", current.get("text", ""))):
            reason = "小红书安全限制：" + current.get("text", "")[:250].replace("\n", "；")
            self.store.platform_pause(reason)
            self.store.event(None, "platform_limited", reason)
            raise Problem(reason + "。已停止在线请求，请先处理平台/网络条件，再在账号设置中恢复。")

    def assert_account(self):
        account = self.identity()
        expected = self.store.settings()["account_id"]
        if not expected or account["user_id"] != expected:
            raise Problem("当前登录账号与设置不匹配，请在设置中核对账号 ID")
        return account

    def login(self):
        result = self.client.get_login_qrcode()
        self.check_access()
        return result

    def research(self, task_id):
        settings = self.store.settings()
        task = self.store.get("tasks", task_id)
        body = task["body"]
        keywords = body.get("keywords") or settings["keywords"]
        if not keywords:
            raise Problem("请先填写关注关键词")
        if not self.client.check_home_login():
            self.check_access()
            raise Problem("小红书未登录，请先扫码")
        self.check_access()
        started, ids, visited, failures = time.monotonic(), [], set(), []
        limit = task["body"].get("max_sources", settings["max_sources"])

        def guard():
            if self.store.get("tasks", task_id)["state"] != "running":
                raise Problem("任务已取消或中断")
            if time.monotonic() - started > min(settings["max_seconds"], 600):
                raise Problem("本轮采集达到时间上限，已有资料已保留")
            self.client.command_timeout_seconds = min(15, max(1, min(settings["max_seconds"], 600) - (time.monotonic() - started)))

        for keyword in keywords[:10]:
            guard()
            result = self.client.search_feeds(keyword=keyword)
            self.check_access()
            for card in result.get("feeds", [])[:limit * 2]:
                guard()
                fid = card.get("id") or card.get("fid")
                token = card.get("xsecToken")
                if not re.fullmatch(r"[a-f0-9]{24}", str(fid)) or not token or fid in visited:
                    continue
                visited.add(fid)
                try:
                    response = self.client.get_feed_detail(fid, token)
                    self.check_access()
                    detail = response.get("detail", {})
                    # FeedExplorer returns note, comments, and related state together.
                    note = detail.get("note", detail)
                    desc = note.get("desc", "")
                    if not desc:
                        failures.append({"id": fid, "reason": "正文为空，未算作精读成功"})
                        continue
                    comments = detail.get("comments", {})
                    comments = comments.get("list", []) if isinstance(comments, dict) else comments
                    images = self.download_images(note, fid, guard)
                    source = normalize_source({
                        "title": note.get("title") or card.get("noteCard", {}).get("displayTitle", ""),
                        "text": desc, "url": f"https://www.xiaohongshu.com/explore/{fid}",
                        "author": note.get("user", {}).get("nickname", ""),
                        "comments": [c["content"] for c in comments[:20] if isinstance(c, dict) and c.get("content")],
                        "images": images, "metrics": note.get("interactInfo", {}),
                        "observed_at": now(), "transport": "dedicated_cdp",
                    })
                    sid = self.store.source(source)
                    ids.append(sid)
                    self.store.transition(task_id, "running", {"source_ids": ids, "collection_failures": failures})
                    self.store.event(task_id, "source", "已保存：" + source["title"])
                except Problem:
                    raise
                except Exception as error:
                    message = str(error)
                    failures.append({"id": fid, "reason": message[:200]})
                    if any(x in message.lower() for x in ("captcha", "验证", "风控", "-412", "406", "登录")) or len(failures) >= 2:
                        self.store.platform_pause("采集受限：" + message[:250])
                        raise Problem("采集受限，已停止本轮；已有资料保留，详情见任务事件") from error
                if len(ids) >= limit:
                    break
                time.sleep(1.5)
            if len(ids) >= limit:
                break
        if not ids:
            raise Problem("本轮未取得可读正文，不能生成无来源内容")
        return {"source_ids": ids, "collection_failures": failures}

    def download_images(self, note, fid, guard):
        import requests
        from PIL import Image
        from urllib.parse import urlsplit
        from io import BytesIO
        directory = self.store.home / "source-images" / fid
        directory.mkdir(parents=True, exist_ok=True)
        paths = []
        for item in note.get("imageList", [])[:4]:
            guard()
            url = item.get("urlDefault") or item.get("url")
            if not url:
                options = item.get("infoList", [])
                url = next((x.get("url") for x in options if x.get("imageScene") == "WB_DFT"), None)
            if not url:
                continue
            parsed = urlsplit(url)
            if parsed.scheme not in ("https", "http") or not parsed.hostname or not parsed.hostname.endswith(".xhscdn.com") or parsed.port not in (None, 80, 443):
                continue
            try:
                # No browser cookies are sent to the image host. Redirects are refused.
                with requests.get(url, headers={"Referer": "https://www.xiaohongshu.com/"}, timeout=15, stream=True, allow_redirects=False) as response:
                    if response.status_code != 200:
                        continue
                    data = bytearray()
                    for chunk in response.iter_content(65536):
                        guard()
                        data.extend(chunk)
                        if len(data) > 8_000_000:
                            raise Problem("来源图片过大")
                image = Image.open(BytesIO(data))
                if image.width * image.height > 24_000_000:
                    continue
                image.thumbnail((1400, 1800))
                path = directory / f"{identifier()}.jpg"
                image.convert("RGB").save(path, quality=88)
                paths.append(str(path.relative_to(PROJECT)))
            except Problem:
                raise
            except Exception:
                continue
        return paths

    def session_fingerprint(self):
        result = self.client._send("Network.getCookies", {"urls": ["https://www.xiaohongshu.com/"]})
        cookies = [(c["name"], c["value"]) for c in result.get("cookies", []) if c.get("name") == "web_session" and c.get("value")]
        if not cookies:
            raise Problem("未取得可核对的登录会话，不能正式发布")
        return digest(sorted(cookies))

    def preview(self, draft):
        account = self.assert_account()
        self.preview_account = account
        self.session_digest = self.session_fingerprint()
        artifact = draft["body"]["artifact"]
        directory = self.store.home / "drafts" / draft["id"] / draft["revision"]
        images = sorted((directory / "images").glob("*.png"))
        if len(images) != len(artifact["cards"]):
            raise Problem("图片缺失，禁止降级发布")
        self.client.publish(title=artifact["title"], content=(directory / "content.txt").read_text(encoding="utf-8"), image_paths=[str(p) for p in images])
        return {"state": "previewed", "account": account, "message": "已填写平台预览，未点击发布"}

    def preflight_submit(self, draft):
        from cdp_publish import SELECTORS
        if not self.preview_account or self.preview_account["user_id"] != self.store.settings()["account_id"] or self.session_fingerprint() != self.session_digest:
            raise Problem("登录会话或账号发生变化，未点击发布")
        title_selector = json.dumps(SELECTORS["title_input"])
        alternative = json.dumps(SELECTORS["title_input_alt"])
        selector = self.client._find_content_editor_selector()
        if not selector:
            raise Problem("当前页面不是可核对的发布编辑器")
        current = self.client._evaluate(f"""(() => {{const t=document.querySelector({title_selector})||document.querySelector({alternative});const b=document.querySelector({json.dumps(selector)});return {{title:t?.value||'',body:b?.innerText||''}};}})()""")
        artifact = draft["body"]["artifact"]
        expected = artifact["body"] + "\n\n" + " ".join("#" + t for t in artifact["tags"])
        if not isinstance(current, dict) or current.get("title") != artifact["title"] or re.sub(r"\s", "", current.get("body", "")) != re.sub(r"\s", "", expected):
            raise Problem("平台编辑器内容与已审阅稿件不一致，未点击发布")
        if self.client._count_uploaded_images() != len(artifact["cards"]):
            raise Problem("平台图片数量与已审阅稿件不一致，未点击发布")

    def submit(self, draft):
        self.preflight_submit(draft)
        url = self.client._click_publish()
        return {"state": "submitted", "url": url, "account": self.preview_account, "message": "已提交发布；需从内容列表核对，不能仅凭按钮点击认定公开可见"}

    def feedback(self):
        account = self.assert_account()
        if not self.client.check_login():
            raise Problem("创作者中心未登录")
        result = self.client.get_content_data(page_num=1, page_size=20)
        return {"account": account, "observed_at": now(), "rows": result.get("rows", []), "total": result.get("total"), "coverage": "后台第一页，最多20篇；不是账号全量"}
