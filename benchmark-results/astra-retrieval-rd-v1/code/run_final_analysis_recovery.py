#!/usr/bin/env python3
"""Read-only, exact-pin final analysis assembly for Vecna82; no models or retrieval."""
from pathlib import Path
import argparse,base64,gzip,hashlib,io,json,os,shutil,subprocess,sys,tempfile,time,traceback,urllib.request,zipfile
PREFIX="benchmark-results/astra-retrieval-rd-v1/"
PINS={"B":"5ea6195fdfb4f895f378bac3c55c0d7bcb1c4353","source":"8c71336d73876d7c31292b453c636fa39efbd921","C":"897111a6f3fc65b42773f564357e7eb4ce6a19dd","A":"e08ef662bb0f02162b4aa72288729c71936bae90","D":"402fc03645a3ace6c1cdaffab26ef621b02c68d2"}
BRANCHES=["btl/issue-82-fusion-study","btl/issue-82-source-review","btl/issue-82-astra-retrieval-rd","btl/issue-82-native-images","btl/issue-82-ledger-recovery"]
RAW="outputs/fusion/capture-full115-v1/provider_rankings.jsonl"
MANIFEST="outputs/fusion/capture-full115-v1/collection_manifest.json"
EVAL="outputs/fusion/evaluation/"
OUT="outputs/synthesis/final-analysis-v1/"
def sha(data):return hashlib.sha256(data).hexdigest()
def git(repo,*args):return subprocess.run(["git","-C",str(repo),*args],check=True,capture_output=True).stdout
def decode(data):return data.decode("utf-8")
def main():
    ap=argparse.ArgumentParser();ap.add_argument("--artifact-url",required=True);args=ap.parse_args()
    repo=Path.cwd();root=repo/PREFIX;native=Path("C:/Users/minhc/Code/Vecna")
    initial_head=git(repo,"rev-parse","HEAD")
    original={p:git(repo,"show","HEAD:"+p) for p in decode(git(repo,"ls-files",PREFIX)).splitlines()}
    overlay={};logs={};checks=[];stage="prepare";result={"status":"failed","new_model_or_retrieval_calls":0,"pins":PINS}
    def put(rel,raw):
        p=root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
    def save(rel,value):put(rel,(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+"\n").encode("utf-8"))
    def copy_pin(label,predicate):
        pin=PINS[label]
        for p in decode(git(native,"ls-tree","-r","--name-only",pin,"--",PREFIX)).splitlines():
            rel=p[len(PREFIX):]
            if predicate(rel):
                raw=git(native,"show",pin+":"+p);put(rel,raw)
                overlay[rel]={"commit":pin,"git_blob":decode(git(native,"rev-parse",pin+":"+p)).strip(),"bytes":len(raw),"sha256":sha(raw)}
    def run(label,argv,timeout=240):
        nonlocal stage
        stage=label;t=time.perf_counter()
        c=subprocess.run([sys.executable,"-B",*argv],cwd=root,capture_output=True,timeout=timeout,env={**os.environ,"PYTHONDONTWRITEBYTECODE":"1"})
        logs[label+".stdout.txt"]=c.stdout;logs[label+".stderr.txt"]=c.stderr
        checks.append({"name":label,"returncode":c.returncode,"elapsed_seconds":time.perf_counter()-t})
        if c.returncode:raise RuntimeError(label+" failed:\n"+c.stderr.decode(errors="replace")[-9500:])
        return c
    try:
        for p,raw in original.items():(repo/p).write_bytes(raw)
        before=(git(native,"rev-parse","HEAD"),git(native,"status","--porcelain=v1","--untracked-files=all"))
        git(native,"fetch","--no-tags","origin",*BRANCHES)
        assert before==(git(native,"rev-parse","HEAD"),git(native,"status","--porcelain=v1","--untracked-files=all"))
        result["native_head_status_unchanged_after_fetch"]=True
        result["native_head"]=decode(before[0]).strip()
        text_suffixes=(".py",".json",".jsonl",".md",".txt",".log",".js")
        copy_pin("B",lambda p:p.endswith(text_suffixes) and not p.startswith(EVAL))
        copy_pin("source",lambda p:p.endswith(text_suffixes) and ((p.startswith("code/") and p.split("/")[-1] not in ("analyze_reranker.py","preflight.py")) or p.startswith(("outputs/dataset-audit/","outputs/source-visibility/","outputs/temporal-truth-review/"))))
        copy_pin("C",lambda p:p.startswith("outputs/reranker/") and p.endswith(text_suffixes))
        copy_pin("A",lambda p:p=="outputs/temporal-multi-image/summary.json")
        copy_pin("D",lambda p:p in ("code/build_failure_ledger.py","code/visibility_ledger.py","tests/test_failure_ledger.py","tests/test_visibility_ledger.py"))
        copy_pin("B",lambda p:p in (EVAL+"compact_per_query.json",))
        # The compact oracle is moved aside so the frozen evaluator gets an absent output directory.
        compact=(root/EVAL/"compact_per_query.json").read_bytes()
        (root/EVAL/"compact_per_query.json").unlink();(root/EVAL).rmdir()
        assert sha((root/"code/analyze_reranker.py").read_bytes())=="2b9b2624fda6582c1ba894ecb8ec39e90b27d9d6258f8c75676773bb36bd2bb1"
        stage="recover-exact-raw"
        archive=urllib.request.urlopen(urllib.request.Request(args.artifact_url,headers={"User-Agent":"Mozilla/5.0"}),timeout=80).read()
        assert len(archive)==3223668 and sha(archive)=="95b505aa824f40cb730ab5bb989b0db1597a619ba348c60cb5bcb234eed84da8"
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            patch_name=next(x for x in z.namelist() if x.endswith("changes.patch"))
            patch=z.read(patch_name).replace(b"\r\n",b"\n")
        assert len(patch)==27410372 and sha(patch)=="b1cfc642c03c0e8e7805646b85c133260307187178d39c1bb5a28d91635e74f9"
        with tempfile.TemporaryDirectory(prefix="vecna82-raw-recovery-") as tmp:
            temp=Path(tmp);git(temp,"init","--quiet")
            pp=temp/"capture.patch";pp.write_bytes(patch)
            git(temp,"-c","core.autocrlf=false","-c","core.eol=lf","apply","--include="+PREFIX+RAW,str(pp))
            raw=(temp/PREFIX/RAW).read_bytes()
        candidates=[raw,raw.replace(b"\r\n",b"\n"),raw.replace(b"\r\n",b"\n").replace(b"\n",b"\r\n")]
        raw=next(x for x in candidates if len(x)==27146363 and sha(x)=="d6223381ea8cbf4b4efcb0cc295f60dccfcae36afe0d9fac004438410c152a82")
        put(RAW,raw)
        assert sha((root/MANIFEST).read_bytes())=="01333a2ce910605b537a90aa6897938103aaf1728048d216af350d26bde756d8"
        for rel in overlay:
            if rel.endswith(".py"):compile((root/rel).read_bytes(),rel,"exec")
        run("fusion-tests",["-m","unittest","discover","-s","tests","-p","test_fusion*.py","-v"])
        run("fusion-evaluation",["code/evaluate_fusion_study.py","--root",".","--rankings",RAW,"--collection-manifest",MANIFEST])
        put(EVAL+"compact_per_query.json",compact)
        run("headroom",["code/analyze_fusion_headroom.py","--root",".","--rankings",RAW,"--collection-manifest",MANIFEST,"--study",EVAL+"study_results.jsonl","--summary",EVAL+"summary.json","--output",EVAL+"coverage_headroom.json"])
        shared=["--rankings",RAW,"--config","outputs/fusion/frozen_config.json","--queries","outputs/fusion/queries.jsonl","--collection-manifest",MANIFEST,"--sidecar",EVAL+"study_timings.json"]
        run("study-freeze",["code/fusion_study_storage.py","freeze",*shared,"--study",EVAL+"study_results.jsonl","--summary",EVAL+"summary.json","--proof",EVAL+"study_reconstruction_proof.json"])
        side_sha=sha((root/EVAL/"study_timings.json").read_bytes())
        with tempfile.TemporaryDirectory(prefix="vecna82-exact-study-rebuild-") as tmp:
            rebuilt=Path(tmp)/"study.jsonl"
            run("study-rebuild",["code/fusion_study_storage.py","rebuild",*shared,"--sidecar-sha256",side_sha,"--output",str(rebuilt)])
            assert rebuilt.read_bytes()==(root/EVAL/"study_results.jsonl").read_bytes()
        run("ledger-tests",["-m","unittest","discover","-s","tests","-p","test_*ledger.py","-v"])
        run("ledger-generation",["code/build_failure_ledger.py","--root",".","--require-complete"])
        with tempfile.TemporaryDirectory(prefix="vecna82-ledger-repeat-") as tmp:
            run("ledger-repeat",["code/build_failure_ledger.py","--root",".","--require-complete","--out-dir",tmp])
            for name in ("failure_ledger.jsonl","summary.json","provenance.json","REPORT.md"):
                assert (root/"outputs/failure-ledger"/name).read_bytes()==(Path(tmp)/name).read_bytes()
        summary=json.loads((root/"outputs/failure-ledger/summary.json").read_bytes())
        headroom=json.loads((root/EVAL/"coverage_headroom.json").read_bytes())
        assert summary["cohort"]["scoreable_queries"]==113 and summary["remaining_misses"]==31
        assert summary["primary_failure_counts"].get("none")==82
        assert headroom["complete_target_admission_headroom_query_ids"]==["p0_q02","p0_q20","p2_q07"]
        assert headroom["additional_partial_target_admission_headroom_query_ids"]==["p2_q29"]
        bsummary=json.loads((root/EVAL/"summary.json").read_bytes())
        assert bsummary["descriptive_best_global_arm"]=="fusion_current_control"
        assert git(repo,"rev-parse","HEAD")==initial_head
        assert before==(git(native,"rev-parse","HEAD"),git(native,"status","--porcelain=v1","--untracked-files=all"))
        result.update(status="passed",stage="complete",checks=checks,native_head_status_unchanged_final=True,disposable_head_unchanged=True,ledger_replay_files=4,ledger_replay_byte_identical=True,study_rebuild_byte_identical=True,study_sha256=sha((root/EVAL/"study_results.jsonl").read_bytes()),sidecar_sha256=side_sha,cohort=summary["cohort"],remaining_misses=31,primary_failure_counts=summary["primary_failure_counts"],headroom={k:v for k,v in headroom.items() if k in ("overall","complete_target_admission_headroom_query_ids","additional_partial_target_admission_headroom_query_ids")})
        save(OUT+"assembly_inputs.json",overlay)
        for name,raw in logs.items():put(OUT+"logs/"+name,raw)
        save(OUT+"verification.json",result)
        selected=[EVAL+n for n in ("per_query.jsonl","summary.json","slices.json","REPORT.md","policy.json","coverage_headroom.json","study_timings.json","study_reconstruction_proof.json")]
        selected+=["outputs/failure-ledger/"+n for n in ("failure_ledger.jsonl","summary.json","provenance.json","REPORT.md")]
        selected += [p.relative_to(root).as_posix() for p in (root/OUT).rglob("*") if p.is_file()]
        files=[]
        for rel in sorted(set(selected)):
            raw=(root/rel).read_bytes()
            files.append({"path":rel,"bytes":len(raw),"sha256":sha(raw),"content":raw.decode("utf-8")})
        payload=(json.dumps({"schema":"vecna82-final-analysis-bundle-v1","files":files},ensure_ascii=False,separators=(",",":"),allow_nan=False)+"\n").encode("utf-8")
        packed=gzip.compress(payload,compresslevel=9,mtime=0)
        put(OUT+"final_bundle.gzip",packed)
        manifest={"schema":"vecna82-final-analysis-transport-v1","bundle_bytes":len(packed),"bundle_sha256":sha(packed),"decoded_bytes":len(payload),"decoded_sha256":sha(payload),"files":[{k:v for k,v in row.items() if k!="content"} for row in files]}
        save(OUT+"transport_manifest.json",manifest)
        result["bundle"]=manifest
    except BaseException as error:
        result.update(status="failed",stage=stage,error=str(error),traceback=traceback.format_exc(),checks=checks)
        for name,raw in logs.items():put(OUT+"logs/"+name,raw)
        save(OUT+"verification.json",result)
    finally:
        # Only exact validation evidence/transport survive; all assembly cleanup is in the disposable clone.
        kept={p.relative_to(root).as_posix():p.read_bytes() for p in (root/OUT).rglob("*") if p.is_file()} if (root/OUT).exists() else {}
        for p in list(root.rglob("*")):
            if p.is_file() and PREFIX+p.relative_to(root).as_posix() not in original:p.unlink()
        for p,raw in original.items():(repo/p).write_bytes(raw)
        for rel,raw in kept.items():put(rel,raw)
        assert git(repo,"rev-parse","HEAD")==initial_head
        print(json.dumps(result,ensure_ascii=False,allow_nan=False))
    return 0 if result["status"]=="passed" else 1
if __name__=="__main__":raise SystemExit(main())
