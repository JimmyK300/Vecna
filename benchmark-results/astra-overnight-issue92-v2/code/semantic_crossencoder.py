"""Frozen top-20 semantic cross-encoder experiment; blind inference then scoring."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
V1 = ROOT.parent / 'astra-overnight-issue92-v1'
sys.path.insert(0, str(V1 / 'code'))
from architecture_common import PARENT, read_json, read_jsonl, write, unique_index, evaluate
from semantic import projection


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def rerank(base, scores):
    """Reorder covered top-20 video slots using equal RRF60; leave others fixed."""
    videos = [r['video_id'] for r in base['videos']]
    covered = [v for v in videos[:20] if v in scores]
    semantic = sorted(covered, key=lambda v: (-scores[v], videos.index(v)))
    ranked = sorted(covered, key=lambda v: (-(1/(60+covered.index(v)+1)
        + 1/(60+semantic.index(v)+1)), videos.index(v)))
    replacements = iter(ranked)
    ordered = [next(replacements) if v in scores and i < 20 else v for i,v in enumerate(videos)]
    positions = {v:i for i,v in enumerate(ordered)}
    frames = sorted(base['frames'], key=lambda f: (positions[f['video_id']], f['rank']))
    result = projection([{**f, 'rank':i+1} for i,f in enumerate(frames)])
    assert {f['frame_id'] for f in result['frames']} == {f['frame_id'] for f in base['frames']}
    assert len(result['frames']) == len(base['frames']) <= 100
    assert [r['video_id'] for r in result['videos']] == ordered
    return result


def main():
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    policy = read_json(ROOT/'policy.json')
    binding = sha(ROOT/'policy.json')
    out = ROOT/'outputs/semantic-crossencoder'
    out.mkdir(parents=True, exist_ok=True)
    assert not (out/'complete.json').exists(), 'Do not relaunch completed job'
    for path,digest in policy['inputs_sha256'].items():
        assert sha(path) == digest, path
    import numpy as np
    import torch
    import transformers
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    torch.set_num_threads(8)
    torch.set_num_interop_threads(1)
    tokenizer = AutoTokenizer.from_pretrained(policy['model_path'], local_files_only=True)
    model, loading = AutoModelForSequenceClassification.from_pretrained(
        policy['model_path'], local_files_only=True, output_loading_info=True)
    assert not any(loading.get(k) for k in ('missing_keys','unexpected_keys','mismatched_keys','error_msgs')), loading
    model.eval()
    audit = {'loading':loading, 'torch':torch.__version__, 'transformers':transformers.__version__,
             'parameters':sum(p.numel() for p in model.parameters()), 'policy_sha256':binding,
             'device':'cpu', 'dtype':str(next(model.parameters()).dtype)}
    if not (out/'model_audit.json').exists(): write(out/'model_audit.json',audit)
    records = read_jsonl(V1/'outputs/semantic/records.jsonl')
    queries = read_jsonl(PARENT/'outputs/fusion/queries.jsonl')
    vectors = np.concatenate([np.load(p,allow_pickle=False) for p in sorted((V1/'outputs/semantic-dense/batches').glob('*.npy'))])
    assert vectors.shape == (3071,1024)
    base = unique_index(read_jsonl(V1/'outputs/packet-e/rankings.jsonl'))
    by_video = {}
    for i,r in enumerate(records): by_video.setdefault(r['video_id'],[]).append(i)
    cache = out/'queries'
    cache.mkdir(exist_ok=True)
    timings = []
    rankings = []
    deadline = datetime.datetime.fromisoformat(policy['stop_compute_utc'])
    for qi,q in enumerate(queries):
        qid = q['query_id']
        control = base[qid]['arms']['control']
        similarity = vectors[:2956] @ vectors[2956+qi]
        chosen = []
        for v in control['videos'][:20]:
            indices = by_video.get(v['video_id'],[])
            if indices:
                idx = min(indices,key=lambda i:(-float(similarity[i]),records[i]['segment_id'],i))
                chosen.append({'video_id':v['video_id'],'record_index':idx,'dense_score':float(similarity[idx])})
        cache_path = cache/f'{qid}.json'
        if cache_path.exists():
            result = read_json(cache_path)
            assert result['policy_sha256'] == binding and result['chosen'] == chosen
        else:
            pairs = [[q['query_text'],records[r['record_index']]['text']] for r in chosen]
            logits, token_counts = [], []
            started = time.perf_counter_ns()
            for start in range(0,len(pairs),2):
                if datetime.datetime.now(datetime.timezone.utc) >= deadline:
                    write(out/'deadline_stop.json',{'status':'INCOMPLETE','completed_queries':len(timings)})
                    return
                batch = pairs[start:start+2]
                token_counts.extend(len(ids) for ids in tokenizer(batch,padding=False,truncation=False)['input_ids'])
                inputs = tokenizer(batch,padding=True,truncation=True,max_length=1024,return_tensors='pt')
                with torch.inference_mode():
                    value = model(**inputs).logits.reshape(-1).float().cpu().numpy()
                assert np.isfinite(value).all()
                logits.extend(float(x) for x in value)
            result = {'query_id':qid,'query_text_sha256':q['query_text_sha256'],'policy_sha256':binding,
                      'chosen':chosen,'logits':logits,'token_counts':token_counts,
                      'truncated_pairs':sum(n>1024 for n in token_counts),'wall_ns':time.perf_counter_ns()-started}
            write(cache_path,result)
        assert len(result['logits']) == len(chosen)
        timings.append(result)
        scores = {r['video_id']:score for r,score in zip(chosen,result['logits'])}
        rankings.append({'query_id':qid,'arms':{'control':control,'crossencoder_rrf60':rerank(control,scores)}})
    summary = evaluate(rankings,out,'crossencoder_rrf60')
    summary['workload'] = {'queries':len(queries),'pairs':sum(len(r['logits']) for r in timings),
        'pair_inference_wall_ns':sum(r['wall_ns'] for r in timings),
        'truncated_pairs':sum(r['truncated_pairs'] for r in timings),'new_corpus_embeddings':0}
    write(out/'summary.json',summary)
    write(out/'complete.json',{'policy_sha256':binding,'summary_sha256':sha(out/'summary.json'),
        'rankings_sha256':sha(out/'rankings.jsonl'),'query_files_sha256':{str(p):sha(p) for p in sorted(cache.glob('*.json'))}})


if __name__ == '__main__': main()
