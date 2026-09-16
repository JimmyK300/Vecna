#!/usr/bin/env python3
"""Freeze dense diagnostic config from verified host cache metadata only."""
import argparse
import json
from pathlib import Path, PureWindowsPath

from collect_dense_visibility import TEXT_EMBEDDING_SHA256
from collect_sparse_visibility import digest, dump


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    probe_path = root / "outputs/source-visibility/dense-identity-v1.json"
    probe = json.loads(probe_path.read_text(encoding="utf-8"))
    transport = json.loads((root / "inputs/dense_visibility_identity_transport.json").read_text(encoding="utf-8"))
    if digest(probe_path.read_bytes()) != transport["recovered_sha256"]:
        raise ValueError("Host cache probe checksum differs")
    refs = [r for r in probe["cache"]["refs"] if PureWindowsPath(r["path"]).name == "main"]
    if len(refs) != 1:
        raise ValueError("Ambiguous cached main revision")
    revision = refs[0]["revision"]
    snapshots = [s for s in probe["cache"]["snapshots"] if s["revision"] == revision]
    if len(snapshots) != 1:
        raise ValueError("Cached main snapshot missing or ambiguous")
    snapshot = snapshots[0]
    files = {PureWindowsPath(f["path"]).name: f for f in snapshot["files"]}
    if len(files) != snapshot["top_level_file_count"]:
        raise ValueError("Cache probe file listing was truncated")
    model_config = files["config.json"]["json"]
    if model_config["model_type"] != "xlm-roberta" or model_config["hidden_size"] != 1024 or model_config["architectures"] != ["XLMRobertaModel"]:
        raise ValueError("Unexpected BGE-M3 architecture")
    config_model = probe["configuration"][0]["projection"]["text_bge_m3"]
    if config_model["pretrained_model"] != "BAAI/bge-m3" or config_model["backend"] != "pytorch" or set(config_model["target"]) != {"ocr_dense", "asr_dense"}:
        raise ValueError("Observed main BGE model declaration differs")
    source = next(s for s in probe["vecna_sources"] if s["repository_path"].endswith("text_embedding.py"))
    if source["lf_sha256"] != TEXT_EMBEDDING_SHA256:
        raise ValueError("Observed BGE implementation differs from pinned main")
    use_safe = "model.safetensors" in files
    weights = "model.safetensors" if use_safe else "pytorch_model.bin"
    required = {"config.json", "tokenizer_config.json", "special_tokens_map.json", "tokenizer.json", "sentencepiece.bpe.model", weights}
    if not required.issubset(files):
        raise ValueError("Observed main snapshot lacks complete model/tokenizer assets")
    selected = []
    for name in sorted(required):
        f = files[name]
        entry = {"relative_path": name, "bytes": f["bytes"], "mtime_ns": f["mtime_ns"]}
        if f.get("sha256"):
            entry["sha256"] = f["sha256"]
            entry["digest_pin_scope"] = "checksum_verified_against_identity_probe"
        else:
            # Windows cache stores regular files, not content-addressed links.
            # Hash every byte before allocating/loading the model or querying.
            entry["digest_pin_scope"] = "metadata_frozen_before_run_sha256_frozen_before_model_loading"
        selected.append(entry)
    sparse = json.loads((root / "outputs/source-visibility/sparse_config.json").read_text(encoding="utf-8"))
    config = {"schema": "vecna82-dense-visibility-config-v1", "status": "identity_pinned_ready", "provider_depth": 100,
              "query_file_sha256": sparse["query_file_sha256"], "query_projection_sha256": sparse["query_projection_sha256"],
              "frozen_sample_sha256": sparse["frozen_sample_sha256"], "collection": sparse["collection"],
              "main_commit": sparse["main_commit"], "searcher_lf_sha256": sparse["searcher_lf_sha256"],
              "text_embedding_lf_sha256": TEXT_EMBEDDING_SHA256,
              "cache_probe_sha256": digest(probe_path.read_bytes()), "cache_probe_transport": transport,
              "model": {"repository": "BAAI/bge-m3", "snapshot_revision": revision, "snapshot_path": snapshot["path"],
                        "backend": "pytorch", "device": "cpu", "dtype": "float32", "max_length": 1024,
                        "use_safetensors": use_safe, "checkpoint_file": weights,
                        "snapshot_top_level_files": sorted(files), "files": selected,
                        "pin_limit": "Small config/tokenizer metadata files have pre-run SHA256 pins. The Windows cache's regular weight/vocabulary files have revision/size/mtime pins; their full SHA256 is frozen before any model loading or retrieval and their stats rechecked after loading. This is current cached identity, not historical corpus extraction identity.",
                        "checkpoint_choice": "Use the complete snapshot referenced by cached refs/main; do not mix the separate safetensors-only snapshot or perform automatic conversion/download."},
              "metric": "COSINE", "nprobe": 32, "server_filter": "", "offset": 0,
              "index_registry_paths": ["D:/Official-Dataset/provenance/indexes/official_l21_l30_all_v2.json", "D:/Official-Dataset/features_L21-L30_branch-feats-siglip/provenance/indexes/official_l21_l30_all_v2.json"],
              "index_generation_identity": {"state": "not_established_by_available_probe", "interpretation": "Collection schema/index metadata are pinned; historical stored-vector encoder/index generation remains unresolved unless the existing index registry provides an actual generation chain. Target absence is only absence from this dense field's retained100 under the declared current encoder."},
              "effective_semantics": "Execute exact pinned main dense-only text path alpha1, CLS/L2 PyTorch float32 CPU query encoder,1024 tokens,one canonical formulation; native quote/filter/1.5boost/max normalization; raw top100 cap with requested native200/500 recorded.",
              "forbidden_capture_inputs": ["truth", "accepted_video", "accepted_frame", "answer", "query_rewrite", "retrieval_outcome"],
              "scope": "Dataset #17 dense visibility diagnostic only. No fusion weights changed, production promotion, model downloads, visual models, collection writes or source repairs."}
    path = root / "outputs/source-visibility/dense_config.json"
    dump(path, config)
    print(json.dumps({"config": str(path.relative_to(root)), "sha256": digest(path.read_bytes()), "snapshot_revision": revision, "checkpoint": weights, "consumed_files": len(selected)}, indent=2))


if __name__ == "__main__":
    main()
