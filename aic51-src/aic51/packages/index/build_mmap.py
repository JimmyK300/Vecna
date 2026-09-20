"""Streaming parallel builder for Vecna numpy.mmap vector indices.
Pre-allocates memory-mapped matrices on disk and streams shards directly
from multiple worker threads without accumulating large vectors in RAM.
"""

import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import time
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from tqdm import tqdm


def process_and_write_video(
    task: tuple[int, int, str, list[str]],
    clip_mmap,
    siglip_mmap,
    qwen_mmap,
    frame_ids_arr,
    video_ids_arr,
):
    """Worker function: reads features for one video, normalizes, and writes directly into mmap slice."""
    start_idx, end_idx, video_id, frame_paths = task
    
    clip_list = []
    siglip_list = []
    qwen_list = []
    records = []
    
    for fpath in frame_paths:
        frame_name = os.path.basename(fpath)
        fid_num = int(frame_name) if frame_name.isdigit() else 0
        frame_id = f"{video_id}#{frame_name}"
        
        # 1. CLIP (1024-d)
        clip_p = os.path.join(fpath, "image_clip_pe-l-14-336.npy")
        if not os.path.exists(clip_p):
            continue
        try:
            cvec = np.load(clip_p).astype(np.float32)
        except Exception:
            continue
            
        # 2. SigLIP (1152-d)
        siglip_p = os.path.join(fpath, "image_siglip_so400m-384.npy")
        svec = None
        if os.path.exists(siglip_p):
            try:
                svec = np.load(siglip_p).astype(np.float32)
            except Exception:
                pass
        if svec is None:
            svec = np.zeros(1152, dtype=np.float32)
            
        # 3. Qwen-VL (2048-d)
        qwen_p = os.path.join(fpath, "qwen_vl.npy")
        qvec = None
        if os.path.exists(qwen_p):
            try:
                qvec = np.load(qwen_p).astype(np.float32)
            except Exception:
                pass
        if qvec is None:
            qvec = np.zeros(2048, dtype=np.float32)
            
        # 4. OCR
        ocr_text = ""
        ocr_p = os.path.join(fpath, "ocr.npy")
        if os.path.exists(ocr_p):
            try:
                ov = np.load(ocr_p, allow_pickle=True)
                ocr_text = str(ov).strip() if ov is not None else ""
            except Exception:
                pass
                
        # 5. ASR
        asr_text = ""
        asr_p = os.path.join(fpath, "asr.npy")
        if os.path.exists(asr_p):
            try:
                av = np.load(asr_p, allow_pickle=True)
                asr_text = str(av).strip() if av is not None else ""
            except Exception:
                pass
                
        pts_time = round(fid_num / 30.0, 3)
        clip_list.append(cvec)
        siglip_list.append(svec)
        qwen_list.append(qvec)
        records.append({
            "frame_id": frame_id,
            "video_id": video_id,
            "frame_idx": fid_num,
            "pts_time": pts_time,
            "ocr": ocr_text,
            "asr": asr_text,
        })
        
    actual_count = len(records)
    if actual_count > 0:
        slice_end = start_idx + actual_count
        
        # 1. Normalize and write CLIP
        c_mat = np.stack(clip_list).astype(np.float32)
        c_norms = np.linalg.norm(c_mat, axis=1, keepdims=True)
        c_norms[c_norms == 0] = 1.0
        c_mat /= c_norms
        clip_mmap[start_idx:slice_end] = c_mat
        
        # 2. Normalize and write SigLIP
        s_mat = np.stack(siglip_list).astype(np.float32)
        s_norms = np.linalg.norm(s_mat, axis=1, keepdims=True)
        s_norms[s_norms == 0] = 1.0
        s_mat /= s_norms
        siglip_mmap[start_idx:slice_end] = s_mat
        
        # 3. Normalize and write Qwen
        q_mat = np.stack(qwen_list).astype(np.float32)
        q_norms = np.linalg.norm(q_mat, axis=1, keepdims=True)
        q_norms[q_norms == 0] = 1.0
        q_mat /= q_norms
        qwen_mmap[start_idx:slice_end] = q_mat
        
        # 4. Lookup arrays
        frame_ids_arr[start_idx:slice_end] = [r["frame_id"] for r in records]
        video_ids_arr[start_idx:slice_end] = video_id
        
    return actual_count, records


