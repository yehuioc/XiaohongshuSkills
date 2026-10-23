#!/usr/bin/env python3
"""
Batch search XHS with a SINGLE in-process CDP connection.
No subprocess, no Chrome tab leaks — one WebSocket reused for all keywords.
"""

import argparse
import json
import os
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from cdp_publish import XiaohongshuPublisher, CDPError
from feed_explorer import SearchFilters

if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def search_one(publisher: XiaohongshuPublisher, keyword: str, filters: SearchFilters | None = None) -> dict:
    """Search a single keyword using the shared publisher connection."""
    result = publisher.search_feeds(keyword=keyword, filters=filters)
    feeds = result.get("feeds", [])
    return {
        "keyword": keyword,
        "recommended_keywords": result.get("recommended_keywords", []),
        "count": len(feeds),
        "feeds": feeds,
    }


def run_batch(keywords: list[str], output_dir: str, filters: SearchFilters | None = None):
    publisher = XiaohongshuPublisher()
    try:
        publisher.connect()
        if not publisher.check_home_login():
            print("NOT_LOGGED_IN — please log in first.")
            return

        os.makedirs(output_dir, exist_ok=True)
        for i, kw in enumerate(keywords):
            print(f"[{i+1}/{len(keywords)}] Searching: {kw}... ", end="", flush=True)
            try:
                data = search_one(publisher, kw, filters)
                safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in kw)
                ts = time.strftime("%Y%m%d-%H%M%S")
                path = os.path.join(output_dir, f"{ts}_search_{safe}.json")
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                print(f"OK ({data['count']} feeds) → {os.path.basename(path)}")
            except CDPError as e:
                print(f"FAILED: {e}")
            time.sleep(4)  # polite gap between searches
    finally:
        try:
            publisher.ws.close()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keywords", nargs="+", required=True, help="Keywords to search")
    ap.add_argument("--keywords-file", help="File with one keyword per line")
    ap.add_argument("--output-dir", default="data/searches", help="Output directory")
    ap.add_argument("--no-chrome-cleanup", action="store_true")
    args = ap.parse_args()

    keywords = args.keywords
    if args.keywords_file:
        with open(args.keywords_file, "r", encoding="utf-8") as f:
            keywords.extend(line.strip() for line in f if line.strip())

    run_batch(keywords, args.output_dir)

    if not args.no_chrome_cleanup:
        import subprocess
        launcher = os.path.join(SCRIPT_DIR, "chrome_launcher.py")
        if os.path.exists(launcher):
            subprocess.run([sys.executable, launcher, "--kill"],
                           capture_output=True, timeout=15,
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"})
            print("[batch_search] Chrome cleaned up.")


if __name__ == "__main__":
    main()
