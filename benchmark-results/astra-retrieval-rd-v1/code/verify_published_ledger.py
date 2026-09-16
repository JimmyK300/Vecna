#!/usr/bin/env python3
"""Verify the published Vecna82 analysis snapshot without models or retrieval."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,sys,tempfile
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def verify(root):
    root=root.resolve();checks=[]
    def run(*argv):
        done=subprocess.run([sys.executable,"-B",*argv],cwd=root,capture_output=True,timeout=180,env={**os.environ,"PYTHONDONTWRITEBYTECODE":"1"})
        checks.append({"command":list(argv),"returncode":done.returncode})
        if done.returncode:raise RuntimeError(done.stderr.decode(errors="replace"))
    run("code/hydrate_fusion_capture.py","--root",".")
    evaluation=root/"outputs/fusion/evaluation"
    proof=json.loads((evaluation/"study_reconstruction_proof.json").read_bytes())
    sidecar=evaluation/"study_timings.json"
    if sha(sidecar)!=proof["sidecar"]["sha256"]:raise ValueError("Published timing sidecar differs from its proof")
    study=evaluation/"study_results.jsonl"
    if not study.exists():
        run("code/fusion_study_storage.py","rebuild","--rankings","outputs/fusion/capture-full115-v1/provider_rankings.jsonl",
            "--config","outputs/fusion/frozen_config.json","--queries","outputs/fusion/queries.jsonl",
            "--collection-manifest","outputs/fusion/capture-full115-v1/collection_manifest.json",
            "--sidecar","outputs/fusion/evaluation/study_timings.json","--sidecar-sha256",proof["sidecar"]["sha256"],
            "--output","outputs/fusion/evaluation/study_results.jsonl")
    if sha(study)!=proof["source_study"]["sha256"]:raise ValueError("Published study reconstruction differs")
    ledger=root/"outputs/failure-ledger"
    provenance=json.loads((ledger/"provenance.json").read_bytes())
    if sha(root/"code/build_failure_ledger.py")!=provenance["generator_sha256"]:raise ValueError("Ledger generator differs")
    for path,want in provenance["inputs_sha256"].items():
        if sha(root/path)!=want:raise ValueError("Published ledger input differs: "+path)
    with tempfile.TemporaryDirectory(prefix="vecna82-published-ledger-replay-") as name:
        output=Path(name)
        run("code/build_failure_ledger.py","--root",".","--require-complete","--out-dir",str(output))
        outputs={}
        for name in ("failure_ledger.jsonl","summary.json","provenance.json","REPORT.md"):
            raw=(ledger/name).read_bytes()
            if raw!=(output/name).read_bytes():raise ValueError("Published ledger does not reproduce byte for byte: "+name)
            outputs[name]={"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}
    summary=json.loads((ledger/"summary.json").read_bytes())
    if summary["cohort"]["scoreable_queries"]!=113 or summary["remaining_misses"]!=31:raise ValueError("Published cohort differs")
    return {"schema":"vecna82-published-snapshot-verification-v1","status":"passed","python":sys.version,
        "new_model_or_retrieval_calls":0,"published_input_files_verified":len(provenance["inputs_sha256"]),
        "study_sha256":sha(study),"sidecar_sha256":sha(sidecar),"ledger_outputs":outputs,
        "primary_failure_counts":summary["primary_failure_counts"],"checks":checks,
        "runtime_limit":"Exact timing restoration preserves the recorded Windows Python3.12 study. Any platform/libm difference must fail the full SHA gate, never loosen it."}
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--root",type=Path,default=Path(__file__).resolve().parents[1]);parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    if args.output and args.output.exists():raise ValueError("Verification output already exists")
    result=verify(args.root);text=json.dumps(result,indent=2,ensure_ascii=False)+"\n"
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        with args.output.open("x",encoding="utf-8",newline="\n") as handle:handle.write(text)
    print(text)
if __name__=="__main__":main()
