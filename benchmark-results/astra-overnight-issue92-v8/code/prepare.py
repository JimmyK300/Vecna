from query_rank import *
assert read_json(V5/'validation/accepted.json')['status']=='passed'
(ROOT/'inputs').mkdir()
source=V1/'outputs/query-translation/queries.jsonl'
queries=[]
for q in read_jsonl(source):
    text=q['texts'][1] if len(q['texts'])>1 else q['texts'][0]
    queries.append({'query_id':q['query_id'],'canonical_sha256':q['canonical_sha256'],'text':text,'variant_sha256':hashlib.sha256(text.encode('utf-8')).hexdigest(),'fallback':len(q['texts'])<2})
write(ROOT/'inputs/queries.jsonl',queries,True)
old=read_json(V5/'policy.json')
paths=[source,ROOT/'inputs/queries.jsonl',V5/'policy.json',V5/'inputs/frame_text.jsonl',V5/'inputs/source_hashes.json',V5/'outputs/frame-text/rankings.jsonl',V5/'outputs/frame-text/complete.json',V5/'validation/accepted.json',V4/'outputs/temporal-bins/rankings.jsonl',PARENT/'inputs/canonical_truth.jsonl',PARENT/'reference/evaluate_reranker_fusion.py']
paths+=list((ROOT/'code').glob('*.py'))+list((V5/'outputs/frame-text/queries').glob('*.json'))+list((V1/'code').glob('*.py'))+list((PARENT/'code').glob('*.py'))+[ROOT.parent/'astra-overnight-issue92-v2/code/semantic_crossencoder.py']
pins={str(p):sha(p) for p in paths}
pins.update({p:h for p,h in old['inputs_sha256'].items() if p.startswith(old['model_path'])})
write(ROOT/'policy.json',{'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'parent_commit':'37b321048432ccba5182a66bd39b1ca73c547537','model_path':old['model_path'],'hypothesis':'A fixed English reformulation may complement canonical-query matching to OCR/ASR text.','rule':'Same temporal5s100 and protected first frame. RRF60 baseline weight1; canonical logit rank weight0.5; first cached English translation logit rank weight0.5. Stable baseline tie order. Missing text fixed. No parameter/query-specific sweep. No repeated rerank.','inference':'CPU float32 batch2 threads8 max1024 local-only. Canonical scores reused, English scores new. No translation or embeddings/extraction.','stop_compute_utc':'2026-09-16T23:40:00+00:00','inputs_sha256':pins})
write(ROOT/'job.json',{'argv':[r'C:\Users\minhc\Code\Vecna\.venv\Scripts\python.exe','-X','utf8','-B',str(ROOT/'code/query_rank.py')],'cwd':str(ROOT.parent.parent),'timeout_seconds':11000,'next_action':'Read result.json/spec.json and v8 outputs complete/summary/rankings/per_query/115query caches. Verify all policy/cache/model/source/query variant identities, exact v5 control, preserved first frame and100 membership, independent RRF replay and113score rows. Compare to exact PR91 too. Preserve negative findings. Continue Issue92 from strongest supported arm until original23:50Z deadline or evidenced quota exhaustion; no deadline standby or completed-job relaunch.'})
print({'policy_sha256':sha(ROOT/'policy.json'),'queries':len(queries),'fallback':sum(q['fallback'] for q in queries)})
