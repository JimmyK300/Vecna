#!/usr/bin/env python3
"""Recover and score the completed dense capture without loading any model.

Run only in a disposable research checkout. Reads a caller-supplied artifact ZIP
(or ephemeral URL), pinned Git objects, and the existing dataset Git checkout.
It never fetches a repository, reads credentials, changes the dataset checkout,
loads Torch/model weights, or calls Milvus. Publication JSON contains no URL.
"""
import argparse
import base64
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

PIN = "50984d58a8aa580ebde561718d4ef5504991a3a5"
PREFIX = "benchmark-results/astra-retrieval-rd-v1/"
EVALUATOR_SHA = "30df93590e50fd679e5e290b89869832b86d0fb08c5b6128e22f34d0f59c6f24"
ZIP_SHA = "bcf142605856e2a23e33b6dc47e05fb94f8119d902cbd234b7c7a3cde939dffa"
PATCH_SHA = "186b8bdcf04e2faa80b6743937ef9c81a627cbfa21598ca4cae991c253ff8d00"
FILES = {
    "outputs/source-visibility/dense-v1/collection_manifest.json": (148873, "80aae4cd4f77465df4c0f7b6eee27b10d365200dd06f3da0b4ca3980eb8e1695"),
    "outputs/source-visibility/dense-v1/dense_rankings.jsonl": (3342474, "097bc5f7680457d068fe075372f67dd03b17d2fac745d7e5a68a85f7195bcfc2"),
    "outputs/source-visibility/dense-v1/model_initialization.json": (132243, "3ea62eed2e66f40ae16a0048c1427dedc3ab50dcc6e78ce926063ef46be8d9bf"),
    "outputs/source-visibility/dense-supervision-v1/stderr.txt": (2059, "511b9bb553c9af644a84216240ba7fa99aff03c51124969f3df04b9b7c2b9a24"),
    "outputs/source-visibility/dense-supervision-v1/stdout.txt": (3078, "25e7d112612e504234a9daebe4b52f9218bd996643b6643bdc1ff2fd20eb8f97"),
    "outputs/source-visibility/dense-supervision-v1/supervision.json": (668, "14ceea7fb82b5e265c4987a03ff6d0f3b515cc699fa759197c2be5701af2cf8a"),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), "-c", "core.autocrlf=false", "-c", "core.eol=lf", *args], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def write_new_or_equal(path, data):
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError("Existing research output differs: " + str(path))
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as handle:
            handle.write(data)


