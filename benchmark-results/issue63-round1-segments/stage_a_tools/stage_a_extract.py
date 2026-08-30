"""Issue #63 Stage A extractor.

Reconstructs reviewable anchor evidence from two Round-1 submission artifacts.
Read-only wrt all benchmark ground truth. Produces:
  - review/provenance.json   (file hashes, video probes, anchor table)
  - review/stills/<sub>/<qid>/*.jpg  (labeled filmstrip contact sheets + anchor stills)
  - anchors.json             (machine-readable parsed anchors, no truth invented)

Frame->time projection: t = frame_id / ffprobe_avg_fps (legacy_time_projection_quality
is "unknown" in provenance v1 records; drift possible; noted in every record).
"""

from __future__ import annotations

import csv
import glob
import hashlib
import json
import os
import subprocess
import sys

ROOT = r"C:\Users\minhc\Code\vecna-issue-63\benchmark-results\issue63-round1-segments"
FINAL_DIR = r"C:\Users\minhc\AppData\Local\Temp\opencode\issue63\final\submission"
FINAL_ZIP = r"C:\Users\minhc\Downloads\submission-final-round1.zip"
T88_DIR = r"C:\Users\minhc\Downloads\submission-testing8.8\submission"
VIDEOS = r"C:\Users\minhc\Code\Official-Dataset\videos"
STILLS = os.path.join(ROOT, "review", "stills")

FFPROBE = glob.glob(
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*\ffmpeg-*\bin\ffprobe.exe")
)[0]
FFMPEG = glob.glob(
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*\ffmpeg-*\bin\ffmpeg.exe")
)[0]


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def find_video(video_id: str) -> str | None:
    lane = video_id.split("_")[0]
    direct = os.path.join(VIDEOS, lane, video_id + ".mp4")
    if os.path.isfile(direct):
        return direct
    for sub in ("L26A", "L26B", "L26C", "L26D", "L26E"):
        p = os.path.join(VIDEOS, sub, video_id + ".mp4")
        if os.path.isfile(p):
            return p
    return None


_probe_cache: dict[str, dict] = {}


def probe(path: str) -> dict:
    if path in _probe_cache:
        return _probe_cache[path]
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=r_frame_rate,avg_frame_rate,nb_frames,duration",
         "-of", "json", path],
        capture_output=True, text=True,
    )
    st = json.loads(out.stdout)["streams"][0]
    num, _, den = st["avg_frame_rate"].partition("/")
    fps = float(num) / float(den or 1)
    info = {
        "fps": fps,
        "nb_frames": int(st.get("nb_frames") or 0),
        "duration_s": float(st.get("duration") or 0),
    }
    _probe_cache[path] = info
    return info


def parse_submission(label: str, directory: str) -> list[dict]:
    records = []
    for f in sorted(glob.glob(os.path.join(directory, "*.csv"))):
        qid = os.path.splitext(os.path.basename(f))[0]  # query-p1-<n>-<type>
        n = int(qid.split("-")[2])
        qtype = qid.split("-")[3]
        with open(f, newline="", encoding="utf-8-sig") as fh:
            rows = [r for r in csv.reader(fh) if r and r[0].strip()]
        if not rows:
            records.append({"submission": label, "query_file": qid, "error": "empty_csv"})
            continue
        top = rows[0]
        rec = {
            "submission": label,
            "query_id": f"p1-{n}",
            "query_number": n,
            "submitted_type": qtype,
            "source_csv": os.path.basename(f),
            "csv_sha256": sha256(f),
            "row_count": len(rows),
        }
        vid = top[0].strip()
        frames = [int(x) for x in top[1:] if x.strip().isdigit()]
        answer = ",".join(top[len(frames) + 1:]).strip().strip('"') if qtype == "qa" else None
        rec.update({
            "video_id": vid,
            "video_path": find_video(vid),
            "anchor_frames": frames[:1] if qtype != "trake" else frames,
            "qa_answer_verbatim": answer,
        })
        records.append(rec)
    return records


def extract_tile(video: str, t: float, out_jpg: str, width: int = 384) -> bool:
    cmd = [
        FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{max(t, 0):.3f}", "-i", video,
        "-frames:v", "1", "-vf", f"scale={width}:-2",
        "-q:v", "3", out_jpg,
    ]
    return subprocess.run(cmd).returncode == 0


def main() -> int:
    subs = {"final_round1_10_4of13": FINAL_DIR, "testing88_submission633": T88_DIR}
    all_records = []
    for label, d in subs.items():
        all_records.extend(parse_submission(label, d))

    prov_files = {
        "submission-final-round1.zip": {
            "path": FINAL_ZIP, "sha256": sha256(FINAL_ZIP), "bytes": os.path.getsize(FINAL_ZIP),
        },
        "submission-testing8.8": {
            "path": T88_DIR, "sha256_of_member_csvs": True, "bytes": None,
        },
    }

    video_probes = {}
    for rec in all_records:
        vp = rec.get("video_path")
        if vp and vp not in video_probes:
            info = probe(vp)
            info["sha256_skipped_large_corpus"] = True
            video_probes[vp] = info
        if vp:
            fps = video_probes[vp]["fps"]
            rec["derived_anchor_times_s"] = [round(fr / fps, 3) for fr in rec["anchor_frames"]]
        else:
            rec["derived_anchor_times_s"] = None
            rec["blocker"] = "source_video_not_found_locally"

    os.makedirs(os.path.join(ROOT, "review"), exist_ok=True)
    with open(os.path.join(ROOT, "anchors.json"), "w", encoding="utf-8") as fh:
        json.dump(all_records, fh, indent=2, ensure_ascii=False)
    with open(os.path.join(ROOT, "review", "provenance.json"), "w", encoding="utf-8") as fh:
        json.dump({"artifacts": prov_files, "video_probes": video_probes}, fh, indent=2)

    print(f"{len(all_records)} submission CSVs parsed; {len(video_probes)} videos probed")
    for rec in all_records:
        flag = "BLOCKER" if rec.get("blocker") else "ok"
        print(flag, rec["submission"], rec.get("query_id"), rec.get("video_id"),
              rec.get("anchor_frames"), rec.get("derived_anchor_times_s"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
