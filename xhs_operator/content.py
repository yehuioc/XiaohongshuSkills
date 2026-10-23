from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from .store import PROJECT, Problem, digest, now


def plain(value, maximum=10000):
    if not isinstance(value, str) or len(value) > maximum or "\x00" in value:
        raise Problem("文字类型或长度无效")
    return value.strip()


def clean_url(value):
    u = urlsplit(plain(value, 3000))
    if u.scheme not in ("http", "https") or not u.hostname or u.username or u.password:
        raise Problem("来源必须使用正常的网页链接")
    return urlunsplit((u.scheme, u.netloc, u.path, "", ""))


def normalize_source(raw):
    if not isinstance(raw, dict):
        raise Problem("来源必须是 JSON 对象")
    title = plain(raw.get("title", ""), 300)
    text = plain(raw.get("text", ""), 60000)
    comments = raw.get("comments", [])
    if not isinstance(comments, list) or len(comments) > 100:
        raise Problem("评论最多保留 100 条")
    comments = [plain(x, 4000) for x in comments]
    if not title or not (text or comments or raw.get("images")):
        raise Problem("来源缺少标题或可读正文/评论/实际图片，不能以列表卡片冒充精读")
    assets = raw.get("images", [])
    if not isinstance(assets, list) or len(assets) > 30:
        raise Problem("图片数量无效")
    images = []
    for entry in assets:
        path = (PROJECT / plain(entry, 2000)).resolve()
        if not path.is_relative_to(PROJECT) or not path.is_file() or path.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
            raise Problem("来源图片必须是项目内已有的图片文件")
        images.append(str(path.relative_to(PROJECT)))
    metrics = raw.get("metrics", {})
    if not isinstance(metrics, dict) or len(metrics) > 20:
        raise Problem("来源数据格式无效")
    return {
        "title": title, "text": text, "url": clean_url(raw.get("url", "")),
        "author": plain(raw.get("author", ""), 200), "comments": comments, "images": images,
        "metrics": metrics, "observed_at": plain(raw.get("observed_at", now()), 100),
        "published_at": plain(raw.get("published_at", "未注明"), 100), "historical": raw.get("historical") is True, "transport": plain(raw.get("transport", "manual"), 100),
        "coverage": {"text": bool(text), "comments_sampled": len(comments), "images_available": len(images), "images_read": False},
    }


def import_combined(store, path):
    path = Path(path).resolve()
    if not path.is_relative_to(PROJECT) or not path.is_file() or path.stat().st_size > 15_000_000:
        raise Problem("仅导入本项目内的有界 JSON 资料")
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    records = raw.get("feeds", [])
    if not isinstance(records, list) or len(records) > 500:
        raise Problem("导入资料格式或规模无效")
    result, skipped = [], []
    for record in records:
        card = record.get("noteCard", {})
        detail = record.get("detail_body", {})
        note_id = record.get("id") or record.get("fid")
        if not note_id or not detail.get("desc"):
            skipped.append(note_id or "unknown")
            continue
        image_dir = path.parent / "images" / note_id
        images = [str(p.relative_to(PROJECT)) for p in sorted(image_dir.glob("*")) if p.suffix.lower() in (".png", ".jpg", ".webp", ".jpeg")][:30]
        comments = []
        for c in detail.get("commentList", []):
            if isinstance(c, dict) and c.get("content"):
                comments.append(str(c["content"]))
        source = normalize_source({
            "title": detail.get("title") or card.get("displayTitle", ""), "text": detail["desc"],
            "url": f"https://www.xiaohongshu.com/explore/{note_id}",
            "author": (detail.get("user") or card.get("user", {})).get("nickname") or card.get("user", {}).get("nickName", ""),
            "comments": comments[:100], "images": images,
            "metrics": detail.get("interactInfo", card.get("interactInfo", {})),
            "observed_at": raw.get("observed_at", "历史导入，原采集时间见来源目录"),
            "historical": True, "transport": "legacy_import",
        })
        result.append(store.source(source))
    return {"source_ids": result, "skipped": skipped}


