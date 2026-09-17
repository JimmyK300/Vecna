"""Verify saved partial inference without scoring a selected query subset."""
import math
from frame_text import *

out=ROOT/'outputs/frame-text'
stop=read_json(out/'deadline_stop.json')
assert stop['status']=='INCOMPLETE'
assert not any((out/n).exists() for n in ('complete.json','rankings.jsonl','summary.json','per_query.jsonl'))
policy=read_json(ROOT/'policy.json');binding=sha(ROOT/'policy.json')
for p,h in policy['inputs_sha256'].items():assert sha(p)==h,p
sources=read_json(ROOT/'inputs/source_hashes.json')['sha256']
for p,h in sources.items():assert sha(p)==h,p
texts=unique_index(read_jsonl(ROOT/'inputs/frame_text.jsonl'),field='frame_id')
v5=ROOT.parent/'astra-overnight-issue92-v5'
oldtexts=unique_index(read_jsonl(v5/'inputs/frame_text.jsonl'),field='frame_id')
for fid,t in texts.items():
    assert t['parts']==oldtexts[fid]['parts']
    assert t['text']==('ASR: '+t['parts']['asr'].strip() if t['parts']['asr'].strip() else '')
queries=read_jsonl(PARENT/'outputs/fusion/queries.jsonl')
base=unique_index(read_jsonl(ROOT.parent/'astra-overnight-issue92-v4/outputs/temporal-bins/rankings.jsonl'))
paths=sorted((out/'queries').glob('*.json'))
assert len(paths)==stop['completed_queries']==104
assert {p.stem for p in paths}=={q['query_id'] for q in queries[:104]}
new=reused=truncated=wall=0
for q in queries[:104]:
    qid=q['query_id'];c=read_json(out/'queries'/f'{qid}.json')
    assert c['query_text_sha256']==q['query_text_sha256'] and c['policy_sha256']==binding
    chosen=[f['frame_id'] for f in base[qid]['arms']['temporal5s']['frames'][1:100] if texts[f['frame_id']]['text'].strip()]
    assert c['chosen']==chosen and len(c['logits'])==len(chosen) and all(math.isfinite(x) for x in c['logits'])
    old=read_json(v5/'outputs/frame-text/queries'/f'{qid}.json')
    assert old['query_text_sha256']==q['query_text_sha256']
    scores=dict(zip(old['chosen'],old['logits']));count=0
    for fid,value in zip(chosen,c['logits']):
        if fid in scores and texts[fid]['text']==oldtexts[fid]['text']:
            assert value==scores[fid];count+=1
    assert count==c['reused_pairs'] and len(chosen)==count+c['new_pairs']
    assert len(c['token_counts'])==c['new_pairs']
    assert sum(n>1024 for n in c['token_counts'])==c['truncated_pairs']
    new+=c['new_pairs'];reused+=count;truncated+=c['truncated_pairs'];wall+=c['wall_ns']
validation=ROOT/'validation';validation.mkdir()
write(validation/'incomplete_verified.json',{'status':'INCOMPLETE_VERIFIED','completed_queries':104,'total_queries':115,
    'policy_sha256':binding,'source_hashes_verified':len(sources),'cache_sha256':{str(p):sha(p) for p in paths},
    'saved_new_pairs':new,'saved_reused_pairs':reused,'saved_truncated_pairs':truncated,'saved_query_wall_ns':wall,
    'unsaved_partial_query_work':'not measured; timings and pair counts are lower bounds',
    'benchmark_metrics':None,'reason':'planned 23:40 UTC compute cutoff; no partial-subset scoring'})
print({'status':'INCOMPLETE_VERIFIED','queries':104,'new':new,'reused':reused,'truncated':truncated,'saved_seconds':wall/1e9})
