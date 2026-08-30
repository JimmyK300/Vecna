"""Issue #63 Stage A filmstrip generator.

For each parsed anchor (anchors.json) extracts a labeled contact sheet around
the anchor from the local source MP4, plus one exact-anchor still.
No benchmark/truth files are touched.
"""

from __future__ import annotations

import glob
import json
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = r"C:\Users\minhc\Code\vecna-issue-63\benchmark-results\issue63-round1-segments"
STILLS = os.path.join(ROOT, "review", "stills")
FFMPEG = glob.glob(
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*\ffmpeg-*\bin\ffmpeg.exe")
)[0]

try:
    FONT = ImageFont.truetype("arial.ttf", 15)
    FONT_BIG = ImageFont.truetype("arialbd.ttf", 17)
except OSError:
    FONT = FONT_BIG = ImageFont.load_default()

TILE_W = 384


def grab(video: str, t: float, out: str) -> bool:
    if os.path.isfile(out) and os.path.getsize(out) > 0:
        return True
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
           "-ss", f"{max(t, 0):.3f}", "-i", video,
           "-frames:v", "1", "-vf", f"scale={TILE_W}:-2", "-q:v", "3", out]
    return subprocess.run(cmd).returncode == 0


def sheet(tiles: list[tuple[int, float]], video: str, fps: float, dur: float,
          out_jpg: str, anchor_frames: list[int], title: str) -> None:
    cols, pad, label_h = 3, 4, 22
    imgs = []
    for fr, t in tiles:
        tmp = out_jpg.replace(".jpg", f"_tmp_{fr}.jpg")
        tt = min(max(t, 0.0), max(dur - 0.05, 0))
        if not grab(video, tt, tmp):
            imgs.append(None)
            continue
        im = Image.open(tmp).convert("RGB")
        imgs.append((im, fr, t))
        os.remove(tmp)
    tw = TILE_W
    ths = [im.height if im else 216 for im, _, _ in imgs]
    rows = (len(imgs) + cols - 1) // cols
    row_h = []
    for r in range(rows):
        row_h.append(max(ths[r * cols:(r + 1) * cols]) + label_h)
    W = cols * (tw + pad) + pad
    H = sum(row_h) + pad * (rows + 1) + 30
    canvas = Image.new("RGB", (W, H), (18, 18, 18))
    d = ImageDraw.Draw(canvas)
    d.text((pad, 4), title, fill=(255, 220, 120), font=FONT_BIG)
    y = 30
    for r in range(rows):
        for c in range(cols):
            i = r * cols + c
            if i >= len(imgs):
                break
            item = imgs[i]
            x = pad + c * (tw + pad)
            ty = y + label_h
            if item:
                im, fr, t = item
                canvas.paste(im, (x, ty))
                is_anchor = fr in anchor_frames
                color = (255, 60, 60) if is_anchor else (60, 180, 90)
                if is_anchor:
                    d.rectangle([x - 2, ty - 2, x + im.width + 1, ty + im.height + 1], outline=color, width=3)
                d.text((x, ty - label_h), f"f={fr:06d}  t={t:.2f}s" + ("  <== ANCHOR" if is_anchor else ""),
                       fill=color, font=FONT)
            else:
                d.text((x, ty), "extract failed", fill=(255, 80, 80), font=FONT)
        y += row_h[r] + pad
    canvas.save(out_jpg, quality=88)


def main() -> int:
    with open(os.path.join(ROOT, "anchors.json"), encoding="utf-8") as fh:
        records = json.load(fh)
    with open(os.path.join(ROOT, "review", "provenance.json"), encoding="utf-8") as fh:
        probes = json.load(fh)["video_probes"]

    n_sheets = 0
    for rec in records:
        if rec.get("blocker"):
            continue
        vp = rec["video_path"]
        info = probes[vp]
        fps, dur = info["fps"], info["duration_s"]
        sub, qid = rec["submission"], rec["query_id"]
        qdir = os.path.join(STILLS, sub, qid)
        os.makedirs(qdir, exist_ok=True)
        anchors = rec["anchor_frames"]

        exact = os.path.join(qdir, f"anchor_{anchors[0]:06d}.jpg")
        cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
               "-ss", f"{min(anchors[0] / fps, max(dur - 0.05, 0)):.3f}", "-i", vp,
               "-frames:v", "1", "-vf", "scale=768:-2", "-q:v", "2", exact]
        subprocess.run(cmd)

        if len(anchors) == 1:
            a = anchors[0] / fps
            tiles = [(round((a + dt) * fps), a + dt) for dt in range(-8, 9, 2)]
            out = os.path.join(qdir, f"sheet_{anchors[0]:06d}.jpg")
            title = f"{sub} {qid} {rec['submitted_type']}  {rec['video_id']}  anchor f={anchors[0]} t={a:.2f}s"
            sheet(tiles, vp, fps, dur, out, [anchors[0]], title)
        else:
            for ei, afr in enumerate(anchors, start=1):
                a = afr / fps
                tiles = [(round((a + dt) * fps), a + dt) for dt in range(-6, 7, 2)]
                out = os.path.join(qdir, f"sheet_E{ei}_{afr:06d}.jpg")
                title = (f"{sub} {qid} trake E{ei}/{len(anchors)}  {rec['video_id']}"
                         f"  anchor f={afr} t={a:.2f}s")
                sheet(tiles, vp, fps, dur, out, [afr], title)
                n_sheets += 1
                print("done", sub, qid, f"E{ei}")
                continue
            continue
        n_sheets += 1
        print("done", sub, qid)
    print("sheets:", n_sheets)
    return 0


if __name__ == "__main__":
    sys.exit(main())
