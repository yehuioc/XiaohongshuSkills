#!/usr/bin/env python3
"""
Batch extract feed detail using a SINGLE in-process CDP connection.
No subprocess, no Chrome tab leaks — one WebSocket reused for all feeds.
"""

import argparse
import json
import os
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from cdp_publish import XiaohongshuPublisher, CDPError
from feed_explorer import make_feed_detail_url

if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def run_batch(input_path: str, output_dir: str, limit: int = 0):
    """Process all feeds in a search JSON using a single CDP connection."""
    publisher = XiaohongshuPublisher()
    try:
        publisher.connect()
        if not publisher.check_home_login():
            print("NOT_LOGGED_IN")
            return

        with open(input_path, "r", encoding="utf-8") as f:
            content = f.read()
        idx = content.find("SEARCH_FEEDS_RESULT:")
        if idx >= 0:
            data = json.loads(content[idx + 20:].strip())
        else:
            data = json.loads(content)

        keyword = data.get("keyword", "unknown")
        feeds = data.get("feeds", [])
        if limit > 0:
            feeds = feeds[:limit]
        valid = [f for f in feeds if f.get("id") and "rec_query" not in f.get("id", "")]
        print(f"Processing '{keyword}': {len(valid)} feeds")

        combined_feeds = []
        success = 0
        for i, feed in enumerate(valid):
            fid = feed.get("id", "")
            xt = feed.get("xsecToken", "")
            title = feed.get("noteCard", {}).get("displayTitle", "(no title)")
            safe = title[:40].encode("ascii", errors="replace").decode("ascii")
            print(f"  [{i+1}/{len(valid)}] {safe}... ", end="", flush=True)

            combined = dict(feed)
            try:
                url = make_feed_detail_url(fid, xt)
                publisher._navigate(url)
                publisher._sleep(2, minimum_seconds=1.0)
                publisher._check_feed_page_accessible()

                note_json = publisher._evaluate("""
                    (() => {
                        const s = window.__INITIAL_STATE__;
                        if (!s || !s.note || !s.note.noteDetailMap) return null;
                        const map = s.note.noteDetailMap;
                        const nid = Object.keys(map)[0];
                        if (!nid) return null;
                        const n = map[nid].note || {};
                        const c = map[nid].comments || {};
                        return JSON.stringify({desc: n.desc||'', title: n.title||'',
                            tagList: n.tagList||[], user: n.user||{},
                            interactInfo: n.interactInfo||{},
                            commentList: (c.list||[]).slice(0,20),
                            commentCursor: c.cursor||'', commentHasMore: !!c.hasMore});
                    })()
                """)
                if note_json and isinstance(note_json, str):
                    body = json.loads(note_json)
                    body["fetched"] = bool(body.get("desc"))
                    if not body["fetched"]:
                        body["error"] = "empty_body"
                    combined["detail_body"] = body
                    combined_feeds.append(combined)
                    success += int(body["fetched"])
                    status = "OK" if body["fetched"] else "EMPTY_BODY"
                    print(f"{status} ({len(body.get('desc',''))} chars)")
                else:
                    combined["detail_body"] = {"desc":"","fetched":False,"error":"extraction_failed"}
                    combined_feeds.append(combined)
                    print("FAILED")
            except CDPError:
                combined["detail_body"] = {"desc":"","fetched":False,"error":"inaccessible"}
                combined_feeds.append(combined)
                print("INACCESSIBLE")
            time.sleep(1.0)

        output_data = {"keyword": keyword, "source_file": os.path.basename(input_path),
                       "total": len(valid), "fetched": success, "failed": len(valid)-success,
                       "feeds": combined_feeds}
        os.makedirs(output_dir, exist_ok=True)
        safe_kw = "".join(c if c.isalnum() or c in "-_" else "_" for c in keyword)
        path = os.path.join(output_dir, f"combined_{safe_kw}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        print(f"  Saved: {path} ({success}/{len(valid)} fetched)")
    finally:
        try:
            publisher.ws.close()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input")
    ap.add_argument("--input-dir")
    ap.add_argument("--output-dir", default="data/searches/combined")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--no-chrome-cleanup", action="store_true")
    args = ap.parse_args()
    if args.input:
        run_batch(args.input, args.output_dir, args.limit)
    elif args.input_dir:
        import glob
        files = sorted(glob.glob(os.path.join(args.input_dir, "*.json")))
        files = [f for f in files if "combined_" not in os.path.basename(f)]
        print(f"Found {len(files)} search JSONs")
        for jf in files:
            run_batch(jf, args.output_dir, args.limit)
            print("---")
    else:
        ap.print_help()
    if not args.no_chrome_cleanup:
        import subprocess
        launcher = os.path.join(SCRIPT_DIR, "chrome_launcher.py")
        if os.path.exists(launcher):
            subprocess.run([sys.executable, launcher, "--kill"],
                           capture_output=True, timeout=15,
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"})
            print("[batch] Chrome cleaned up.")


if __name__ == "__main__":
    main()
