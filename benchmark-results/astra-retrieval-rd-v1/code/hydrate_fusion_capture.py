#!/usr/bin/env python3
"""Hydrate the exact saved B capture and optionally replay its model-free analysis."""
from __future__ import annotations
import argparse
import hashlib
import json
import lzma
import math
import subprocess
import sys
from pathlib import Path

ARCHIVE_REL = "outputs/fusion/recovery-evaluation-v1/archives/provider_rankings.jsonl.xz"
RAW_REL = "outputs/fusion/capture-full115-v1/provider_rankings.jsonl"
ARCHIVE = (1699128, "b793108e648605d413f8fd8d061fa6029f2a5e3b5a1c884f62e55849f004443f")
RAW = (27146363, "d6223381ea8cbf4b4efcb0cc295f60dccfcae36afe0d9fac004438410c152a82")
RUN_ID = "f0d32893564111064d47f6f2f72f7b03dbb14ebbfbb3d05c48e49e30ef165755"
PINNED = {
    "code/fusion_study.py": "57ded10b78c0a6649008d15e61882e3b52d2eb0b5cf63b57a7133a6a9da2a292",
    "code/evaluate_fusion_study.py": "faef438a265ef61c6dc17a3221b0d6497efaadae6772bcba27a77dfa9e613f7b",
    "code/analyze_reranker.py": "2b9b2624fda6582c1ba894ecb8ec39e90b27d9d6258f8c75676773bb36bd2bb1",
    "outputs/fusion/frozen_config.json": "ff7a6f817579a2ba65572734016d51164f454a9d5012177841a458bbdca34b1a",
    "outputs/fusion/queries.jsonl": "3b91dfe26a893192a497a964d3a9ea5f50c595fdaabad000cbc60fc602be0d1a",
    "outputs/fusion/capture-full115-v1/collection_manifest.json": "01333a2ce910605b537a90aa6897938103aaf1728048d216af350d26bde756d8",
    "outputs/fusion/evaluation/compact_per_query.json": "ef360ed383421baa8c6dfb7e280db6f01139888714e65737f318517beac260b9",
}

def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_bytes(data, expected, label):
    require((len(data), sha(data)) == expected, label + " byte count or SHA256 differs")


def hydrate(archive, target, archive_identity=ARCHIVE, raw_identity=RAW):
    packed = archive.read_bytes()
    verify_bytes(packed, archive_identity, "compressed capture")
    if target.exists():
        verify_bytes(target.read_bytes(), raw_identity, "existing raw capture")
        return {"created": False, "bytes": raw_identity[0], "sha256": raw_identity[1]}
    raw = lzma.decompress(packed, format=lzma.FORMAT_XZ)
    verify_bytes(raw, raw_identity, "decompressed capture")
    target.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        with target.open("xb") as handle:
            created = True
            handle.write(raw)
    except BaseException:
        if created:
            target.unlink(missing_ok=True)
        raise
    verify_bytes(target.read_bytes(), raw_identity, "written raw capture")
    return {"created": True, "bytes": raw_identity[0], "sha256": raw_identity[1]}


def verify_compact(root, outdir):
    compact = json.loads((root / "outputs/fusion/evaluation/compact_per_query.json").read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in (outdir / "per_query.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    actual = {row["query_id"]: row for row in rows}
    expected = {row["query_id"]: row for row in compact["queries"]}
    require(len(rows) == len(actual) == len(expected) == 113 and set(actual) == set(expected), "replayed per-query cohort differs")
    require(compact["run_identity_sha256"] == RUN_ID, "compact reference identity differs")
    for qid, saved in expected.items():
        row = actual[qid]
        require(row["query_text_sha256"] == saved["query_text_sha256"] and row["run_identity_sha256"] == RUN_ID, "replayed query identity differs: " + qid)
        require(set(row["arms"]) == set(saved["arms"]), "replayed arm set differs: " + qid)
        for arm, baseline in saved["arms"].items():
            value = row["arms"][arm]
            mapping = {
                "distinct_video_rank": "distinct_video_rank_observed",
                "frame_position_video_rank": "frame_position_video_rank_observed",
                "frozen_rank": "frozen_rank_observed",
                "target_coverage_at100": "required_target_coverage_at_retained100",
                "all_targets_at100": "all_required_targets_at_retained100",
            }
            require(all(value[field] == baseline[key] for key, field in mapping.items()), "replayed retained rank/coverage differs: " + qid + "/" + arm)
            metrics = value["frozen_frame_range_event"]["metrics"]
            require(set(metrics) == set(baseline["frozen_metrics"]), "replayed metric set differs")
            require(all(math.isclose(metrics[key], number, rel_tol=0, abs_tol=1e-12) for key, number in baseline["frozen_metrics"].items()), "replayed frozen metric differs: " + qid + "/" + arm)
    summary = json.loads((outdir / "summary.json").read_text(encoding="utf-8"))
    proof = summary["transform_proof"]
    require(proof["output_sha256"] == sha((outdir / "study_results.jsonl").read_bytes()), "summary/study hash mismatch")
    require(proof["run_identity_sha256"] == RUN_ID and proof["rankings_sha256"] == RAW[1], "summary input identity mismatch")
    require(proof["queries"] == 115 and summary["cohort"] == {"collected": 115, "scored": 113, "excluded": ["p0_q15", "p3_q09"]}, "summary cohort differs")
    require(summary["descriptive_best_global_arm"] == "fusion_current_control", "global selection differs")
    return {"scored": 113, "arms": 6, "all_saved_ranks_coverage_and_frozen_metrics_match": True,
            "run_identity_sha256": RUN_ID, "new_study_sha256": proof["output_sha256"]}


def replay(root, rankings, outdir):
    require(not outdir.exists(), "replay output already exists; select a fresh path, preserving the committed snapshot")
    require(root == outdir or root in outdir.parents, "replay output must be inside research root")
    for name, expected in PINNED.items():
        require(sha((root / name).read_bytes()) == expected, "pinned LF source/input differs: " + name)
    command = [
        sys.executable, str(root / "code/evaluate_fusion_study.py"), "--root", str(root),
        "--rankings", str(rankings), "--collection-manifest", str(root / "outputs/fusion/capture-full115-v1/collection_manifest.json"),
        "--outdir", str(outdir),
    ]
    subprocess.run(command, check=True)
    return verify_compact(root, outdir)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--replay-outdir", type=Path, help="Fresh output path relative to research root, or an absolute path inside it.")
    args = parser.parse_args()
    root = args.root.resolve()
    result = {"capture": hydrate(root / ARCHIVE_REL, root / RAW_REL), "new_model_or_retrieval_calls": False}
    if args.replay_outdir:
        outdir = args.replay_outdir if args.replay_outdir.is_absolute() else root / args.replay_outdir
        result["replay"] = replay(root, root / RAW_REL, outdir.resolve())
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
