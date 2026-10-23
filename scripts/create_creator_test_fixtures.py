"""Generate clearly marked, non-personal media for authorized creator research."""
import hashlib
import json
from pathlib import Path
import subprocess

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/operator/diagnostics/creator-research/fixtures'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    image = Image.new('RGB', (720, 960), '#f4ecd9')
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=46)
    draw.text((55, 250), 'TEST ONLY\n\nDO NOT PUBLISH\n\nCreator research\n\nNo personal data', fill='#174e3c', font=font, spacing=18)
    image.save(OUT / 'creator-test.png')
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    base = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-y']
    subprocess.run(base + ['-loop', '1', '-i', str(OUT / 'creator-test.png'), '-t', '20', '-r', '12', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(OUT / 'creator-test.mp4')], check=True, timeout=40)
    subprocess.run(base + ['-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=22050', '-t', '601', '-af', 'volume=0.02', '-c:a', 'libmp3lame', '-b:a', '32k', str(OUT / 'creator-test.mp3')], check=True, timeout=40)
    manifest = {}
    for kind, name, mime in [('image', 'creator-test.png', 'image/png'), ('video', 'creator-test.mp4', 'video/mp4'), ('audio', 'creator-test.mp3', 'audio/mpeg')]:
        path = OUT / name
        manifest[kind] = {'name': name, 'mime': mime, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'bytes': path.stat().st_size}
    (OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == '__main__':
    main()
