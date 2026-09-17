"""One fixed score-guided semantic interval projection, no new inference."""
import bisect
import hashlib
import time
from architecture_common import *
from fusion_study import validate_row,current_scores
from semantic import projection,fuse


def project_record(record, catalog, candidates, scores, tie, fallback):
    video=record['video_id']
    lo,hi=record['start_sec']*catalog['fps'][video],record['end_sec']*catalog['fps'][video]
    eligible=[fid for fid,n in candidates.get(video,[]) if lo<=n<=hi]
    return min(eligible,key=lambda fid:(-scores[fid],tie[fid])) if eligible else fallback


def main():
    import numpy as np
    policy=read_json(ROOT/'semantic_grounding_policy.json')
    for path,digest in policy['input_sha256'].items():
        from pathlib import Path
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest,path
    out=ROOT/'outputs/semantic-grounding'
    out.mkdir(exist_ok=False)
    records=read_jsonl(ROOT/'outputs/semantic/records.jsonl')
    mapped=read_json(ROOT/'outputs/semantic/record_frame_mapping.json')
    catalog=read_json(ROOT/'outputs/semantic/frame_catalog.json')
    queries=read_jsonl(PARENT/'outputs/fusion/queries.jsonl')
    embeddings=np.concatenate([np.load(p,allow_pickle=False) for p in sorted((ROOT/'outputs/semantic-dense/batches').glob('*.npy'))])
    assert embeddings.shape==(3071,1024)
    raw=unique_index(read_jsonl(PARENT/'outputs/fusion/capture-full115-v1/provider_rankings.jsonl'))
    base=unique_index(read_jsonl(ROOT/'outputs/packet-e/rankings.jsonl'))
    config=read_json(PARENT/'outputs/fusion/frozen_config.json')
    rows=[]
    for q,vector in zip(queries,embeddings[2956:]):
        start=time.perf_counter_ns()
        qid=q['query_id'];r=raw[qid]
        scores,_=current_scores(validate_row(r,config),r['candidate_tie_order'],config)
        tie={fid:i for i,fid in enumerate(r['candidate_tie_order'])}
        candidates={}
        for fid in r['candidate_tie_order']:
            video,n=fid.rsplit('#',1)
            candidates.setdefault(video,[]).append((fid,int(n)))
        semantic_scores=embeddings[:2956]@vector
        order=sorted(range(len(records)),key=lambda i:(-float(semantic_scores[i]),records[i]['segment_id'],i))
        frames=[];seen=set()
        for i in order:
            fid=project_record(records[i],catalog,candidates,scores,tie,mapped[i])
            if fid is None or fid in seen:continue
            seen.add(fid)
            frames.append({'frame_id':fid,'video_id':records[i]['video_id'],'rank':len(frames)+1,
                'score':float(semantic_scores[i]),'record_index':i,'mapping_changed':fid!=mapped[i],
                'mapping_source':'current_score_inside_interval' if fid in scores else 'midpoint_fallback'})
            if len(frames)==100:break
        rows.append({'query_id':qid,'query_text_sha256':q['query_text_sha256'],'wall_ns':time.perf_counter_ns()-start,
            'arms':{'control':base[qid]['arms']['control'],'grounded_dense':projection(frames)}})
    provider=out/'provider';provider.mkdir()
    summary=evaluate(rows,provider,'grounded_dense')
    gate=bool(summary['coverage']['accepted_video_present']['rescues'] or summary['coverage']['target_coverage']['rescues'])
    summary['contribution_gate_passed']=gate
    summary['workload']={'new_inference_calls':0,'new_provider_calls':0,'cached_cosine_pairs':2956*115,
        'changed_representatives':sum(f['mapping_changed'] for r in rows for f in r['arms']['grounded_dense']['frames']),
        'same_session_wall_ns':sum(r['wall_ns'] for r in rows)}
    write(provider/'summary.json',summary)
    if gate:
        integrated=[{'query_id':r['query_id'],'arms':{'control':r['arms']['control'],
            'grounded_dense_rrf':fuse(r['arms']['control']['frames'],r['arms']['grounded_dense']['frames'])}} for r in rows]
        write(out/'summary.json',evaluate(integrated,out,'grounded_dense_rrf'))
    write(out/'complete.json',{'status':'complete','coverage_gate':gate,'policy_sha256':hashlib.sha256((ROOT/'semantic_grounding_policy.json').read_bytes()).hexdigest()})
    print('grounding complete',summary['verdict'],summary['workload'])


if __name__=='__main__':main()