def build_mmap_index(
    features_dir: Path,
    output_dir: Path,
    collections: list[str] | None = None,
    num_workers: int = 32,
):
    output_dir.mkdir(parents=True, exist_ok=True)
    features_dir_str = str(features_dir)
    
    print(f"=== FAST PARALLEL MMAP BUILDER FOR VECNA ===")
    print(f"Features directory: {features_dir}")
    print(f"Target output directory: {output_dir}")
    print(f"Worker threads: {num_workers}")
    if collections:
        print(f"Filtering collections: {collections}")
    else:
        print("Processing: ALL collections")
        
    t0 = time.time()
    print("\n[Phase 1/3] Fast scanning videos and frame directories...")
    with os.scandir(features_dir_str) as it:
        all_video_entries = [e for e in it if e.is_dir()]
        
    if collections:
        video_entries = [e for e in all_video_entries if any(e.name.startswith(c + "_") for c in collections)]
    else:
        video_entries = all_video_entries
        
    video_entries.sort(key=lambda e: e.name)
    print(f"Found {len(video_entries)} videos to process.")
    
    # Pre-scan frames per video to determine exact shape and offsets
    tasks = []
    total_frames = 0
    for ve in video_entries:
        with os.scandir(ve.path) as fit:
            fdirs = [f.path for f in fit if f.is_dir()]
        fdirs.sort(key=lambda p: int(os.path.basename(p)) if os.path.basename(p).isdigit() else os.path.basename(p))
        n_frames = len(fdirs)
        if n_frames > 0:
            start_idx = total_frames
            end_idx = total_frames + n_frames
            tasks.append((start_idx, end_idx, ve.name, fdirs))
            total_frames += n_frames
            
    scan_time = time.time() - t0
    print(f"Scanning completed: {total_frames:,} total frames in {scan_time:.2f}s")
    if total_frames == 0:
        print("No valid frames found.")
        return

    print("\n[Phase 2/3] Pre-allocating zero-copy memmap matrices on disk...")
    clip_path = output_dir / "image_clip_pe_l_14_336.npy"
    siglip_path = output_dir / "image_siglip_so400m_384.npy"
    qwen_path = output_dir / "qwen_vl.npy"
    
    clip_mmap = np.lib.format.open_memmap(clip_path, mode="w+", dtype=np.float32, shape=(total_frames, 1024))
    siglip_mmap = np.lib.format.open_memmap(siglip_path, mode="w+", dtype=np.float32, shape=(total_frames, 1152))
    qwen_mmap = np.lib.format.open_memmap(qwen_path, mode="w+", dtype=np.float32, shape=(total_frames, 2048))
    
    frame_ids_arr = np.empty(total_frames, dtype=object)
    video_ids_arr = np.empty(total_frames, dtype=object)
    
    print(f"  - Pre-allocated CLIP:   {clip_path.name} ({clip_path.stat().st_size / (1024*1024):.1f} MB)")
    print(f"  - Pre-allocated SigLIP: {siglip_path.name} ({siglip_path.stat().st_size / (1024*1024):.1f} MB)")
    print(f"  - Pre-allocated Qwen:   {qwen_path.name} ({qwen_path.stat().st_size / (1024*1024):.1f} MB)")

    print(f"\n[Phase 3/3] Streaming features from {len(tasks)} videos ({num_workers} threads)...")
    all_records = []
    actual_written = 0
    
    def worker_wrapper(task):
        return process_and_write_video(
            task,
            clip_mmap,
            siglip_mmap,
            qwen_mmap,
            frame_ids_arr,
            video_ids_arr,
        )
        
    t_stream = time.time()
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        for written, recs in tqdm(
            executor.map(worker_wrapper, tasks),
            total=len(tasks),
            desc="Indexing videos",
            unit="vid",
            ncols=90,
        ):
            actual_written += written
            all_records.extend(recs)
            
    print(f"\nFlushing memory-mapped arrays to disk...")
    clip_mmap.flush()
    siglip_mmap.flush()
    qwen_mmap.flush()
    del clip_mmap, siglip_mmap, qwen_mmap
    
    # If any frame was skipped (e.g. missing clip), trim arrays
    if actual_written < total_frames:
        print(f"Notice: written {actual_written:,} of {total_frames:,} (trimmed {total_frames - actual_written:,} missing frames)")
        frame_ids_arr = frame_ids_arr[:actual_written]
        video_ids_arr = video_ids_arr[:actual_written]
        
    print(f"Saving frame_ids.npy and video_ids.npy...")
    np.save(output_dir / "frame_ids.npy", frame_ids_arr)
    np.save(output_dir / "video_ids.npy", video_ids_arr)
    del frame_ids_arr, video_ids_arr
    
    print(f"Saving metadata.json ({actual_written:,} records)...")
    with open(output_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(all_records, f, ensure_ascii=False)
    del all_records
    
    total_time = time.time() - t0
    print(f"\n========================================================")
    print(f"SUCCESS! {actual_written:,} FRAMES INDEXED IN {total_time:.2f}s ({actual_written / total_time:.0f} frames/s)")
    print(f"Output files in {output_dir}:")
    for p in sorted(output_dir.iterdir()):
        print(f"  - {p.name:<32} ({p.stat().st_size / (1024*1024):.2f} MB)")
    print(f"========================================================\n")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Build streaming numpy.mmap indices for Vecna")
    parser.add_argument("--collections", nargs="+", default=None, help="Filter collections e.g. L21 L22 (default: all)")
    parser.add_argument("--all", action="store_true", help="Build all collections")
    parser.add_argument("--features-dir", type=str, default="E:/Projects/Vecna/workspace/features", help="Path to workspace/features")
    parser.add_argument("--output-dir", type=str, default="E:/Projects/Vecna/workspace/mmap_indices", help="Path to output mmap_indices")
    parser.add_argument("--workers", type=int, default=32, help="Thread count (default: 32)")
    args = parser.parse_args()
    
    colls = None if args.all else args.collections
    build_mmap_index(
        features_dir=Path(args.features_dir),
        output_dir=Path(args.output_dir),
        collections=colls,
        num_workers=args.workers,
    )


if __name__ == "__main__":
    main()
