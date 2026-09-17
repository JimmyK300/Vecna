"""Read-only scientific acceptance; no inference or answer-aware repair."""
from query_rank import *
out=ROOT/'outputs';policy=read_json(ROOT/'policy.json');complete=read_json(out/'complete.json')
assert complete['policy_sha256']==sha(ROOT/'policy.json')
for p,h in policy['inputs_sha256'].items():assert sha(p)==h,p
sources=read_json(V5/'inputs/source_hashes.json')['sha256']
for p,h in sources.items():assert sha(p)==h,p
for p,h in complete['query_files_sha256'].items():assert sha(p)==h,p
for n in ('summary','rankings'):assert sha(out/(n+'.json'+('l' if n=='rankings' else '')))==complete[n+'_sha256']
qs=unique_index(read_jsonl(ROOT/'inputs/queries.jsonl'))
translations=unique_index(read_jsonl(V1/'outputs/query-translation/queries.jsonl'))
base=unique_index(read_jsonl(V4/'outputs/temporal-bins/rankings.jsonl'))
best=unique_index(read_jsonl(V5/'outputs/frame-text/rankings.jsonl'))
original=unique_index(read_jsonl(V1/'outputs/packet-e/rankings.jsonl'))
texts=unique_index(read_jsonl(V5/'inputs/frame_text.jsonl'),field='frame_id')
rows=read_jsonl(out/'rankings.jsonl');assert len(rows)==len(complete['query_files_sha256'])==115
pr=[]
for r in rows:
 q=r['query_id'];query=qs[q];t=translations[q]
 assert query['text']==t['texts'][1] and query['canonical_sha256']==t['canonical_sha256']
 assert query['variant_sha256']==hashlib.sha256(query['text'].encode('utf-8')).hexdigest()
 cache=read_json(out/'queries'/f'{q}.json');old=read_json(V5/'outputs/frame-text/queries'/f'{q}.json')
 assert cache['chosen']==old['chosen'] and cache['canonical_sha256']==old['query_text_sha256'] and cache['variant_sha256']==query['variant_sha256']
 assert len(cache['chosen'])==len(cache['logits'])==cache['new_pairs'] and cache['reused_pairs']==0
 assert len(cache['token_counts'])==cache['new_pairs'] and sum(n>1024 for n in cache['token_counts'])==cache['truncated_pairs']
 fs=base[q]['arms']['temporal5s']['frames'];ids=cache['chosen'];positions={fid:i for i,fid in enumerate(ids)}
 assert ids==[f['frame_id'] for f in fs[1:] if texts[f['frame_id']]['text'].strip()]
 cr=sorted(ids,key=lambda fid:(-old['logits'][positions[fid]],positions[fid]))
 er=sorted(ids,key=lambda fid:(-cache['logits'][positions[fid]],positions[fid]))
 fused={fid:1/(61+positions[fid])+.5*(1/(61+cr.index(fid))+1/(61+er.index(fid))) for fid in ids}
 ranked=iter(sorted(ids,key=lambda fid:(-fused[fid],positions[fid])))
 final=[next(ranked) if i>0 and f['frame_id'] in positions else f['frame_id'] for i,f in enumerate(fs)]
 a=r['arms']['query_variant'];assert final==[f['frame_id'] for f in a['frames']]
 assert r['arms']['control']==best[q]['arms']['protected_full100_rrf60']
 assert a['frames'][0]==fs[0] and set(final)=={f['frame_id'] for f in fs} and len(final)==100
 pr.append({'query_id':q,'arms':{'control':original[q]['arms']['control'],'query_variant':a}})
validation=ROOT/'validation/recomputed';validation.mkdir(parents=True)
s=evaluate(rows,validation,'query_variant');saved=read_json(out/'summary.json')
for k,v in s.items():assert saved[k]==v,k
versus=ROOT/'validation/vs-pr91';versus.mkdir()
p=evaluate(pr,versus,'query_variant');write(versus/'summary.json',p)
write(ROOT/'validation/accepted.json',{'status':'passed','query_rows':115,'scored_rows':113,'source_hashes':len(sources),'cache_hashes':115,'independent_rank_replay':True,'metrics':s['metrics']['distinct_video'],'paired_vs_v5':s['paired']['distinct_video'],'paired_vs_pr91':p['paired']['distinct_video']})
print({'status':'passed','metrics':s['metrics']['distinct_video'],'paired':s['paired']['distinct_video'],'workload':saved['workload']})
