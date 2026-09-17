from architecture_common import *
from fusion_study import digest_bytes


def ident(item):
    fid=str(item["frame_id"])
    return item["video_id"],int(fid.split("#")[-1])


def main():
    out=ROOT/"outputs/reranker-compatibility"
    out.mkdir(parents=True,exist_ok=False)
    path=PARENT/"inputs/qwen3_vl_reranker_2b_top100.json"
    saved=unique_index(read_json(path)["per_query"])
    historical=unique_index(read_jsonl(PARENT/"inputs/qwen_only_top100.jsonl"))
    current=unique_index(read_jsonl(ROOT/"outputs/packet-e/rankings.jsonl"))
    rows=[]
    for qid in sorted(current):
        c=current[qid]["arms"]["control"]["frames"]
        s=saved[qid]["reranked_candidates_top20"]
        known={ident(r) for r in s}
        rows.append({"query_id":qid,"retained_scores":len(s),
            "same_query":saved[qid]["query"]==historical[qid]["query"],
            "same_ordered_candidate_pool":[ident(r) for r in c]==[ident(r) for r in historical[qid]["candidates_top100"]],
            "top10_scores_present":sum(ident(r) in known for r in c[:10]),
            "top20_scores_present":sum(ident(r) in known for r in c[:20]),
            "missing_top20":[r["frame_id"] for r in c[:20] if ident(r) not in known]})
    write(out/"per_query.jsonl",rows,True)
    summary={"verdict":"INCONCLUSIVE","executed":False,"reason":"Historical top20 retained scores do not establish matched scores over fresh fused top10/top20. No censored scores invented; no historical fusion sweep repeated.",
        "same_ordered_pool_queries":sum(r["same_ordered_candidate_pool"] for r in rows),
        "all_top10_scores_present_queries":sum(r["top10_scores_present"]==10 for r in rows),
        "all_top20_scores_present_queries":sum(r["top20_scores_present"]==20 for r in rows),
        "input_sha256":digest_bytes(path.read_bytes()),"new_inference_calls":0}
    write(out/"summary.json",summary)
    print(summary)


if __name__=="__main__":main()
