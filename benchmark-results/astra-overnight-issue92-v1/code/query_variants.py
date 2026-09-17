import importlib.util
import re
import sys
import time
from architecture_common import *
from semantic import projection,fuse


def variants(query,module):
    quoted=re.findall(r'["“]([^"“”]+)["”]',query)
    texts=[query," ".join(dict.fromkeys(module.tokenize(query)))," ".join(quoted) if quoted else query]
    # Duplicate token streams count once, retaining the canonical route first.
    streams=[]
    for text in texts:
        tokens=module.tokenize(text)
        if tokens not in streams:
            streams.append(tokens)
    return texts,streams


def main():
    out=ROOT/"outputs/query-variants"
    out.mkdir(parents=True,exist_ok=False)
    source=ROOT/"outputs/semantic"
    spec=importlib.util.spec_from_file_location("variants_bm25",source/"source_bm25.py")
    module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module
    spec.loader.exec_module(module)
    records=read_jsonl(source/"records.jsonl")
    mapped=read_json(source/"record_frame_mapping.json")
    bm25=module.BM25([r["tokens"] for r in records])
    queries=read_jsonl(PARENT/"outputs/fusion/queries.jsonl")
    frozen=[{"query_id":q["query_id"],"texts":variants(q["query_text"],module)[0],"token_streams":variants(q["query_text"],module)[1]} for q in queries]
    write(out/"queries.jsonl",frozen,True)
    base=unique_index(read_jsonl(ROOT/"outputs/packet-e/rankings.jsonl"))
    results=[]
    calls=0
    for query in frozen:
        start=time.perf_counter_ns()
        rrf={}
        for tokens in query["token_streams"]:
            scores=bm25.scores(tokens)
            calls+=1
            order=sorted(range(len(records)),key=lambda i:(-scores[i],records[i]["segment_id"],i))
            # Fixed top100 positive records per route; no outcome-dependent expansion.
            for rank,i in enumerate([i for i in order if scores[i]>0][:100],1):
                rrf[i]=rrf.get(i,0)+1/(60+rank)
        order=sorted(rrf,key=lambda i:(-rrf[i],records[i]["segment_id"],i))
        seen=set()
        frames=[]
        for i in order:
            fid=mapped[i]
            if fid is None or fid in seen:
                continue
            seen.add(fid)
            frames.append({"frame_id":fid,"video_id":records[i]["video_id"],"rank":len(frames)+1,"score":rrf[i],"record_index":i})
            if len(frames)==100:break
        qid=query["query_id"]
        control=base[qid]["arms"]["control"]
        results.append({"query_id":qid,"wall_ns":time.perf_counter_ns()-start,
            "arms":{"control":control,"variants_rrf":fuse(control["frames"],frames)},"semantic_variant_frames":frames})
    summary=evaluate(results,out,"variants_rrf")
    summary["workload"]={"new_inference_calls":0,"provider_calls":calls,"max_query_variants":3,
        "same_session_wall_ns":sum(r["wall_ns"] for r in results),"source":"semantic BM25 only; no new visual embedding/index calls"}
    write(out/"summary.json",summary)
    print(summary["verdict"],summary["workload"])


if __name__=="__main__":main()
