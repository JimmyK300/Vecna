"""Fixed top30 frame-text rerank using existing OCR/ASR, blind to truth."""
import datetime
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
V2=ROOT.parent/'astra-overnight-issue92-v2'
sys.path.insert(0,str(V2/'code'))
from semantic_crossencoder import sha, V1, PARENT, read_json, read_jsonl, write, unique_index, evaluate, projection


def rerank_frames(base,scores):
    covered=[f['frame_id'] for f in base['frames'][:30] if f['frame_id'] in scores]
    semantic=sorted(covered,key=lambda fid:(-scores[fid],covered.index(fid)))
    order=sorted(covered,key=lambda fid:(-(1/(60+covered.index(fid)+1)+1/(60+semantic.index(fid)+1)),covered.index(fid)))
    replacements=iter(order)
    lookup={f['frame_id']:f for f in base['frames']}
    ids=[next(replacements) if i<30 and f['frame_id'] in scores else f['frame_id'] for i,f in enumerate(base['frames'])]
    result=projection([{**lookup[fid],'rank':i+1} for i,fid in enumerate(ids)])
    assert set(ids)==set(lookup) and len(ids)==len(lookup)<=100
    return result


def main():
    os.environ['HF_HUB_OFFLINE']='1'
    os.environ['TRANSFORMERS_OFFLINE']='1'
    policy=read_json(ROOT/'policy.json');binding=sha(ROOT/'policy.json')
    out=ROOT/'outputs/frame-text';out.mkdir(parents=True,exist_ok=True)
    assert not (out/'complete.json').exists(),'Do not relaunch completed job'
    for p,h in policy['inputs_sha256'].items():assert sha(p)==h,p
    import numpy as np
    import torch
    import transformers
    from transformers import AutoTokenizer,AutoModelForSequenceClassification
    torch.set_num_threads(8);torch.set_num_interop_threads(1)
    tokenizer=AutoTokenizer.from_pretrained(policy['model_path'],local_files_only=True)
    model,loading=AutoModelForSequenceClassification.from_pretrained(policy['model_path'],local_files_only=True,output_loading_info=True)
    assert not any(loading.get(k) for k in ('missing_keys','unexpected_keys','mismatched_keys','error_msgs')),loading
    model.eval()
    if not (out/'model_audit.json').exists():write(out/'model_audit.json',{'loading':loading,'torch':torch.__version__,'transformers':transformers.__version__,'device':'cpu','dtype':str(next(model.parameters()).dtype),'policy_sha256':binding})
    texts=unique_index(read_jsonl(ROOT/'inputs/frame_text.jsonl'),field='frame_id')
    queries=read_jsonl(PARENT/'outputs/fusion/queries.jsonl')
    base=unique_index(read_jsonl(V1/'outputs/packet-e/rankings.jsonl'))
    cache=out/'queries';cache.mkdir(exist_ok=True)
    deadline=datetime.datetime.fromisoformat(policy['stop_compute_utc'])
    timings=[];rankings=[]
    for q in queries:
        qid=q['query_id'];control=base[qid]['arms']['control']
        chosen=[f['frame_id'] for f in control['frames'][:30] if texts[f['frame_id']]['text'].strip()]
        path=cache/f'{qid}.json'
        if path.exists():
            result=read_json(path)
            assert result['policy_sha256']==binding and result['chosen']==chosen
        else:
            pairs=[[q['query_text'],texts[fid]['text']] for fid in chosen]
            logits=[];counts=[];started=time.perf_counter_ns()
            for start in range(0,len(pairs),2):
                if datetime.datetime.now(datetime.timezone.utc)>=deadline:
                    write(out/'deadline_stop.json',{'status':'INCOMPLETE','completed_queries':len(timings)})
                    return
                batch=pairs[start:start+2]
                counts.extend(len(ids) for ids in tokenizer(batch,padding=False,truncation=False)['input_ids'])
                inputs=tokenizer(batch,padding=True,truncation=True,max_length=1024,return_tensors='pt')
                with torch.inference_mode():values=model(**inputs).logits.reshape(-1).float().cpu().numpy()
                assert np.isfinite(values).all()
                logits.extend(float(x) for x in values)
            result={'query_id':qid,'query_text_sha256':q['query_text_sha256'],'policy_sha256':binding,'chosen':chosen,'logits':logits,'token_counts':counts,'truncated_pairs':sum(n>1024 for n in counts),'wall_ns':time.perf_counter_ns()-started}
            write(path,result)
        assert len(result['logits'])==len(chosen)
        rankings.append({'query_id':qid,'arms':{'control':control,'frame_text_rrf60':rerank_frames(control,dict(zip(chosen,result['logits'])))}})
        timings.append(result)
    summary=evaluate(rankings,out,'frame_text_rrf60')
    summary['workload']={'queries':len(queries),'pairs':sum(len(r['logits']) for r in timings),'pair_inference_wall_ns':sum(r['wall_ns'] for r in timings),'truncated_pairs':sum(r['truncated_pairs'] for r in timings),'new_corpus_embeddings':0,'new_frame_extractions':0}
    write(out/'summary.json',summary)
    write(out/'complete.json',{'policy_sha256':binding,'summary_sha256':sha(out/'summary.json'),'rankings_sha256':sha(out/'rankings.jsonl'),'query_files_sha256':{str(p):sha(p) for p in sorted(cache.glob('*.json'))}})


if __name__=='__main__':main()
