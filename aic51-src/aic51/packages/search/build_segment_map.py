import json
import numpy as np
from pathlib import Path
from pymilvus import MilvusClient

KEYFRAMES_DIR = Path("aic51-src/workspace/data/keyframes")
COLLECTION = "milvus"
MODEL_FIELD = "image_clip_pe_l_14_336"
OUT = "segment_map.json"

# Keyframe mỗi 2 giây
KF_INTERVAL_SEC = 2

# CLIP similarity smoothing
K = 5

# Lấy 5% điểm similarity thấp nhất làm candidate boundary
Q = 0.05

# Hai boundary cách nhau < 10s thì coi là quá gần
MIN_GAP_SEC = 5
MIN_GAP_FRAMES = MIN_GAP_SEC // KF_INTERVAL_SEC


client = MilvusClient(uri="http://localhost:19530")
segment_map = {}

for video_dir in sorted(KEYFRAMES_DIR.iterdir()):
    if not video_dir.is_dir():
        continue

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

    # --------------------------------------------------
    # 5. Adaptive threshold
    # --------------------------------------------------
    thr = np.quantile(smooth, Q)

    # Những frame có similarity thấp → candidate boundary
    candidates = np.where(smooth < thr)[0]

    # --------------------------------------------------
    # 6. Merge boundaries quá gần nhau
    #
    # Ví dụ:
    #
    # 20s
    # 22s
    # 24s
    #
    # → chỉ giữ boundary mạnh nhất
    # --------------------------------------------------
    boundaries = []

    for b in candidates:

        if not boundaries:
            boundaries.append(b)
            continue

        prev = boundaries[-1]

        if b - prev < MIN_GAP_FRAMES:
            # Hai boundary quá gần nhau.
            # Giữ boundary có similarity thấp hơn
            # (= visual change mạnh hơn)
            if smooth[b] < smooth[prev]:
                boundaries[-1] = b

        else:
            boundaries.append(b)

    boundaries = np.array(
        boundaries,
        dtype=np.int32
    )

    # --------------------------------------------------
    # 7. Convert boundaries → segment IDs
    # --------------------------------------------------
    segs = np.zeros(
        len(fids),
        dtype=np.int32
    )

    for b in boundaries:
        segs[b + 1:] += 1

    segs = segs.tolist()

    nseg = (
        int(segs[-1]) + 1
        if segs
        else 0
    )

    # --------------------------------------------------
    # 8. Save
    # --------------------------------------------------
    segment_map[vid] = {
        "fids": fids,
        "segs": segs,
    }

    print(
        f"{vid}: "
        f"{len(fids)} kf → "
        f"{nseg} segments | "
        f"threshold={thr:.3f} | "
        f"min_gap={MIN_GAP_SEC}s"
    )


with open(OUT, "w") as f:
    json.dump(segment_map, f)

print(f"DONE → {OUT}")