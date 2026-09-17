"""Fixed soft object evidence on accepted ranking, with no new inference."""
import sys,time,datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
V1=ROOT.parent/'astra-overnight-issue92-v1'
V5=ROOT.parent/'astra-overnight-issue92-v5'
sys.path.insert(0,str(ROOT.parent/'astra-overnight-issue92-v2/code'))
from semantic_crossencoder import sha,read_json,read_jsonl,write,unique_index,evaluate,projection,PARENT
from yolo import mentions
import numpy as np

def reorder(frames,support):
    # Preserve the accepted leading frame. Positive support is never absence evidence.
    tail=sorted(enumerate(frames[1:],2),key=lambda x:(-(61/(60+x[0])+.05*support.get(x[1]['frame_id'],0)),x[0]))
    return projection([{**f,'rank':i+1} for i,f in enumerate([frames[0]]+[f for _,f in tail])])

def main():
    base=read_jsonl(V5/'outputs/frame-text/rankings.jsonl')
    assert read_json(V5/'validation/accepted.json')['status']=='passed'
    queries=unique_index(read_jsonl(PARENT/'outputs/fusion/queries.jsonl'))
    rules=read_json(V1/'yolo_policy.json')
    paths=[V5/'outputs/frame-text/rankings.jsonl',V5/'validation/accepted.json',V1/'yolo_policy.json',V1/'code/yolo.py',PARENT/'outputs/fusion/queries.jsonl',PARENT/'inputs/canonical_truth.jsonl',PARENT/'reference/evaluate_reranker_fusion.py',Path(__file__)]
    write(ROOT/'policy.json',{'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'parent':'accepted v5','hypothesis':'Sparse existing positive object evidence may complement OCR/ASR ranking without filtering missing detections.','rule':'Protect first frame; rank tail by61/(60+accepted frame rank)+0.05*fraction supported categories. Same inherited dictionary/confidence0.5/negation guard. Stable ties. No sweeps.','inputs_sha256':{str(p):sha(p) for p in paths}})
    source=Path(r'D:\Official-Dataset\derived\yoloe-26x-directml\features')
    labels={};hashes={};rows=[];evidence=[];start=time.perf_counter_ns()
    for r in base:
        q=r['query_id'];control=r['arms']['protected_full100_rrf60'];rule=mentions(queries[q]['query_text'],rules);support={};available=0
        for f in control['frames']:
            fid=f['frame_id']
            if not rule['applicable']:continue
            vid,num=fid.split('#');p=source/vid/(num+'.npy')
            if fid not in labels:
                if p.exists():
                    hashes[str(p)]=sha(p);a=np.load(p,allow_pickle=False)
                    labels[fid]=sorted({str(x['label']).casefold() for x in a if float(x['conf'])>=rules['detection_confidence']})
                else:labels[fid]=None
            if labels[fid] is not None:
                available+=1
                support[fid]=sum(bool(set(rules['categories'][c]['labels'])&set(labels[fid])) for c in rule['categories'])/len(rule['categories'])
        rows.append({'query_id':q,'arms':{'control':control,'object_rank':reorder(control['frames'],support)}})
        evidence.append({'query_id':q,'rule':rule,'available':available,'support':support})
    write(ROOT/'inputs/detection_labels.json',labels);write(ROOT/'inputs/detection_hashes.json',hashes);write(ROOT/'inputs/evidence.jsonl',evidence,True)
    elapsed=time.perf_counter_ns()-start
    out=ROOT/'outputs';out.mkdir()
    summary=evaluate(rows,out,'object_rank')
    summary['workload']={'new_inference':0,'detection_files':len(hashes),'applicable_queries':sum(x['rule']['applicable'] for x in evidence),'covered_queries':sum(x['available']>0 for x in evidence),'supported_frames':sum(sum(v>0 for v in x['support'].values()) for x in evidence),'same_session_wall_ns':elapsed}
    write(out/'summary.json',summary)
    write(out/'complete.json',{'policy_sha256':sha(ROOT/'policy.json'),'rankings_sha256':sha(out/'rankings.jsonl'),'summary_sha256':sha(out/'summary.json')})
    print(summary['verdict'],summary['workload'])

if __name__=='__main__':main()
