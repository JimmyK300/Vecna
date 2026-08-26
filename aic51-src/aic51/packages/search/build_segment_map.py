import os
import json
from pathlib import Path
import numpy as np
from pymilvus import MilvusClient

# Resolve keyframes directory dynamically for Windows / Linux / macOS
SCRIPT_DIR = Path(__file__).resolve().parent
# search (0) -> packages (1) -> aic51 (2) -> aic51-src (3) -> repo root (3 relative to SCRIPT_DIR)
REPO_ROOT = SCRIPT_DIR.parents[3]

def find_keyframes_dir() -> Path:
    env_dir = os.environ.get("KEYFRAMES_DIR")
    if env_dir:
        return Path(env_dir)
    
    candidates = [
        REPO_ROOT / "workspace" / "data" / "keyframes",
        Path("workspace/data/keyframes"),
        Path("data/keyframes"),
        REPO_ROOT / "data" / "keyframes",
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate.resolve()
            
    return candidates[0]

KEYFRAMES_DIR = find_keyframes_dir()
MILVUS_URI = os.environ.get("MILVUS_URI", "http://localhost:19530")
COLLECTION = "milvus"
MODEL_FIELD = "image_clip_pe_l_14_336"
OUT = Path(os.environ.get("SEGMENT_MAP_OUT", "segment_map.json"))

# Keyframe mỗi 2 giây
KF_INTERVAL_SEC = 2

# CLIP similarity smoothing
K = 5

# Lấy 5% điểm similarity thấp nhất làm candidate boundary
Q = 0.05

# Hai boundary cách nhau < 10s thì coi là quá gần
MIN_GAP_SEC = 5
MIN_GAP_FRAMES = MIN_GAP_SEC // KF_INTERVAL_SEC


if not KEYFRAMES_DIR.is_dir():
    raise FileNotFoundError(f"Keyframes directory not found: {KEYFRAMES_DIR}")

print(f"Using KEYFRAMES_DIR: {KEYFRAMES_DIR}")

client = MilvusClient(uri=MILVUS_URI)
segment_map = {}

for video_dir in sorted(KEYFRAMES_DIR.iterdir()):
    vid = video_dir.name

    rows = client.query(
        collection_name=COLLECTION,
        filter=f'frame_id like "{vid}#%"',
        output_fields=["frame_id", MODEL_FIELD],
        limit=16384,
    )

    if len(rows) < 10:
        continue

    # --------------------------------------------------
    # 1. Sort frames
    # --------------------------------------------------
    rows.sort(
        key=lambda r: int(r["frame_id"].split("#")[1])
    )

    fids = [
        int(r["frame_id"].split("#")[1])
        for r in rows
    ]

    # --------------------------------------------------
    # 2. Normalize CLIP embeddings
    # --------------------------------------------------
    F = np.array(
        [r[MODEL_FIELD] for r in rows],
        dtype=np.float32
    )

    F /= (
        np.linalg.norm(F, axis=1, keepdims=True)
        + 1e-9
    )

    # --------------------------------------------------
    # 3. Similarity giữa 2 frame liên tiếp
    # --------------------------------------------------
    sims = (F[:-1] * F[1:]).sum(axis=1)

    # --------------------------------------------------
    # 4. Smooth để giảm noise
    # --------------------------------------------------
    pad = np.pad(
        sims,
        (K // 2, K // 2),
        mode="edge"
    )

    smooth = np.convolve(
        pad,
        np.ones(K) / K,
        mode="valid"
    )

    # Auto-select threshold: thử 3 giá trị, chọn cái cho nseg hợp lý
    candidates = []
    for abs_floor in [0.35, 0.55, 0.75]:
        thr = min(np.quantile(smooth, Q), abs_floor)
        nseg = int((smooth < thr).sum()) + 1
        candidates.append((abs_floor, thr, nseg))

    # Chọn candidate có nseg gần nhất với kỳ vọng (1 seg per 60s)
    duration_min = len(fids) * 2 / 60  # mỗi kf 2s
    target_segs = max(1, int(duration_min))  # kỳ vọng ~1 seg/phút
    best = min(candidates, key=lambda c: abs(c[2] - target_segs))

    abs_floor, thr, nseg = best
    segs = np.concatenate([[0], np.cumsum((smooth < thr).astype(int))]).tolist()

    segment_map[vid] = {"fids": fids, "segs": segs}
    print(f"{vid}: {len(fids)} kf → {nseg} segs (threshold={thr:.3f})")

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(segment_map, f, indent=2)

print(f"DONE → {OUT.resolve()}")