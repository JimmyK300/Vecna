"""One cached English query variant, with conserved text-fusion weight."""
import sys,os,time,datetime,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
V5=ROOT.parent/'astra-overnight-issue92-v5'
V4=ROOT.parent/'astra-overnight-issue92-v4'
sys.path.insert(0,str(ROOT.parent/'astra-overnight-issue92-v2/code'))
from semantic_crossencoder import sha,read_json,read_jsonl,write,unique_index,evaluate,projection,V1,PARENT

def rerank(base,canonical,english):
    ids=[f['frame_id'] for f in base['frames'][1:] if f['frame_id'] in canonical]
    assert set(ids)==set(canonical)==set(english)
    ranks={fid:i+1 for i,fid in enumerate(ids)}
    cr={f:i+1 for i,f in enumerate(sorted(ids,key=lambda f:(-canonical[f],ranks[f])))}
    er={f:i+1 for i,f in enumerate(sorted(ids,key=lambda f:(-english[f],ranks[f])))}
    order=iter(sorted(ids,key=lambda f:(-(1/(60+ranks[f])+.5*(1/(60+cr[f])+1/(60+er[f]))),ranks[f])))
    lookup={f['frame_id']:f for f in base['frames']}
    ordered=[next(order) if i>0 and f['frame_id'] in canonical else f['frame_id'] for i,f in enumerate(base['frames'])]
    return projection([{**lookup[fid],'rank':i+1} for i,fid in enumerate(ordered)])

def main():
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
    policy=read_json(ROOT/'policy.json');binding=sha(ROOT/'policy.json')
    for p,h in policy['inputs_sha256'].items():assert sha(p)==h,p
    out=ROOT/'outputs';out.mkdir(exist_ok=True);cache=out/'queries';cache.mkdir(exist_ok=True)
    assert not (out/'complete.json').exists(),'Completed jobs must not be relaunched'
    import torch,numpy as np,transformers
    from transformers import AutoTokenizer,AutoModelForSequenceClassification
    torch.set_num_threads(8);torch.set_num_interop_threads(1)
    tok=AutoTokenizer.from_pretrained(policy['model_path'],local_files_only=True)
    model,loading=AutoModelForSequenceClassification.from_pretrained(policy['model_path'],local_files_only=True,output_loading_info=True)
    assert not any(loading.get(k) for k in ('missing_keys','unexpected_keys','mismatched_keys','error_msgs'))
    model.eval()
    write(out/'model_audit.json',{'loading':loading,'torch':torch.__version__,'transformers':transformers.__version__,'device':'cpu','dtype':str(next(model.parameters()).dtype),'policy_sha256':binding})
    texts=unique_index(read_jsonl(V5/'inputs/frame_text.jsonl'),field='frame_id')
    base=unique_index(read_jsonl(V4/'outputs/temporal-bins/rankings.jsonl'))
    best=unique_index(read_jsonl(V5/'outputs/frame-text/rankings.jsonl'))
    rows=[];timings=[];deadline=datetime.datetime.fromisoformat(policy['stop_compute_utc'])
    for q in read_jsonl(ROOT/'inputs/queries.jsonl'):
        qid=q['query_id'];old=read_json(V5/'outputs/frame-text/queries'/f'{qid}.json')
        assert old['query_text_sha256']==q['canonical_sha256']
        chosen=old['chosen'];path=cache/f'{qid}.json'
        if path.exists():
            result=read_json(path);assert result['policy_sha256']==binding and result['chosen']==chosen
        else:
            start=time.perf_counter_ns();logits=[];counts=[]
            if q['fallback']:logits=old['logits']
            else:
                pairs=[[q['text'],texts[f]['text']] for f in chosen]
                for i in range(0,len(pairs),2):
                    if datetime.datetime.now(datetime.timezone.utc)>=deadline:
                        write(out/'deadline_stop.json',{'status':'INCOMPLETE','completed_queries':len(rows)});return
                    batch=pairs[i:i+2];counts.extend(len(v) for v in tok(batch,padding=False,truncation=False)['input_ids'])
                    inp=tok(batch,padding=True,truncation=True,max_length=1024,return_tensors='pt')
                    with torch.inference_mode():values=model(**inp).logits.reshape(-1).float().cpu().numpy()
                    assert np.isfinite(values).all();logits.extend(float(x) for x in values)
            result={'query_id':qid,'canonical_sha256':q['canonical_sha256'],'variant_sha256':q['variant_sha256'],'policy_sha256':binding,'chosen':chosen,'logits':logits,'new_pairs':0 if q['fallback'] else len(chosen),'reused_pairs':len(chosen) if q['fallback'] else 0,'token_counts':counts,'truncated_pairs':sum(n>1024 for n in counts),'wall_ns':time.perf_counter_ns()-start}
            write(path,result)
        assert len(result['logits'])==len(chosen)
        arm=rerank(base[qid]['arms']['temporal5s'],dict(zip(chosen,old['logits'])),dict(zip(chosen,result['logits'])))
        rows.append({'query_id':qid,'arms':{'control':best[qid]['arms']['protected_full100_rrf60'],'query_variant':arm}});timings.append(result)
    s=evaluate(rows,out,'query_variant');s['workload']={k:sum(r[k] for r in timings) for k in ('new_pairs','reused_pairs','truncated_pairs','wall_ns')}
    s['workload'].update({'new_embeddings':0,'new_extraction':0,'new_translation':0,'queries':len(rows)})
    write(out/'summary.json',s)
    write(out/'complete.json',{'policy_sha256':binding,'summary_sha256':sha(out/'summary.json'),'rankings_sha256':sha(out/'rankings.jsonl'),'query_files_sha256':{str(p):sha(p) for p in sorted(cache.glob('*.json'))}})

if __name__=='__main__':main()