def dump(path, value):
    data = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()
    write_new_or_equal(path, data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--dataset-repo", type=Path, required=True)
    transport = parser.add_mutually_exclusive_group(required=True)
    transport.add_argument("--artifact-zip", type=Path)
    transport.add_argument("--artifact-url", help="Ephemeral caller-provided download URL; not persisted or printed")
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    base = repo / PREFIX
    proof = base / "outputs/source-visibility/dense-offline-recovery-v1"
    proof.mkdir(parents=True, exist_ok=True)
    assert git(repo, "rev-parse", PIN + "^{commit}").decode().strip() == PIN
    assert git(args.dataset_repo, "rev-parse", "--is-inside-work-tree").decode().strip() == "true"
    dataset_before = (git(args.dataset_repo, "rev-parse", "HEAD"),
                      git(args.dataset_repo, "status", "--porcelain=v1", "--untracked-files=all"))

    # Git-show avoids Windows autocrlf changing any hash-pinned research inputs.
    restored = []
    listing = git(repo, "ls-tree", "-r", "--name-only", PIN, "--", PREFIX).decode().splitlines()
    for name in listing:
        if Path(name).suffix.lower() not in (".py", ".json", ".jsonl", ".md", ".txt", ".csv", ".tsv"):
            continue
        data = git(repo, "show", PIN + ":" + name)
        destination = repo / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        restored.append({"path": name, "bytes": len(data), "sha256": sha(data)})
    assert sha((base / "code/evaluate_dense_visibility.py").read_bytes()) == EVALUATOR_SHA
    assert sha((base / "code/collect_dense_visibility.py").read_bytes()) == "f4daac0debe0e33c043bd0a38e1dc722fe6d51283c0d370c0b171a03bda3938b"
    assert sha((base / "outputs/source-visibility/dense_config.json").read_bytes()) == "c50d1cc64cc0b5e62913343c9bb2329780314d1480d6e422603ba22a1dd33071"
    if args.artifact_zip:
        archive = args.artifact_zip.read_bytes()
    else:
        request = urllib.request.Request(args.artifact_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=90) as response:
            archive = response.read(430633)
    assert len(archive) == 430632 and sha(archive) == ZIP_SHA
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        assert sorted(bundle.namelist()) == ["changes.patch", "result.json"]
        patch = bundle.read("changes.patch").replace(b"\r\n", b"\n")
        broker = json.loads(bundle.read("result.json"))
    assert len(patch) == 3640437 and sha(patch) == PATCH_SHA
    pairs = re.findall(r"^diff --git a/(\S+) b/(\S+)$", patch.decode(), re.M)
    expected = {PREFIX + name for name in FILES}
    assert len(pairs) == 6 and {b for a, b in pairs} == expected and all(a == b for a, b in pairs)
    recovered = []
    with tempfile.TemporaryDirectory(prefix="dense-patch-", dir=proof) as temporary:
        temporary = Path(temporary)
        git(temporary, "init", "-q")
        patch_path = temporary / "capture.patch"
        patch_path.write_bytes(patch)
        git(temporary, "apply", "--check", str(patch_path))
        git(temporary, "apply", str(patch_path))
        for name, (length, checksum) in FILES.items():
            data = (temporary / PREFIX / name).read_bytes()
            note = "Git patch LF bytes"
            if name.endswith(("/stderr.txt", "/stdout.txt")) and sha(data) != checksum:
                data = data.replace(b"\n", b"\r\n")
                note = "Exact host CRLF reconstructed and verified against original supervisor hash"
            assert len(data) == length and sha(data) == checksum, name
            write_new_or_equal(base / name, data)
            recovered.append({"path": name, "bytes": length, "sha256": checksum, "newline_note": note})
    hydrated = subprocess.run([sys.executable, "-B", "code/dataset_text_audit.py",
                               "--root", ".", "--dataset-repo", str(args.dataset_repo.resolve()), "--hydrate-only"],
                              cwd=base, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
    write_new_or_equal(proof / "hydrate_stdout.txt", hydrated.stdout)
    write_new_or_equal(proof / "hydrate_stderr.txt", hydrated.stderr)
    if hydrated.returncode:
        raise RuntimeError("Source hydration failed: " + hydrated.stderr.decode(errors="replace")[-5000:])
    evaluated = subprocess.run([sys.executable, "-B", "code/evaluate_dense_visibility.py", "--root", "."],
                               cwd=base, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
    write_new_or_equal(proof / "evaluate_stdout.txt", evaluated.stdout)
    write_new_or_equal(proof / "evaluate_stderr.txt", evaluated.stderr)
    if evaluated.returncode:
        raise RuntimeError("Dense offline scoring failed: " + evaluated.stderr.decode(errors="replace")[-5000:])
    dataset_after = (git(args.dataset_repo, "rev-parse", "HEAD"),
                     git(args.dataset_repo, "status", "--porcelain=v1", "--untracked-files=all"))
    assert dataset_before == dataset_after, "Dataset checkout changed"
    out = base / "outputs/source-visibility/dense-evaluation-v1"
    evaluation = json.loads((out / "evaluation_manifest.json").read_text(encoding="utf-8"))
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert evaluation["status"] == "complete" and evaluation["evaluator_sha256"] == EVALUATOR_SHA
    assert evaluation["captured_rankings_sha256"] == FILES["outputs/source-visibility/dense-v1/dense_rankings.jsonl"][1]
    assert evaluation["sparse_comparison_rescored_from_verified_capture"] is True
    for name, checksum in evaluation["outputs"].items():
        assert sha((out / name).read_bytes()) == checksum
    rows = [json.loads(line) for line in (out / "dense_visibility.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == len({(row["channel"], row["query_id"]) for row in rows}) == 38
    model = evaluation["capture_manifest"]["model_identity"]
    params = model["checkpoint_parameter_audit"]
    assert params["active_parameter_tensor_count"] == 389 and params["active_parameter_elements"] == 566705152
    assert params["all_active_encoder_parameters_equal_cached_checkpoint"] is True
    assert all(not model["loading_info"].get(key) for key in ("missing_keys", "unexpected_keys", "mismatched_keys", "error_msgs"))
    # One model-free deterministic replay, without rewriting the first report.
    with tempfile.TemporaryDirectory(prefix="dense-score-replay-", dir=proof) as temporary:
        replay = subprocess.run([sys.executable, "-B", "code/evaluate_dense_visibility.py", "--root", ".", "--output-dir", temporary],
                                cwd=base, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
        assert replay.returncode == 0, replay.stderr.decode(errors="replace")[-5000:]
        for name in ("dense_visibility.jsonl", "summary.json", "DENSE_VISIBILITY.md", "evaluation_manifest.json"):
            assert (out / name).read_bytes() == (Path(temporary) / name).read_bytes(), name
    publication = []
    names = sorted(set(FILES) | {
        "outputs/source-visibility/dense-evaluation-v1/" + name
        for name in ("dense_visibility.jsonl", "summary.json", "DENSE_VISIBILITY.md", "evaluation_manifest.json")})
    for number, name in enumerate(names):
        raw = (base / name).read_bytes()
        packed = gzip.compress(raw, compresslevel=9, mtime=0)
        packed_name = f"publication-{number:02}.gz"
        write_new_or_equal(proof / packed_name, packed)
        publication.append({"path": PREFIX + name, "bytes": len(raw), "sha256": sha(raw),
                            "git_blob": hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest(),
                            "gzip_file": packed_name, "gzip_bytes": len(packed), "gzip_sha256": sha(packed)})
    transport_proof = {"schema": "vecna82-dense-offline-recovery-v1", "source_commit": PIN, "zip_sha256": ZIP_SHA,
                       "patch_sha256": PATCH_SHA, "recovered": recovered, "restored_text_count": len(restored),
                       "restored_text_sha256": sha(json.dumps(restored, sort_keys=True).encode()),
                       "dataset_checkout_modified": False, "model_or_retrieval_calls": 0,
                       "evaluation_replay_byte_identical_files": 4, "publication_files": publication,
                       "broker_result": broker}
    dump(proof / "recovery_manifest.json", transport_proof)
    # Small report bodies are directly publishable; large immutable artifacts are
    # retained as exact bytes plus deterministic gzip files for chunked transport.
    compact = {}
    for name in ("summary.json", "DENSE_VISIBILITY.md"):
        raw = (out / name).read_bytes()
        assert len(raw) < 14000
        compact[name] = {"sha256": sha(raw), "bytes": len(raw), "base64": base64.b64encode(raw).decode()}
    payload = {"status": "complete", "rows": 38, "model_or_retrieval_calls": 0,
                      "summary": summary, "source_commit": PIN, "evaluator_sha256": EVALUATOR_SHA,
                      "model_proof": {"revision": model["snapshot_revision"], "active_tensors": 389,
                                      "active_elements": 566705152, "loading_info": model["loading_info"]},
                      "runtime_versions": evaluation["capture_manifest"].get("packages"),
                      "byte_identical_replay_files": 4, "publication": publication, "compact": compact}
    output = json.dumps(payload, ensure_ascii=True)
    if len(output.encode()) > 27000:
        payload["compact"] = {"deferred": "Broker stdout bound; exact files and gzip publication copies are preserved"}
        output = json.dumps(payload, ensure_ascii=True)
    assert len(output.encode()) <= 27000
    print(output)


if __name__ == "__main__":
    main()
