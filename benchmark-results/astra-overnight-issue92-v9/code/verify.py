"""Post-run acceptance and paired comparison to exact PR91."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from frame_text import *
from candidate_admission import admit

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
strongest=unique_index(read_jsonl(v3/'outputs/frame-text/rankings.jsonl'))
admitted=unique_index(read_jsonl(ROOT/'inputs/admission.jsonl'))
provider=unique_index(read_jsonl(V1/'outputs/semantic-grounding/provider/rankings.jsonl'))
v6=ROOT.parent/'astra-overnight-issue92-v6'
extra_texts=unique_index(read_jsonl(v6/'inputs/frame_text.jsonl'),field='frame_id')
extra_policy=read_json(v6/'policy.json')
assert extra_policy['model_path']==policy['model_path']
for p,h in extra_policy['inputs_sha256'].items():
    if p.startswith(policy['model_path']):assert policy['inputs_sha256'][p]==h
old_texts=unique_index(read_jsonl(v3/'inputs/frame_text.jsonl'),field='frame_id')
old_policy=read_json(v3/'policy.json')
assert policy['model_path']==old_policy['model_path']
for p,h in old_policy['inputs_sha256'].items():
    if p.startswith(policy['model_path']):assert policy['inputs_sha256'][p]==h
queries=unique_index(read_jsonl(PARENT/'outputs/fusion/queries.jsonl'))
assert len(rankings)==len(complete['query_files_sha256'])==115 and len(read_jsonl(out/'per_query.jsonl'))==113
reused=0;new=0;original_comparison=[]
for row in rankings:
    q=row['query_id'];control=row['arms']['control'];arm=row['arms']['video_preserving']
    assert control==strongest[q]['arms']['protected_full100_rrf60']
    control=admitted[q]['arms']['video_preserving']
    assert control==projection(admit(base[q]['arms']['temporal5s']['frames'],provider[q]['arms']['grounded_dense']['frames']))
    assert {f['video_id'] for f in base[q]['arms']['temporal5s']['frames']} <= {f['video_id'] for f in control['frames']}
    assert control['frames'][0]==base[q]['arms']['temporal5s']['frames'][0]
    assert len(control['frames'])==len({f['frame_id'] for f in control['frames']})==100
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
    extra=read_json(v6/'outputs/frame-text/queries'/f'{q}.json')
    assert extra['query_text_sha256']==cache['query_text_sha256']
    extra_scores=dict(zip(extra['chosen'],extra['logits']))
    reused_here=0
    for fid in cache['chosen']:
        if fid in old_scores and texts[fid]['text']==old_texts[fid]['text']:
            assert scores[fid]==old_scores[fid];reused_here+=1
        elif fid in extra_scores and texts[fid]['text']==extra_texts[fid]['text']:
            assert scores[fid]==extra_scores[fid];reused_here+=1
    assert reused_here==cache['reused_pairs']
    assert len(cache['chosen'])==cache['reused_pairs']+cache['new_pairs']
    reused+=reused_here;new+=cache['new_pairs']
    original_comparison.append({'query_id':q,'arms':{'control':original[q]['arms']['control'],'video_preserving':arm}})
verify=ROOT/'validation/recomputed';verify.mkdir(parents=True)
summary=evaluate(rankings,verify,'video_preserving');saved=read_json(out/'summary.json')
for k,v in summary.items():assert v==saved[k],k
against=ROOT/'validation/vs-pr91';against.mkdir()
original_summary=evaluate(original_comparison,against,'video_preserving');write(against/'summary.json',original_summary)
write(ROOT/'validation/accepted.json',{'status':'passed','queries':115,'scoreable':113,'source_hashes':len(sources),'cache_hashes':115,'reused_pairs_verified':reused,'new_pairs':new,'distinct_video':summary['metrics']['distinct_video'],'paired_vs_v5':summary['paired']['distinct_video'],'paired_vs_pr91':original_summary['paired']['distinct_video']})
print({'status':'passed','source_hashes':len(sources),'reused':reused,'new':new,'vs_pr91':original_summary['paired']['distinct_video']})