def source_image_inputs(sources, maximum=12):
    inputs = []
    for source in sources:
        for index, path in enumerate(source["body"]["images"], 1):
            if len(inputs) >= maximum:
                return inputs
            inputs.append({"input_index": len(inputs) + 1, "source_id": source["id"], "image_index": index, "path": path})
    return inputs


def validate_artifact(raw, sources, mode="cards"):
    if not isinstance(raw, dict):
        raise Problem("生产结果必须是 JSON 对象")
    if mode == "text":
        native_text = plain(raw.get("native_text", ""), 500)
        if not native_text:
            raise Problem("纯文案需要非空的配图文字（全部配图文字合计不超过500字符）")
        if raw.get("cards", []):
            raise Problem("纯文案模式不能夹带本地卡片")
        checked = validate_artifact(raw | {"cards": [{"title": "仅作文字校验", "points": ["校验"]}] * 3}, sources)
        return checked | {"cards": [], "native_text": native_text, "mode": "text"}
    if not isinstance(raw, dict):
        raise Problem("生产结果必须是 JSON 对象")
    title, body = plain(raw.get("title", ""), 100), plain(raw.get("body", ""), 10000)
    if not title or sum(2 if ord(c) > 127 else 1 for c in title) > 38:
        raise Problem("标题超过当前发布器的 38 计数限制，请压缩标题")
    if not 80 <= len(body) <= 1000:
        raise Problem("正文须为 80–1000 字符；不能交付空稿或超长稿")
    tags = raw.get("tags", [])
    if not isinstance(tags, list) or not 1 <= len(tags) <= 10:
        raise Problem("话题须为 1–10 个")
    tags = [plain(t, 25).lstrip("#") for t in tags]
    if any(not t or re.search(r"\s|#", t) for t in tags):
        raise Problem("话题不能包含空格或额外井号")
    refs = {s["id"]: s["body"] for s in sources}
    images = {(x["source_id"], x["image_index"]): x["path"] for x in source_image_inputs(sources)}
    evidence = raw.get("evidence", [])
    if not isinstance(evidence, list) or not evidence or len(evidence) > 30:
        raise Problem("必须提供可核对的主张与来源")
    checked = []
    for row in evidence:
        if not isinstance(row, dict):
            raise Problem("证据格式无效")
        sid, quote = row.get("source_id"), plain(row.get("quote", ""), 2000)
        if sid not in refs:
            raise Problem("证据引用了任务范围外的来源")
        medium, image_index = row.get("medium", "text"), row.get("image_index", 0)
        if medium not in ("text", "image") or type(image_index) is not int:
            raise Problem("证据媒介或图片页码无效")
        image_path = None
        if medium == "text":
            corpus = refs[sid]["text"] + "\n" + "\n".join(refs[sid]["comments"])
            if image_index != 0 or len(quote) < 4 or re.sub(r"\s", "", quote) not in re.sub(r"\s", "", corpus):
                raise Problem("证据原文未在来源中找到，不能伪造引用")
        else:
            image_path = images.get((sid, image_index))
            if not image_path or not (PROJECT / image_path).is_file() or len(quote) < 4:
                raise Problem("图片证据必须指向本任务实际附件范围内的来源图片")
        claim = plain(row.get("claim", ""), 2000)
        if not claim:
            raise Problem("证据必须说明支持的主张")
        checked.append({"source_id": sid, "quote": quote, "claim": claim, "medium": medium, "image_index": image_index,
                        "verification": "exact_text_match" if medium == "text" else "image_requires_review",
                        **({"image_path": image_path} if image_path else {})})
    cards = raw.get("cards", [])
    if not isinstance(cards, list) or not 3 <= len(cards) <= 12:
        raise Problem("完整图文需要 3–12 张卡片，包含封面和结尾")
    normalized = []
    for i, card in enumerate(cards):
        if not isinstance(card, dict):
            raise Problem("卡片格式无效")
        heading = plain(card.get("title", ""), 44)
        points = card.get("points", [])
        if not heading or not isinstance(points, list) or not 1 <= len(points) <= 5:
            raise Problem("每张卡片需要标题和 1–5 段有效内容")
        points = [plain(p, 130) for p in points]
        if any(not p for p in points) or sum(map(len, points)) > 300:
            raise Problem("卡片过密或含空段，请重新拆分")
        normalized.append({"title": heading, "points": points, "eyebrow": plain(card.get("eyebrow", "封面" if i == 0 else "方法"), 24)})
    insights = raw.get("insights", [])
    if not isinstance(insights, list) or len(insights) > 12:
        raise Problem("观察记录格式无效")
    return {"title": title, "body": body, "tags": tags, "cards": normalized,
            "evidence": checked, "insights": [plain(x, 2000) for x in insights],
            "limitations": plain(raw.get("limitations", ""), 5000)}


