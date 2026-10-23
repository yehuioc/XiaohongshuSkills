#!/usr/bin/env python3
"""
Batch download post images for all feeds in a combined or search-feeds JSON.

For each feed, downloads cover image (WB_DFT quality) and all carousel images,
saving them to images/<feed_id>/ alongside the JSON data.

Usage:
    # Download images for a combined JSON
    python scripts/batch_image_download.py \\
        --input data/research/<topic>/raw/combined/combined_<kw>.json \\
        --output-dir data/research/<topic>/raw/combined/images/

    # Download images for all combined JSONs in a directory
    python scripts/batch_image_download.py \\
        --input-dir data/research/<topic>/raw/combined/ \\
        --output-dir data/research/<topic>/raw/combined/images/

Output structure:
    images/<feed_id>/
      cover.jpg       ← cover (highest quality from imageList)
      01.jpg          ← carousel image 1
      02.jpg          ← carousel image 2
      metadata.json   ← image URLs + dimensions
"""

import argparse
import json
import os
import sys
import time
import uuid
import requests
from pathlib import Path
from urllib.parse import urlparse, unquote

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}
TIMEOUT = 30


def guess_ext(url: str, content_type: str | None) -> str:
    """Guess file extension from URL or Content-Type."""
    path = urlparse(url).path
    _, ext = os.path.splitext(unquote(path))
    if ext and ext.lower() in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"):
        return ext.lower()
    # XHS uses webp with !nc_n_webp_mw_1 suffix — check URL for webp hint
    if "webp" in url.lower():
        return ".webp"
    ct_map = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
              "image/webp": ".webp", "image/bmp": ".bmp"}
    if content_type:
        for mime, e in ct_map.items():
            if mime in content_type:
                return e
    return ".webp"  # XHS default is webp


def download_image(url: str, save_path: str, referer: str = "https://www.xiaohongshu.com/") -> bool:
    """Download a single image. Returns True on success."""
    try:
        hdrs = dict(HEADERS)
        hdrs["Referer"] = referer
        hdrs["Accept"] = "image/webp,image/*,*/*"
        resp = requests.get(url, timeout=TIMEOUT, stream=True, headers=hdrs)
        resp.raise_for_status()
        # Get content-type for extension
        ct = resp.headers.get("Content-Type", "")
        ext = guess_ext(url, ct)
        # Adjust save path extension if needed
        base, old_ext = os.path.splitext(save_path)
        if old_ext.lower() not in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"):
            save_path = base + ext
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"      ERR: {e}", flush=True)
        return False


def extract_image_urls(feed: dict) -> list[dict]:
    """Extract all image URLs from a feed's noteCard.imageList, preferring WB_DFT quality."""
    images = []
    nc = feed.get("noteCard", {})
    cover = nc.get("cover", {})
    image_list = nc.get("imageList", [])

    # Cover image first
    cover_url = cover.get("urlDefault") or cover.get("urlPre") or ""
    if cover_url and cover_url.startswith("http"):
        images.append({
            "label": "cover",
            "url": cover_url,
            "width": cover.get("width", 0),
            "height": cover.get("height", 0),
            "quality": "cover",
        })

    # Carousel images (prefer WB_DFT over WB_PRV)
    for idx, img in enumerate(image_list):
        info_list = img.get("infoList", [])
        # Prefer WB_DFT
        best_url = ""
        for info in info_list:
            url = info.get("url", "")
            if not url or not url.startswith("http"):
                continue
            if info.get("imageScene") == "WB_DFT":
                best_url = url
                break
            best_url = url  # fallback to first available
        if best_url:
            images.append({
                "label": f"{idx+1:02d}",
                "url": best_url,
                "width": img.get("width", 0),
                "height": img.get("height", 0),
                "quality": "carousel",
            })
    return images


