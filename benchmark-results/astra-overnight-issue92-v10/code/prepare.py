"""Frozen modality ablation, no truth-conditioned text selection."""
from frame_text import *
V5=ROOT.parent/'astra-overnight-issue92-v5';V4=ROOT.parent/'astra-overnight-issue92-v4'
assert read_json(V5/'validation/accepted.json')['status']=='passed'
(ROOT/'inputs').mkdir()
rows=read_jsonl(V5/'inputs/frame_text.jsonl')
for r in rows:r['text']='OCR: '+r['parts']['ocr'].strip() if r['parts']['ocr'].strip() else ''
write(ROOT/'inputs/frame_text.jsonl',rows,True)
write(ROOT/'inputs/source_hashes.json',read_json(V5/'inputs/source_hashes.json'))
old=read_json(V5/'policy.json')
paths=[ROOT/'inputs/frame_text.jsonl',ROOT/'inputs/source_hashes.json',V5/'policy.json',V5/'inputs/frame_text.jsonl',V5/'outputs/frame-text/complete.json',V5/'outputs/frame-text/rankings.jsonl',V5/'validation/accepted.json',V4/'outputs/temporal-bins/rankings.jsonl',PARENT/'outputs/fusion/queries.jsonl',PARENT/'inputs/canonical_truth.jsonl',PARENT/'reference/evaluate_reranker_fusion.py',V2/'code/semantic_crossencoder.py']
paths+=list((ROOT/'code').glob('*.py'))+list((V1/'code').glob('*.py'))+list((PARENT/'code').glob('*.py'))+list((V5/'outputs/frame-text/queries').glob('*.json'))
pins={str(p):sha(p) for p in paths};pins.update({p:h for p,h in old['inputs_sha256'].items() if p.startswith(old['model_path'])})
write(ROOT/'policy.json',{'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'parent_commit':'37b321048432ccba5182a66bd39b1ca73c547537','model_path':old['model_path'],'stop_compute_utc':'2026-09-16T23:40:00+00:00','hypothesis':'Removing ASR context may reduce irrelevant text distraction; test fixed OCR-only evidence over the accepted candidate pool.','ranking':'Same temporal5s100. Protect first frame; only nonempty OCR slots2..100 permute using equal RRF60 of baseline covered rank and canonical-query/OCR score rank. Baseline tie order. No ASR fallback. Compare accepted v5 OCR+ASR.','reuse':'Only reuse v5 scores for identical query hash, frame ID, exact text and model/config. ASR-free strings only can qualify.','inference':'CPU float32 batch2 threads8 max1024, no download/embedding/extraction.','inputs_sha256':pins,'coverage':{'unique_frames':len(rows),'nonempty_ocr':sum(bool(r['text']) for r in rows)}})
write(ROOT/'frame-text-job.json',{'argv':[r'C:\Users\minhc\Code\Vecna\.venv\Scripts\python.exe','-X','utf8','-B',str(ROOT/'code/frame_text.py')],'cwd':str(ROOT.parent.parent),'timeout_seconds':4200,'next_action':'Read result/spec and v10 outputs complete/summary/rankings/per_query/115query caches. Verify frozen OCR-only transformation, all source/input/cache hashes, exactv5control,100membership/firstframe, score-reuse identities, independent ranking replay and113rescored rows. Compare exactPR91 too. Preserve all negatives. Continue substantive Issue92 research/final synthesis until original23:50Z bound; no deadline standby, no completed-job relaunch.'})
print({'policy_sha256':sha(ROOT/'policy.json'),'nonempty_ocr':sum(bool(r['text']) for r in rows)})
