"""Query-only alternate English translations; frozen beams, no answer repair."""
import hashlib
import importlib.util
import os
import sys
import time
from pathlib import Path
from architecture_common import *
from semantic import projection, fuse


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def routes(texts, tokenize):
    streams=[]
    for text in texts:
        tokens=tokenize(text)
        if tokens not in streams:
            streams.append(tokens)
    return streams


def main():
    os.environ['HF_HUB_OFFLINE']='1'
    os.environ['TRANSFORMERS_OFFLINE']='1'
    policy=read_json(ROOT/'query_translation_policy.json')
    for path,digest in policy['input_sha256'].items():
        assert sha(Path(path))==digest,path
    out=ROOT/'outputs/query-translation'
    out.mkdir(exist_ok=False)
    import torch
    from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
    torch.set_num_threads(8)
    torch.set_num_interop_threads(1)
    tokenizer=AutoTokenizer.from_pretrained(policy['snapshot'],local_files_only=True,trust_remote_code=False)
    model,loading=AutoModelForSeq2SeqLM.from_pretrained(policy['snapshot'],local_files_only=True,
        trust_remote_code=False,use_safetensors=False,output_loading_info=True,torch_dtype=torch.float32)
    assert not any(loading[k] for k in ('missing_keys','unexpected_keys','mismatched_keys','error_msgs')),loading
    model.eval()
    write(out/'model_audit.json',{'loading_info':loading,'model_class':type(model).__name__,
          'parameter_count':sum(p.numel() for p in model.parameters()),'model_files_sha256':policy['input_sha256'],
          'device':'cpu','dtype':'float32','torch':torch.__version__})
    queries=read_jsonl(PARENT/'outputs/fusion/queries.jsonl')
    generated=[]
    checkpoint=out/'generated'
    checkpoint.mkdir()
    for q in queries:
        started=time.perf_counter_ns()
        encoded=tokenizer(q['query_text'],return_tensors='pt',truncation=False)
        length=encoded['input_ids'].shape[1]
        translations=[]
        status='input_too_long_canonical_fallback'
        if length<=512:
            with torch.inference_mode():
                sequences=model.generate(**encoded,do_sample=False,num_beams=4,num_return_sequences=2,
                                         max_new_tokens=512,early_stopping=True)
            # Do not silently accept a token-capped partial translation.
            for seq in sequences:
                ids=seq.tolist()[1:]
                if tokenizer.eos_token_id in ids:
                    text=tokenizer.decode(seq,skip_special_tokens=True).strip()
                    if text and text not in translations:
                        translations.append(text)
            status='translated' if translations else 'output_capped_canonical_fallback'
        row={'query_id':q['query_id'],'canonical_sha256':q['query_text_sha256'],
             'texts':[q['query_text']]+translations,'input_tokens':length,'status':status,
             'generation_wall_ns':time.perf_counter_ns()-started}
        write(checkpoint/(q['query_id']+'.json'),row)
        generated.append(row)
    write(out/'queries.jsonl',generated,True)
    # Entire query-only transformation set is on disk before retrieval or scoring.
    source=ROOT/'outputs/semantic'
    spec=importlib.util.spec_from_file_location('translation_bm25',source/'source_bm25.py')
    module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module
    spec.loader.exec_module(module)
    records=read_jsonl(source/'records.jsonl')
    mapped=read_json(source/'record_frame_mapping.json')
    index=module.BM25([r['tokens'] for r in records])
    base=unique_index(read_jsonl(ROOT/'outputs/packet-e/rankings.jsonl'))
    results=[]
    calls=0
    for q in generated:
        started=time.perf_counter_ns()
        rrf={}
        streams=routes(q['texts'],module.tokenize)
        for tokens in streams:
            scores=index.scores(tokens)
            calls+=1
            order=sorted(range(len(records)),key=lambda i:(-scores[i],records[i]['segment_id'],i))
            for rank,i in enumerate([i for i in order if scores[i]>0][:100],1):
                rrf[i]=rrf.get(i,0)+1/(60+rank)
        frames=[]
        seen=set()
        for i in sorted(rrf,key=lambda i:(-rrf[i],records[i]['segment_id'],i)):
            fid=mapped[i]
            if fid is None or fid in seen:continue
            seen.add(fid)
            frames.append({'frame_id':fid,'video_id':records[i]['video_id'],'rank':len(frames)+1,'score':rrf[i],'record_index':i})
            if len(frames)==100:break
        control=base[q['query_id']]['arms']['control']
        results.append({'query_id':q['query_id'],'wall_ns':time.perf_counter_ns()-started,'route_count':len(streams),
             'arms':{'control':control,'translation_provider':projection(frames)}})
    provider=out/'provider'
    provider.mkdir()
    summary=evaluate(results,provider,'translation_provider')
    gate=bool(summary['coverage']['accepted_video_present']['rescues'] or summary['coverage']['target_coverage']['rescues'])
    summary['contribution_gate_passed']=gate
    summary['workload']={'generation_calls':sum(q['input_tokens']<=512 for q in generated),'provider_calls':calls,
        'query_count':len(generated),'record_count':len(records),'new_corpus_inference':0,'download_bytes':0,
        'generation_wall_ns':sum(q['generation_wall_ns'] for q in generated),'search_wall_ns':sum(r['wall_ns'] for r in results),
        'fallback_queries':[q['query_id'] for q in generated if q['status']!='translated']}
    write(provider/'summary.json',summary)
    if gate:
        rows=[{'query_id':r['query_id'],'arms':{'control':r['arms']['control'],
              'translation_rrf':fuse(r['arms']['control']['frames'],r['arms']['translation_provider']['frames'])}} for r in results]
        write(out/'summary.json',evaluate(rows,out,'translation_rrf'))
    write(out/'complete.json',{'status':'complete','queries_sha256':sha(out/'queries.jsonl'),
          'provider_summary_sha256':sha(provider/'summary.json'),'integration_executed':gate})
    print('query translation complete',summary['workload'],flush=True)


if __name__=='__main__':main()
