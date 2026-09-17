import re
import time
import unicodedata
from pathlib import Path
import numpy as np
from architecture_common import *
from fusion_study import digest_bytes
from semantic import projection


def normalize(text):
    text=text.casefold().replace("đ","d")
    return " ".join(re.findall(r"\w+","".join(c for c in unicodedata.normalize("NFD",text) if unicodedata.category(c)!="Mn")))


def mentions(query, policy):
    text=" "+normalize(query)+" "
    unsafe=any(" "+term+" " in text for term in policy["negative_query_markers"])
    categories=[key for key,value in policy["categories"].items() if any(" "+term+" " in text for term in value["query"])]
    return {"categories":categories,"negative_marker":unsafe,"applicable":bool(categories) and not unsafe}


def main():
    out=ROOT/"outputs/yolo"
    out.mkdir(parents=True,exist_ok=False)
    policy=read_json(ROOT/"yolo_policy.json")
    queries=read_jsonl(PARENT/"outputs/fusion/queries.jsonl")
    applicable={q["query_id"]:mentions(q["query_text"],policy) for q in queries}
    write(out/"applicability.json",applicable)
    base=read_jsonl(ROOT/"outputs/packet-e/rankings.jsonl")
    source=Path(r"D:\Official-Dataset\derived\yoloe-26x-directml\features")
    cache={}
    inputs={}
    rankings=[]
    for r in base:
        start=time.perf_counter_ns()
        qid=r["query_id"]
        rule=applicable[qid]
        frames=r["arms"]["control"]["frames"]
        scored=[]
        available=boosted=0
        for f in frames:
            support=[]
            if rule["applicable"]:
                fid=f["frame_id"]
                video,frame=fid.split("#")
                path=source/video/(frame+".npy")
                if fid not in cache:
                    if path.exists():
                        data=path.read_bytes()
                        inputs[str(path)]=digest_bytes(data)
                        a=np.load(path,allow_pickle=False)
                        cache[fid]=sorted({str(x["label"]).casefold() for x in a if float(x["conf"])>=policy["detection_confidence"]})
                    else:
                        cache[fid]=None
                labels=cache[fid]
                if labels is not None:
                    available+=1
                    support=[cat for cat in rule["categories"] if set(policy["categories"][cat]["labels"])&set(labels)]
            boost=policy["boost"]*len(support)/len(rule["categories"]) if support else 0
            boosted+=bool(boost)
            scored.append({**f,"score":f["score"]+boost,"yolo_boost":boost,"supported_categories":support})
        # Python stable sort preserves original current order on unchanged scores.
        scored.sort(key=lambda f:f["score"],reverse=True)
        scored=[{**f,"rank":i} for i,f in enumerate(scored,1)]
        rankings.append({"query_id":qid,"available_detection_frames":available,"boosted_frames":boosted,
            "wall_ns":time.perf_counter_ns()-start,"arms":{"control":r["arms"]["control"],"yolo":projection(scored)}})
    write(out/"detection_labels.json",cache)
    write(out/"input_hashes.json",inputs)
    summary=evaluate(rankings,out,"yolo")
    summary["workload"]={"new_inference_calls":0,"provider_calls":0,"read_detection_files":len(inputs),
        "applicable_queries":sum(r["applicable"] for r in applicable.values()),"queries_with_detection_coverage":sum(r["available_detection_frames"]>0 for r in rankings),
        "queries_with_boost":sum(r["boosted_frames"]>0 for r in rankings),"boosted_frame_appearances":sum(r["boosted_frames"] for r in rankings),
        "same_session_wall_ns":sum(r["wall_ns"] for r in rankings)}
    subset=[r for r in read_jsonl(out/"per_query.jsonl") if applicable[r["query_id"]]["applicable"]]
    summary["applicable_slice"]={layer:{arm:aggregate(subset,layer,arm) for arm in ("control","yolo")} for layer in LAYERS}
    write(out/"summary.json",summary)
    print(summary["verdict"],summary["workload"])


if __name__=="__main__":main()
