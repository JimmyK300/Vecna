import json
import numpy as np
from pathlib import Path
from pymilvus import MilvusClient

KEYFRAMES_DIR = Path("aic51-src/workspace/data/keyframes")
COLLECTION = "milvus"
MODEL_FIELD = "image_clip_pe_l_14_336"
OUT = "segment_map.json"

K, Q = 5, 0.05

client = MilvusClient(uri="http://localhost:19530")
segment_map = {}

for video_dir in sorted(KEYFRAMES_DIR.iterdir()):
    vid = video_dir.name
    rows = client.query(collection_name=COLLECTION,
                        filter=f'frame_id like "{vid}#%"',
                        output_fields=["frame_id", MODEL_FIELD], limit=16384)
    if len(rows) < 10: continue

    rows.sort(key=lambda r: int(r["frame_id"].split("#")[1]))
    fids = [int(r["frame_id"].split("#")[1]) for r in rows]
    F = np.array([r[MODEL_FIELD] for r in rows], dtype=np.float32)
    F /= np.linalg.norm(F, axis=1, keepdims=True) + 1e-9
    sims = (F[:-1] * F[1:]).sum(axis=1)

    pad = np.pad(sims, (K//2, K//2), mode='edge')
    smooth = np.convolve(pad, np.ones(K)/K, mode='valid')

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

json.dump(segment_map, open(OUT, "w"))
print(f"DONE → {OUT}")