"""Existing production semantic BM25 on canonical115; no inference or truth-fed retrieval."""
import csv
import dataclasses
import importlib.util
import shutil
import sys
import time
from pathlib import Path
from architecture_common import *
from fusion_study import digest_bytes

SOURCE=Path(r"C:\Users\minhc\Code\official-dataset-control")
FEATURES=Path(r"D:\Official-Dataset\features_L21-L30_branch-feats-siglip\features")


def projection(frames):
    seen=set()
    videos=[]
    for f in frames:
        if f["video_id"] not in seen:
            seen.add(f["video_id"])
            videos.append({**f,"frame_rank":f["rank"],"rank":len(videos)+1})
    return {"frames":frames,"videos":videos}


def fuse(base, semantic):
    scores={}
    for rows in (base,semantic):
        for rank, f in enumerate(rows,1):
            fid=f["frame_id"]
            scores[fid]=scores.get(fid,0)+1/(60+rank)
    order=sorted(scores,key=lambda fid:scores[fid],reverse=True)[:100]
    return projection([{"frame_id":fid,"video_id":fid.split("#")[0],"rank":i,"score":scores[fid]} for i,fid in enumerate(order,1)])


def main():
    out=ROOT/"outputs/semantic"
    out.mkdir(parents=True,exist_ok=False)
    code=SOURCE/"scripts/benchmark_semantic_index.py"
    spec=importlib.util.spec_from_file_location("semantic_source",code)
    module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module
    spec.loader.exec_module(module)
    shutil.copyfile(code,out/"source_bm25.py")
    records=module.load_records()
    write(out/"records.jsonl",[dataclasses.asdict(r) for r in records],True)
    sources={r.path for r in records}
    coverage_path=SOURCE/"derived/metadata/asr-ocr-text-v1/coverage.csv"
    fps={r["video_id"]:int(r["rounded_fps"]) for r in csv.DictReader(coverage_path.open(encoding="utf-8-sig")) if r["fps_status"]=="ok"}
    source_hashes={str(SOURCE/name):digest_bytes((SOURCE/name).read_bytes()) for name in sorted(sources)}
    source_hashes[str(code)]=digest_bytes(code.read_bytes())
    source_hashes[str(coverage_path)]=digest_bytes(coverage_path.read_bytes())
    write(out/"source_hashes.json",source_hashes)
    frame_catalog={}
    for video in sorted({r.video_id for r in records}):
        frame_catalog[video]=sorted((int(p.name),p.name) for p in (FEATURES/video).iterdir() if p.is_dir() and p.name.isdigit())
    write(out/"frame_catalog.json",{"fps":fps,"frames":frame_catalog,"source":str(FEATURES)})
    mapped=[]
    for r in records:
        lo,hi=r.start_sec*fps[r.video_id],r.end_sec*fps[r.video_id]
        candidates=[(n,s) for n,s in frame_catalog[r.video_id] if lo<=n<=hi]
        chosen=min(candidates,key=lambda pair:(abs(pair[0]-(lo+hi)/2),pair[0])) if candidates else None
        mapped.append(f"{r.video_id}#{chosen[1]}" if chosen else None)
    write(out/"record_frame_mapping.json",mapped)
    queries=read_jsonl(PARENT/"outputs/fusion/queries.jsonl")
    index=module.BM25([r.tokens for r in records])
    ranked=[]
    base=unique_index(read_jsonl(ROOT/"outputs/packet-e/rankings.jsonl"))
    for q in queries:
        start=time.perf_counter_ns()
        scores=index.scores(module.tokenize(q["query_text"]))
        order=sorted(range(len(records)),key=lambda i:(-scores[i],records[i].segment_id,i))
        frames=[]
        seen=set()
        for i in order:
            fid=mapped[i]
            if scores[i]<=0:
                break
            if fid is None or fid in seen:
                continue
            seen.add(fid)
            frames.append({"frame_id":fid,"video_id":records[i].video_id,"rank":len(frames)+1,"score":scores[i],"record_index":i})
            if len(frames)==100:
                break
        ranked.append({"query_id":q["query_id"],"query_text_sha256":q["query_text_sha256"],
            "wall_ns":time.perf_counter_ns()-start,"arms":{"control":base[q["query_id"]]["arms"]["control"],"semantic":projection(frames)}})
    summary=evaluate(ranked,out,"semantic")
    gains=summary["coverage"]["accepted_video_present"]["rescues"]
    target_gains=summary["coverage"]["target_coverage"]["rescues"]
    summary["contribution_gate_passed"]=bool(gains or target_gains)
    summary["workload"]={"new_inference_calls":0,"provider_calls":115,"records":len(records),"videos":len(frame_catalog),
        "mapped_records":sum(x is not None for x in mapped),"wall_ns_total":sum(r["wall_ns"] for r in ranked)}
    write(out/"summary.json",summary)
    if summary["contribution_gate_passed"]:
        integrated=ROOT/"outputs/semantic-integrated"
        integrated.mkdir(exist_ok=False)
        rows=[{"query_id":r["query_id"],"arms":{"control":r["arms"]["control"],"semantic_rrf":fuse(r["arms"]["control"]["frames"],r["arms"]["semantic"]["frames"])}} for r in ranked]
        integrated_summary=evaluate(rows,integrated,"semantic_rrf")
        write(integrated/"summary.json",integrated_summary)
    write(out/"complete.json",{"status":"complete","records_sha256":digest_bytes((out/"records.jsonl").read_bytes()),
        "coverage_gate":summary["contribution_gate_passed"],"integration_executed":summary["contribution_gate_passed"]})
    print("semantic complete",summary["workload"],"gate",summary["contribution_gate_passed"])


if __name__=="__main__":main()
