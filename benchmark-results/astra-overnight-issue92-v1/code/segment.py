import shutil
import time
from pathlib import Path
from architecture_common import *
from fusion_study import validate_row,current_scores,_rank,digest_bytes


def identity(fid):
    video,frame=fid.split("#")
    return video,int(frame)


def select(order, mapping):
    seen=set()
    result=[]
    for fid in order:
        key=mapping.get(identity(fid), ("unmapped",fid))
        if key not in seen:
            result.append(fid)
            seen.add(key)
    return result


def main():
    out=ROOT/"outputs/segment-v2"
    out.mkdir(parents=True,exist_ok=False)
    source=Path(r"C:\Users\minhc\Code\Vecna\.worktrees\shot-clustering\segment_map.json")
    snapshot=out/"segment_map.json"
    shutil.copyfile(source,snapshot)
    data=read_json(snapshot)
    mapping={}
    for video, row in data.items():
        assert len(row["fids"])==len(row["segs"]) and len(set(row["fids"]))==len(row["fids"])
        mapping.update({(video,int(fid)):(video,seg) for fid,seg in zip(row["fids"],row["segs"])})
    raw=unique_index(read_jsonl(PARENT/"outputs/fusion/capture-full115-v1/provider_rankings.jsonl"))
    base=unique_index(read_jsonl(ROOT/"outputs/packet-e/rankings.jsonl"))
    config=read_json(PARENT/"outputs/fusion/frozen_config.json")
    rankings=[]
    for qid in sorted(raw):
        r=raw[qid]
        start=time.perf_counter_ns()
        scores,contrib=current_scores(validate_row(r,config),r["candidate_tie_order"],config)
        order=sorted(r["candidate_tie_order"],key=lambda fid:scores[fid],reverse=True)
        retained=select(order,mapping)[:100]
        f,v=_rank(scores,contrib,[fid for fid in r["candidate_tie_order"] if fid in set(retained)],config)
        rankings.append({"query_id":qid,"mapped_union_frames":sum(identity(fid) in mapping for fid in order),
            "removed_duplicates":len(order)-len(select(order,mapping)),"wall_ns":time.perf_counter_ns()-start,
            "arms":{"control":base[qid]["arms"]["control"],"segment": {"frames":f,"videos":v}}})
    summary=evaluate(rankings,out,"segment")
    summary["map"]={"source":str(source),"sha256":digest_bytes(snapshot.read_bytes()),"videos":len(data),"frames":len(mapping),
        "mapped_union_frames":sum(r["mapped_union_frames"] for r in rankings),"affected_queries":sum(r["removed_duplicates"]>0 for r in rankings),
        "scope_caveat":"Existing map covers only five videos; unknown frames retain singleton identity. No corpus-wide conclusion."}
    summary["workload"]={"new_inference_calls":0,"provider_calls":0,"wall_ns_total":sum(r["wall_ns"] for r in rankings)}
    write(out/"summary.json",summary)
    print(summary["verdict"],summary["map"])


if __name__=="__main__":main()