def font_path(serif=False):
    candidates = ([Path("C:/Windows/Fonts/simsun.ttc")] if serif else []) + [Path("C:/Windows/Fonts/msyh.ttc"), Path("C:/Windows/Fonts/simhei.ttf"), Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")]
    for path in candidates:
        if path.is_file():
            return str(path)
    raise Problem("缺少中文字体，请在 content.font_path 中指定本机中文字体")


def balanced_heading(value, measure, width):
    """Balance automatic title lines, retaining the author's explicit breaks."""
    from functools import lru_cache
    closing = "，。！？；：、）》】〉”’％%,.!?;:)]}"
    opening = "（《【〈“‘([{"
    result = []
    for text in value.split("\n"):
        if not text:
            result.append("")
            continue
        minimum = max(1, int(measure(text) / width))
        for count in range(minimum, len(text) + 1):
            target = measure(text) / count

            @lru_cache(None)
            def partition(start, remaining):
                if remaining == 0:
                    return (0, []) if start == len(text) else None
                best = None
                for end in range(start + 1, len(text) - remaining + 2):
                    line = text[start:end].strip()
                    length = measure(line)
                    if length > width:
                        break
                    if not line or line[0] in closing or line[-1] in opening:
                        continue
                    tail = partition(end, remaining - 1)
                    if tail is None:
                        continue
                    cost = (length - target) ** 2 + tail[0]
                    if end < len(text) and text[end - 1].isascii() and text[end - 1].isalnum() and text[end].isascii() and text[end].isalnum():
                        cost += width ** 2  # Keep Latin words together when possible.
                    if line[-1] in closing:
                        cost -= width ** 2 * .01
                    if best is None or cost < best[0]:
                        best = (cost, [line] + tail[1])
                return best

            chosen = partition(0, count)
            if chosen is not None:
                result.extend(chosen[1])
                break
        else:
            raise Problem("标题无法在当前字号内换行，请调整标点或拆分标题")
    return result


def cover_heading(value, measure, width=910):
    if "\n" not in value:
        clauses = re.findall(r"[^，：；！？。,.!?;:]+[，：；！？。,.!?;:]*", value)
        if 2 <= len(clauses) <= 3 and min(map(len, clauses)) >= 3 and max(map(len, clauses)) <= min(map(len, clauses)) * 2.5:
            for size in range(118, 105, -2):
                if all(measure(line, size) <= width for line in clauses):
                    return "\n".join(clauses), size
    return value, 118


def render_package(directory, artifact, style="editorial", brand="创作札记"):
    from PIL import Image, ImageDraw, ImageFont
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "images").mkdir(exist_ok=True)
    paper, ink, muted, accent = (("#F4F0E8", "#22231E", "#717368", "#983F32") if style == "editorial" else ("#F6F7F7", "#171C21", "#64707A", "#244FD5"))
    serif = style == "editorial"
    font = lambda size, display=False: ImageFont.truetype(font_path(serif and display), size)
    previews = []
    layout = []
    for i, card in enumerate(artifact["cards"]):
        im = Image.new("RGB", (1080, 1440), paper)
        d = ImageDraw.Draw(im)
        bounds = []

        def wrap(value, f, width):
            lines, current = [], ""
            closing = "，。！？；：、）》】〉”’％%,.!?;:)]}"
            opening = "（《【〈“‘([{"
            for char in value:
                if char == "\n":
                    lines.append(current)
                    current = ""
                elif d.textlength(current + char, font=f) > width:
                    if current and (char in closing or current[-1] in opening):
                        lines.append(current[:-1])
                        current = current[-1] + char
                    else:
                        lines.append(current)
                        current = char
                else:
                    current += char
            if current:
                lines.append(current)
            return lines

        def paragraph(value, x, y, size, width, color=ink, display=False, gap=1.45):
            f = font(size, display)
            lines = balanced_heading(value, lambda s: d.textlength(s, font=f), width) if display else wrap(value, f, width)
            for line in lines:
                box = d.textbbox((x, y), line, font=f)
                if box[2] > 1008 or box[3] > 1290:
                    raise Problem(f"第 {i+1} 张卡片文字溢出，请压缩文案，不能缩成小字")
                bounds.append(list(box))
                d.text((x, y), line, font=f, fill=color)
                y += int(size * gap)
            return y

        d.line((80, 96, 1000, 96), fill=ink, width=2)
        paragraph(brand[:20], 80, 50, 23, 700, muted)
        paragraph(f"{i+1:02d} / {len(artifact['cards']):02d}", 880, 50, 22, 120, muted)
        paragraph(card["eyebrow"], 82, 144, 25, 800, accent)
        if i == 0:
            heading, heading_size = cover_heading(card["title"], lambda text, size: d.textlength(text, font=font(size, True)))
            y = paragraph(heading, 76, 240, heading_size, 910, display=True, gap=1.25)
            y = max(y + 110, 780)
            d.rectangle((80, y - 35, 210, y - 29), fill=accent)
            for point in card["points"]:
                y = paragraph(point, 82, y, 43, 880, gap=1.55) + 35
        else:
            y = max(paragraph(card["title"], 78, 220, 72, 915, display=True, gap=1.35) + 110, 445)
            size = 44
            heights = [len(wrap(p, font(size), 805)) * int(size * 1.65) for p in card["points"]]
            if y + sum(heights) + 65 * (len(heights) - 1) > 1240:
                size = 38
                heights = [len(wrap(p, font(size), 805)) * int(size * 1.65) for p in card["points"]]
            available = 1240 - y - sum(heights)
            if available < 40 * (len(heights) - 1):
                raise Problem(f"第 {i+1} 张卡片过密，请拆页或压缩内容")
            spacing = available / len(heights)
            for index, point in enumerate(card["points"]):
                d.line((80, y - 12, 1000, y - 12), fill="#C9C9BF", width=1)
                paragraph(f"{index+1:02d}", 82, y + 7, 28, 80, accent)
                y = paragraph(point, 185, y, size, 805, gap=1.65) + int(spacing)
        d.line((80, 1325, 1000, 1325), fill=ink, width=1)
        d.text((80, 1350), "保留判断过程，留下可用方法", font=font(23), fill=muted)
        name = f"{i+1:02d}.png"
        im.save(directory / "images" / name, optimize=True)
        previews.append(im.resize((270, 360)))
        layout.append({"page": i + 1, "size": [1080, 1440], "text_bounds": bounds})
    cols = max(1, min(4, len(previews)))
    sheet = Image.new("RGB", (cols * 290 + 20, max(1, ((len(previews) + cols - 1) // cols)) * 380 + 20), "#DDDDD5")
    for i, preview in enumerate(previews):
        sheet.paste(preview, (20 + (i % cols) * 290, 20 + (i // cols) * 380))
    if previews:
        sheet.save(directory / "contact-sheet.png")
    if artifact.get("native_text"):
        (directory / "native-text.txt").write_text(artifact["native_text"], encoding="utf-8")
    (directory / "title.txt").write_text(artifact["title"], encoding="utf-8")
    (directory / "content.txt").write_text(artifact["body"] + "\n\n" + " ".join("#" + t for t in artifact["tags"]), encoding="utf-8")
    (directory / "artifact.json").write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    (directory / "layout.json").write_text(json.dumps(layout, indent=2), encoding="utf-8")
    hashes = {str(p.relative_to(directory)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in directory.rglob("*") if p.is_file()}
    return {"pages": len(previews), "contact_sheet": "contact-sheet.png", "artifact_hash": digest(artifact), "files": hashes}
