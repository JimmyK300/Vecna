#!/usr/bin/env python3
"""
Script to batch compress S01 videos to 75% resolution (480x270) using NVIDIA NVENC.
Original videos remain 100% untouched and safe.
"""

import os
import sys
import time
import argparse
import subprocess
from pathlib import Path

# Fix Windows console UTF-8 output
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def format_size(bytes_val: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_val < 1024.0:
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.2f} TB"

def main():
    parser = argparse.ArgumentParser(description="Batch compress S01 videos to 75% resolution (480x270)")
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path(r"E:\Projects\Vecna\workspace\data\videos"),
        help="Thu muc chua video goc",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(r"E:\Projects\Vecna\workspace\data\compressed_videos_75p"),
        help="Thu muc chua video nen dau ra (mac dinh: workspace\\data\\compressed_videos_75p)",
    )
    parser.add_argument(
        "--pattern",
        type=str,
        default="S01-V*.mp4",
        help="Pattern video can nen (mac dinh: S01-V*.mp4)",
    )
    parser.add_argument(
        "--scale",
        type=str,
        default="480:270",
        help="Do phan giai dau ra: 480:270 (75%% cua 640x360)",
    )
    parser.add_argument(
        "--cq",
        type=int,
        default=28,
        help="Constant Quality NVENC (mac dinh: 28)",
    )
    parser.add_argument(
        "--preset",
        type=str,
        default="p4",
        help="Preset NVENC (mac dinh: p4)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Ghi de neu file da ton tai trong thu muc output",
    )
    args = parser.parse_args()

    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()

    if not input_dir.exists():
        print(f"[!] Khong tim thay thu muc input: {input_dir}")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    videos = sorted(list(input_dir.glob(args.pattern)))
    if not videos:
        print(f"[!] Khong tim thay video nao voi pattern '{args.pattern}' tai {input_dir}")
        sys.exit(1)

    print("=" * 70)
    print("🎬 VECNA BATCH VIDEO COMPRESSOR - 75% RESOLUTION (480x270)")
    print("=" * 70)
    print(f"📁 Thu muc goc (AN TOAN - KHONG XOA): {input_dir}")
    print(f"📁 Thu muc dich (Output):              {output_dir}")
    print(f"📐 Do phan giai nen (75%):             {args.scale}")
    print(f"⚙️  Cau hinh encoder:                   h264_nvenc (preset={args.preset}, cq={args.cq})")
    print(f"📦 Tong so video can xu ly:            {len(videos)}")
    print("=" * 70)

    total_start = time.time()
    total_orig_bytes = 0
    total_comp_bytes = 0

    for idx, vpath in enumerate(videos, start=1):
        target_path = output_dir / vpath.name
        orig_size = vpath.stat().st_size
        total_orig_bytes += orig_size

        print(f"\n[{idx}/{len(videos)}] 🎞️  Dang xu ly: {vpath.name} ({format_size(orig_size)})")

        if target_path.exists() and not args.overwrite:
            comp_size = target_path.stat().st_size
            total_comp_bytes += comp_size
            ratio = (comp_size / orig_size) * 100 if orig_size > 0 else 0
            print(f"    ⏭️  Da ton tai ({format_size(comp_size)}, {ratio:.1f}% goc). Bo qua (them --overwrite de nen lai).")
            continue

        temp_target = output_dir / f".tmp_{vpath.name}"
        if temp_target.exists():
            temp_target.unlink()

        # Build ffmpeg command
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-stats",
            "-y",
            "-i", str(vpath),
            "-vf", f"scale={args.scale}",
            "-c:v", "h264_nvenc",
            "-preset", args.preset,
            "-cq", str(args.cq),
            "-c:a", "copy",
            str(temp_target),
        ]

        t0 = time.time()
        try:
            ret = subprocess.run(cmd)
            if ret.returncode != 0:
                print(f"    ❌ Loi khi nen {vpath.name} (exit code: {ret.returncode})")
                if temp_target.exists():
                    temp_target.unlink()
                continue

            # Rename temp to final target
            if temp_target.exists():
                if target_path.exists():
                    target_path.unlink()
                temp_target.rename(target_path)

            elapsed = time.time() - t0
            comp_size = target_path.stat().st_size
            total_comp_bytes += comp_size
            ratio = (comp_size / orig_size) * 100 if orig_size > 0 else 0
            saved = ((orig_size - comp_size) / orig_size) * 100 if orig_size > 0 else 0

            print(f"    ✅ Hoan tat trong {elapsed:.1f}s | Dung luong: {format_size(comp_size)} ({ratio:.1f}% goc, giam {saved:.1f}%)")

        except KeyboardInterrupt:
            print("\n[!] Da huy tien trinh (Ctrl+C). Don dep file tam...")
            if temp_target.exists():
                temp_target.unlink()
            sys.exit(0)
        except Exception as e:
            print(f"    ❌ Ngoai le: {e}")
            if temp_target.exists():
                temp_target.unlink()

    total_time = time.time() - total_start
    print("\n" + "=" * 70)
    print("🎉 HOAN TAT TAT CA VIDEO (75% RESOLUTION)!")
    print(f"⏱️  Tong thoi gian:     {total_time/60:.2f} phut")
    print(f"📊 Dung luong goc:       {format_size(total_orig_bytes)}")
    print(f"📊 Dung luong sau nen:   {format_size(total_comp_bytes)}")
    if total_orig_bytes > 0:
        saved_mb = total_orig_bytes - total_comp_bytes
        saved_pct = (saved_mb / total_orig_bytes) * 100
        print(f"💾 Tiet kiem duoc:       {format_size(saved_mb)} ({saved_pct:.1f}%)")
    print(f"📂 Thu muc video nen 75%: {output_dir}")
    print("=" * 70)

if __name__ == "__main__":
    main()
