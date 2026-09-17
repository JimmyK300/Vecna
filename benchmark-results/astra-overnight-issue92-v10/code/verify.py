"""Post-run acceptance and paired comparison to exact PR91."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from frame_text import *

out=ROOT/'outputs/frame-text';complete=read_json(out/'complete.json');policy=read_json(ROOT/'policy.json')
assert complete['policy_sha256']==sha(ROOT/'policy.json')
for p,h in policy['inputs_sha256'].items():assert sha(p)==h,p
sources=read_json(ROOT/'inputs/source_hashes.json')['sha256']
for p,h in sources.items():assert sha(p)==h,p
for n in ('summary','rankings'):assert sha(out/(n+'.json'+('l' if n=='rankings' else '')))==complete[n+'_sha256']
for p,h in complete['query_files_sha256'].items():assert sha(p)==h,p
rankings=read_jsonl(out/'rankings.jsonl');base=unique_index(read_jsonl(ROOT.parent/'astra-overnight-issue92-v4/outputs/temporal-bins/rankings.jsonl'))
original=unique_index(read_jsonl(V1/'outputs/packet-e/rankings.jsonl'))
texts=unique_index(read_jsonl(ROOT/'inputs/frame_text.jsonl'),field='frame_id')
v3=ROOT.parent/'astra-overnight-issue92-v5'
best=unique_index(read_jsonl(v3/'outputs/frame-text/rankings.jsonl'))
old_texts=unique_index(read_jsonl(v3/'inputs/frame_text.jsonl'),field='frame_id')
for fid,t in texts.items():
    assert t['parts']==old_texts[fid]['parts']
    assert t['text']==('OCR: '+t['parts']['ocr'].strip() if t['parts']['ocr'].strip() else '')
old_policy=read_json(v3/'policy.json')
assert policy['model_path']==old_policy['model_path']
for p,h in old_policy['inputs_sha256'].items():
    if p.startswith(policy['model_path']):assert policy['inputs_sha256'][p]==h
queries=unique_index(read_jsonl(PARENT/'outputs/fusion/queries.jsonl'))
assert len(rankings)==len(complete['query_files_sha256'])==115 and len(read_jsonl(out/'per_query.jsonl'))==113
reused=0;new=0;original_comparison=[]
for row in rankings:
    q=row['query_id'];control=row['arms']['control'];arm=row['arms']['ocr_only']
    assert control==best[q]['arms']['protected_full100_rrf60']
    control=base[q]['arms']['temporal5s']
    cache=read_json(out/'queries'/f'{q}.json');scores=dict(zip(cache['chosen'],cache['logits']))
    assert cache['query_text_sha256']==queries[q]['query_text_sha256']
    assert arm==rerank_frames(control,scores)
    assert arm['frames'][0]==control['frames'][0]
    assert {f['frame_id'] for f in arm['frames']}=={f['frame_id'] for f in control['frames']}
    for i,f in enumerate(control['frames']):
        if i==0 or f['frame_id'] not in scores:assert arm['frames'][i]['frame_id']==f['frame_id']
    old=read_json(v3/'outputs/frame-text/queries'/f'{q}.json')
    assert old['query_text_sha256']==cache['query_text_sha256']
    old_scores=dict(zip(old['chosen'],old['logits']))
    reused_here=0
    for fid in cache['chosen']:
        if fid in old_scores and texts[fid]['text']==old_texts[fid]['text']:
            assert scores[fid]==old_scores[fid];reused_here+=1
    assert reused_here==cache['reused_pairs']
    assert len(cache['chosen'])==cache['reused_pairs']+cache['new_pairs']
    reused+=reused_here;new+=cache['new_pairs']
    original_comparison.append({'query_id':q,'arms':{'control':original[q]['arms']['control'],'ocr_only':arm}})
verify=ROOT/'validation/recomputed';verify.mkdir(parents=True)
summary=evaluate(rankings,verify,'ocr_only');saved=read_json(out/'summary.json')
for k,v in summary.items():assert v==saved[k],k
against=ROOT/'validation/vs-pr91';against.mkdir()
original_summary=evaluate(original_comparison,against,'ocr_only');write(against/'summary.json',original_summary)
write(ROOT/'validation/accepted.json',{'status':'passed','queries':115,'scoreable':113,'source_hashes':len(sources),'cache_hashes':115,'reused_pairs_verified':reused,'new_pairs':new,'distinct_video':summary['metrics']['distinct_video'],'paired_vs_v5':summary['paired']['distinct_video'],'paired_vs_pr91':original_summary['paired']['distinct_video']})
print({'status':'passed','source_hashes':len(sources),'reused':reused,'new':new,'vs_pr91':original_summary['paired']['distinct_video']})