def process_feed(feed: dict, images_base: str) -> dict:
    """Download images for a single feed. Returns image_paths dict."""
    fid = feed.get("id", str(uuid.uuid4().hex[:12]))
    # Sanitize feed_id for filesystem
    safe_fid = "".join(c if c.isalnum() or c in "-_" else "_" for c in fid)
    feed_dir = os.path.join(images_base, safe_fid)
    os.makedirs(feed_dir, exist_ok=True)

    image_urls = extract_image_urls(feed)
    downloaded = []

    for img_info in image_urls:
        url = img_info["url"]
        label = img_info["label"]
        # Guess extension
        ext = guess_ext(url, None)
        filename = f"{label}{ext}"
        filepath = os.path.join(feed_dir, filename)

        # Build referer — must use xiaohongshu.com, not the CDN domain
        referer = "https://www.xiaohongshu.com/"

        ok = download_image(url, filepath, referer)
        entry = {
            "label": label,
            "url": url,
            "file": filename,
            "path": filepath,
            "width": img_info.get("width", 0),
            "height": img_info.get("height", 0),
            "quality": img_info.get("quality", ""),
            "downloaded": ok,
        }
        downloaded.append(entry)

        if ok:
            size_kb = os.path.getsize(filepath) / 1024 if os.path.exists(filepath) else 0
            print(f"    {label}: OK ({size_kb:.0f}KB)")
        else:
            print(f"    {label}: FAILED")

        time.sleep(0.3)  # polite delay

    # Save metadata
    meta = {
        "feed_id": fid,
        "safe_fid": safe_fid,
        "image_count": len(image_urls),
        "downloaded_count": sum(1 for d in downloaded if d["downloaded"]),
        "images": downloaded,
    }
    with open(os.path.join(feed_dir, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    return meta


def process_json(input_path: str, output_dir: str, limit: int = 0):
    """Download images for all feeds in a JSON file."""
    with open(input_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Handle SEARCH_FEEDS_RESULT: or GET_FEED_DETAIL_RESULT: prefix
    for marker in ["SEARCH_FEEDS_RESULT:", "GET_FEED_DETAIL_RESULT:"]:
        idx = content.find(marker)
        if idx >= 0:
            content = content[idx + len(marker):].strip()
            break

    data = json.loads(content)
    keyword = data.get("keyword", os.path.basename(input_path))
    feeds = data.get("feeds", [])
    if limit > 0:
        feeds = feeds[:limit]

    # Filter to valid feeds
    valid = [f for f in feeds if f.get("id") and "rec_query" not in f.get("id", "")]
    print(f"Downloading images for '{keyword}': {len(valid)} feeds (of {len(feeds)} total)")

    results = []
    for i, feed in enumerate(valid):
        title = feed.get("noteCard", {}).get("displayTitle") or feed.get("detail_body", {}).get("title") or "(no title)"
        safe_title = title[:40].encode("ascii", errors="replace").decode("ascii")
        print(f"  [{i+1}/{len(valid)}] {safe_title}")
        meta = process_feed(feed, output_dir)
        results.append(meta)

    print(f"\nDone: {sum(1 for r in results if r['downloaded_count'] > 0)} feeds with images, "
          f"{sum(r['downloaded_count'] for r in results)} total images")


def main():
    ap = argparse.ArgumentParser(description="Batch download XHS post images")
    ap.add_argument("--input", help="Path to a single combined/search JSON")
    ap.add_argument("--input-dir", help="Directory of combined JSONs to process")
    ap.add_argument("--output-dir", default="data/searches/images", help="Output directory for images")
    ap.add_argument("--limit", type=int, default=0, help="Max feeds to download (0=all)")
    args = ap.parse_args()

    if args.input:
        process_json(args.input, args.output_dir, args.limit)
    elif args.input_dir:
        import glob
        json_files = sorted(glob.glob(os.path.join(args.input_dir, "combined_*.json")))
        if not json_files:
            json_files = sorted(glob.glob(os.path.join(args.input_dir, "*.json")))
            json_files = [f for f in json_files if "combined_" in os.path.basename(f) or "metadata" not in os.path.basename(f)]
        print(f"Found {len(json_files)} JSONs")
        for jf in json_files:
            process_json(jf, args.output_dir, args.limit)
            print("---")
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
