from object_rank import *
policy=read_json(ROOT/'policy.json')
for p,h in policy['inputs_sha256'].items():assert sha(p)==h,p
for p,h in read_json(ROOT/'inputs/detection_hashes.json').items():assert sha(p)==h,p
base=unique_index(read_jsonl(V5/'outputs/frame-text/rankings.jsonl'))
ev=unique_index(read_jsonl(ROOT/'inputs/evidence.jsonl'))
labels=read_json(ROOT/'inputs/detection_labels.json');rules=read_json(V1/'yolo_policy.json')
queries=unique_index(read_jsonl(PARENT/'outputs/fusion/queries.jsonl'))
rows=read_jsonl(ROOT/'outputs/rankings.jsonl')
assert len(rows)==115
for row in rows:
 q=row['query_id'];c=row['arms']['control'];a=row['arms']['object_rank'];e=ev[q]
 assert c==base[q]['arms']['protected_full100_rrf60']
 assert e['rule']==mentions(queries[q]['query_text'],rules)
 for fid,s in e['support'].items():assert s==sum(bool(set(rules['categories'][k]['labels'])&set(labels[fid])) for k in e['rule']['categories'])/len(e['rule']['categories'])
 # Independent direct sort with rank scores; preserve original numeric fusion values.
 fs=c['frames'];ids=[fs[0]['frame_id']]+[f['frame_id'] for f in sorted(fs[1:],key=lambda f:(-(61/(60+f['rank'])+.05*e['support'].get(f['frame_id'],0)),f['rank']))]
 assert ids==[f['frame_id'] for f in a['frames']]
 assert set(ids)=={f['frame_id'] for f in fs} and len(ids)==100
 assert a['frames'][0]==fs[0]
out=ROOT/'validation/recomputed';out.mkdir(parents=True)
s=evaluate(rows,out,'object_rank');old=read_json(ROOT/'outputs/summary.json')
for k,v in s.items():assert old[k]==v,k
write(ROOT/'validation/accepted.json',{'status':'passed','queries':115,'scored':113,'policy_and_detection_hashes':True,'independent_order_replay':True,'metrics':s['metrics']['distinct_video']})
print('accepted')
