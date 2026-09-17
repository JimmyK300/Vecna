"""One global five-second temporal-neighborhood admission test, unchanged fusion."""
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
V2=ROOT.parent/'astra-overnight-issue92-v2'
sys.path.insert(0,str(V2/'code'))
from semantic_crossencoder import sha,V1,PARENT,read_json,read_jsonl,write,unique_index,evaluate
from fusion_study import validate_row,current_scores,_rank


def select(order,fps,seconds=5,budget=100):
    seen=set();chosen=[]
    for fid in order:
        video,frame=fid.split('#')
        key=(video,int(frame)//(fps[video]*seconds)) if video in fps else ('unknown',fid)
        if key in seen:continue
        seen.add(key);chosen.append(fid)
        if len(chosen)==budget:break
    return chosen


def main():
    policy=read_json(ROOT/'policy.json')
    for p,h in policy['inputs_sha256'].items():assert sha(p)==h,p
    fps=read_json(V1/'outputs/semantic/frame_catalog.json')['fps']
    raw=unique_index(read_jsonl(PARENT/'outputs/fusion/capture-full115-v1/provider_rankings.jsonl'))
    base=unique_index(read_jsonl(V1/'outputs/packet-e/rankings.jsonl'))
    config=read_json(PARENT/'outputs/fusion/frozen_config.json')
    out=ROOT/'outputs/temporal-bins';out.mkdir(parents=True,exist_ok=False)
    rankings=[]
    for qid,r in sorted(raw.items()):
        started=time.perf_counter_ns()
        scores,contrib=current_scores(validate_row(r,config),r['candidate_tie_order'],config)
        cf,cv=_rank(scores,contrib,r['candidate_tie_order'],config)
        assert {'frames':cf,'videos':cv}==base[qid]['arms']['control']
        order=sorted(r['candidate_tie_order'],key=lambda fid:scores[fid],reverse=True)
        chosen=select(order,fps)
        f,v=_rank(scores,contrib,[fid for fid in r['candidate_tie_order'] if fid in set(chosen)],config)
        assert len(f)<=100 and all(row['score']==scores[row['frame_id']] for row in f)
        rankings.append({'query_id':qid,'unknown_fps_union_frames':sum(fid.split('#')[0] not in fps for fid in order),
          'admission_order':chosen,'wall_ns':time.perf_counter_ns()-started,'arms':{'control':{'frames':cf,'videos':cv},'temporal5s':{'frames':f,'videos':v}}})
    summary=evaluate(rankings,out,'temporal5s')
    summary['workload']={'new_inference_calls':0,'provider_calls':0,'new_extraction':0,'unknown_fps_union_frames':sum(r['unknown_fps_union_frames'] for r in rankings),'wall_ns':sum(r['wall_ns'] for r in rankings)}
    write(out/'summary.json',summary)
    write(out/'complete.json',{'policy_sha256':sha(ROOT/'policy.json'),'summary_sha256':sha(out/'summary.json'),'rankings_sha256':sha(out/'rankings.jsonl')})
    print(summary['verdict'],summary['metrics']['distinct_video'],summary['coverage'])

if __name__=='__main__':main()
