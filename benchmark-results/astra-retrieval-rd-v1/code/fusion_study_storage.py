#!/usr/bin/env python3
"""Losslessly reconstruct frozen fusion study bytes with a tiny timing sidecar.

Only fusion_wall_ns and fusion_cpu_ns vary during deterministic offline replay.
No model, database or truth is read by this storage operation.
"""
from __future__ import annotations
import argparse
import copy
import json
import platform
import sys
import tempfile
from pathlib import Path
from fusion_study import ARMS, ContractError, digest_bytes, run as transform_run

SCHEMA = "vecna82-fusion-study-timing-sidecar-v1"
FIELDS = ("fusion_wall_ns", "fusion_cpu_ns")


def require(condition, message):
    if not condition:
        raise ContractError(message)


def serialized(rows):
    return "".join(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in rows).encode("utf-8")


def timing_rows(rows):
    result = []
    for row in rows:
        require(list(row["arms"]) == list(ARMS), "source study arm order differs")
        values = []
        for arm in ARMS:
            pair = [row["arms"][arm][field] for field in FIELDS]
            require(all(type(value) is int and value >= 0 for value in pair), "timings must be nonnegative integers")
            values.append(pair)
        result.append([row["query_id"], values])
    return result


def restore_timing_bytes(replayed, saved_timings, expected_bytes, expected_sha256):
    require(len(replayed) == len(saved_timings), "timing row count differs")
    require(len({row["query_id"] for row in replayed}) == len(replayed), "duplicate replay query")
    output = copy.deepcopy(replayed)
    for row, saved in zip(output, saved_timings):
        require(isinstance(saved, list) and len(saved) == 2 and saved[0] == row["query_id"], "timing query identity/order differs")
        require(list(row["arms"]) == list(ARMS), "replayed arm order differs")
        pairs = saved[1]
        require(isinstance(pairs, list) and len(pairs) == len(ARMS), "timing arm count differs")
        for arm, pair in zip(ARMS, pairs):
            require(isinstance(pair, list) and len(pair) == 2 and all(type(value) is int and value >= 0 for value in pair), "timings must be nonnegative integer pairs")
            require(all(field in row["arms"][arm] for field in FIELDS), "replayed timing field is absent")
            for field, value in zip(FIELDS, pair):
                row["arms"][arm][field] = value
    raw = serialized(output)
    require(len(raw) == expected_bytes and digest_bytes(raw) == expected_sha256,
            "restored study is not byte-exact; preserve source evidence and use the declared original runtime, never relax this gate")
    return raw


def replay_inputs(args):
    with tempfile.TemporaryDirectory(prefix="vecna82-study-byte-replay-") as directory:
        output = Path(directory) / "fresh.jsonl"
        proof = transform_run(args.rankings, args.config, args.queries, output, args.collection_manifest)
        require(proof["queries"] == 115, "storage requires all115 frozen queries")
        rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines() if line.strip()]
    proof.pop("output_sha256")
    proof["config_file_sha256"] = digest_bytes(args.config.read_bytes())
    return rows, proof


def write_new(path, data):
    require(not path.exists(), "output already exists: " + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        with path.open("xb") as handle:
            created = True
            handle.write(data)
    except BaseException:
        if created:
            path.unlink(missing_ok=True)
        raise


def freeze(args):
    require(not args.sidecar.exists() and not args.proof.exists(), "freeze output exists")
    source = args.study.read_bytes()
    source_rows = [json.loads(line) for line in source.decode("utf-8").splitlines() if line.strip()]
    require(serialized(source_rows) == source, "source study does not use the frozen LF/JSON serialization")
    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    source_sha = digest_bytes(source)
    require(summary["transform_proof"]["output_sha256"] == source_sha, "summary/source-study hash mismatch")
    replayed, input_proof = replay_inputs(args)
    require(all(summary["transform_proof"].get(key) == value for key, value in input_proof.items() if key != "config_file_sha256"), "summary/replay input proof differs")
    timings = timing_rows(source_rows)
    restored = restore_timing_bytes(replayed, timings, len(source), source_sha)
    require(restored == source, "exact study comparison failed")
    sidecar = {
        "schema": SCHEMA,
        "input_proof": input_proof,
        "arms": list(ARMS),
        "timing_fields": list(FIELDS),
        "study": {"bytes": len(source), "sha256": source_sha},
        "serialization": {"ensure_ascii": False, "allow_nan": False, "separators": "json.dumps default", "sort_keys": False, "newline": "LF after every row"},
        "original_runtime": {"python": sys.version, "platform": platform.platform()},
        "timings": timings,
    }
    encoded = (json.dumps(sidecar, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n").encode("utf-8")
    proof = {
        "schema": "vecna82-study-exact-reconstruction-proof-v1",
        "status": "verified", "queries": 115, "arms": len(ARMS),
        "new_model_or_retrieval_calls": False, "ground_truth_read": False,
        "restored_fields_only": list(FIELDS),
        "source_study": sidecar["study"],
        "sidecar": {"bytes": len(encoded), "sha256": digest_bytes(encoded)},
        "reconstructed_bytes_equal_original": True,
        "input_proof": input_proof,
        "helper_sha256": digest_bytes(Path(__file__).read_bytes()),
        "runtime_qualification": "Exact byte proof was run on the recorded runtime. Platform/libm differences must fail the full SHA gate; use the recorded runtime for exact reconstruction.",
    }
    write_new(args.sidecar, encoded)
    write_new(args.proof, (json.dumps(proof, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))
    return proof


def rebuild(args):
    require(not args.output.exists(), "rebuild output exists")
    sidecar_bytes = args.sidecar.read_bytes()
    if args.sidecar_sha256:
        require(digest_bytes(sidecar_bytes) == args.sidecar_sha256, "timing sidecar SHA256 differs")
    sidecar = json.loads(sidecar_bytes)
    require(sidecar["schema"] == SCHEMA and sidecar["arms"] == list(ARMS) and sidecar["timing_fields"] == list(FIELDS), "unknown sidecar contract")
    replayed, input_proof = replay_inputs(args)
    require(input_proof == sidecar["input_proof"], "replay source/input identity differs")
    raw = restore_timing_bytes(replayed, sidecar["timings"], sidecar["study"]["bytes"], sidecar["study"]["sha256"])
    write_new(args.output, raw)
    return {"status": "verified", "study": sidecar["study"], "queries": 115, "new_model_or_retrieval_calls": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("freeze", "rebuild"))
    for name in ("rankings", "config", "queries", "collection-manifest", "sidecar"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--study", type=Path)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--proof", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--sidecar-sha256")
    args = parser.parse_args()
    if args.operation == "freeze":
        require(all((args.study, args.summary, args.proof)), "freeze requires study, summary and proof paths")
        result = freeze(args)
    else:
        require(args.output is not None, "rebuild requires an output path")
        result = rebuild(args)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
