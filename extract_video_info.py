import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from fractions import Fraction
from pathlib import Path

# Ensure UTF-8 output on Windows console
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")



def get_fps_info(video_path: Path) -> dict:
    ffprobe_cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=r_frame_rate,avg_frame_rate",
        str(video_path),
    ]
    res = subprocess.run(ffprobe_cmd, capture_output=True, text=True)

    if not res.stdout.strip():
        ffprobe_cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-of",
            "compact=p=0",
            "-select_streams",
            "0",
            "-show_entries",
            "stream=r_frame_rate,avg_frame_rate",
            str(video_path),
        ]
        res = subprocess.run(ffprobe_cmd, capture_output=True, text=True)

    entry_dict = {}
    for item in res.stdout.strip().replace("stream|", "").split("|"):
        if "=" in item:
            k, v = item.split("=", 1)
            entry_dict[k] = v

    r_fps_str = entry_dict.get("r_frame_rate", "25/1")
    avg_fps_str = entry_dict.get("avg_frame_rate", r_fps_str)

    fps_fraction = None
    for cand in [r_fps_str, avg_fps_str]:
        if cand and cand != "0/0":
            try:
                frac = Fraction(cand)
                if frac > 0:
                    fps_fraction = frac
                    break
            except (ValueError, ZeroDivisionError):
                continue

    if fps_fraction is None:
        fps_fraction = Fraction(25, 1)

    fps_float = float(fps_fraction)

    return {
        "frame_rate": fps_float,
        "frame_rate_fraction": str(fps_fraction),
        "r_frame_rate": r_fps_str,
        "avg_frame_rate": avg_fps_str,
    }


def process_video(video_path: Path, output_dir: Path, overwrite: bool = False):
    output_file = output_dir / f"{video_path.stem}.json"
    if output_file.exists() and not overwrite:
        return video_path.stem, "SKIPPED", None

    try:
        data = get_fps_info(video_path)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return video_path.stem, "OK", data
    except Exception as e:
        return video_path.stem, "ERROR", str(e)


def main():
    parser = argparse.ArgumentParser(
        description="Trích xuất riêng video-info (.json) cho video trong workspace Vecna / AIC51"
    )
    parser.add_argument(
        "--workspace",
        "-w",
        type=str,
        default="workspace_3",
        help="Đường dẫn đến thư mục workspace (mặc định: workspace_3)",
    )
    parser.add_argument(
        "--overwrite",
        "-o",
        action="store_true",
        help="Ghi đè file video-info đã có",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=16,
        help="Số luồng ffprobe chạy song song (mặc định: 16)",
    )
    args = parser.parse_args()

    work_dir = Path(args.workspace).resolve()
    video_dir = work_dir / "data" / "videos"
    info_dir = work_dir / "data" / "video_info"

    if not video_dir.exists():
        print(f"[!] Không tìm thấy thư mục video: {video_dir}")
        return

    info_dir.mkdir(parents=True, exist_ok=True)

    supported_ext = {".mp4", ".mkv", ".avi", ".mov", ".webm"}
    video_files = sorted(
        [f for f in video_dir.glob("*") if f.suffix.lower() in supported_ext and not f.is_dir()]
    )

    total = len(video_files)
    print(f"[*] Workspace: {work_dir}")
    print(f"[*] Tìm thấy {total} videos trong {video_dir}")
    print(f"[*] Đích xuất video_info: {info_dir}")
    print(f"[*] Đang xử lý với {args.workers} luồng...")

    start_time = time.time()
    ok_count = 0
    skip_count = 0
    err_count = 0

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(process_video, v, info_dir, args.overwrite): v
            for v in video_files
        }
        for future in as_completed(futures):
            v_stem, status, detail = future.result()
            if status == "OK":
                ok_count += 1
            elif status == "SKIPPED":
                skip_count += 1
            else:
                err_count += 1
                print(f"[X] Lỗi {v_stem}: {detail}")

    elapsed = time.time() - start_time
    print(f"\n[+] Hoàn thành sau {elapsed:.2f}s!")
    print(f"    - Thành công mới: {ok_count}")
    print(f"    - Đã bỏ qua (đã có): {skip_count}")
    print(f"    - Lỗi: {err_count}")
    print(f"    - Tổng số file video_info hiện có: {len(list(info_dir.glob('*.json')))}")


if __name__ == "__main__":
    main()
