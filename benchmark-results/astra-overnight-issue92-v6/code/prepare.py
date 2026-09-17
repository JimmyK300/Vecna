"""Snapshot unchanged existing text and freeze policy before deeper inference."""
import datetime
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'code'))
from frame_text import V1,V2,PARENT,sha,read_json,read_jsonl,write,unique_index,projection
from candidate_admission import admit
import numpy as np

V3=ROOT.parent/'astra-overnight-issue92-v5'
V4=ROOT.parent/'astra-overnight-issue92-v4'
(ROOT/'inputs').mkdir()
assert read_json(V3/'validation/accepted.json')['status']=='passed'
base=read_jsonl(V4/'outputs/temporal-bins/rankings.jsonl')
semantic=unique_index(read_jsonl(V1/'outputs/semantic-grounding/provider/rankings.jsonl'))
admission=[{'query_id':r['query_id'],'arms':{'admitted80plus20':projection(admit(r['arms']['temporal5s']['frames'],semantic[r['query_id']]['arms']['grounded_dense']['frames']))}} for r in base]
write(ROOT/'inputs/admission.jsonl',admission,True)
fids=sorted({f['frame_id'] for r in admission for f in r['arms']['admitted80plus20']['frames']})
features=Path(r'D:\Official-Dataset\features_L21-L30_branch-feats-siglip\features')
rows=[];sources={};missing=[]
for fid in fids:
    vid,num=fid.split('#');parts={}
    for kind in ('ocr','asr'):
        p=features/vid/num/(kind+'.npy')
        if p.exists():
            a=np.load(p,allow_pickle=False)
            assert a.shape==() and a.dtype.kind in ('U','S'),(p,a.shape,a.dtype)
            parts[kind]=str(a.item()).strip();sources[str(p)]=sha(p)
        else:parts[kind]='';missing.append(str(p))
    text='\n'.join(kind.upper()+': '+value for kind,value in parts.items() if value)
    rows.append({'frame_id':fid,'text':text,'parts':parts})
write(ROOT/'inputs/frame_text.jsonl',rows,True)
write(ROOT/'inputs/source_hashes.json',{'sha256':sources,'missing_files':missing})
previous=read_json(V3/'policy.json')
paths=[ROOT/'inputs/admission.jsonl',V1/'outputs/semantic-grounding/provider/rankings.jsonl',V3/'outputs/frame-text/rankings.jsonl',V3/'validation/accepted.json',ROOT/'inputs/frame_text.jsonl',ROOT/'inputs/source_hashes.json',V2/'code/semantic_crossencoder.py',V3/'policy.json',V3/'inputs/frame_text.jsonl',V3/'outputs/frame-text/complete.json',V4/'policy.json',V4/'outputs/temporal-bins/rankings.jsonl',V4/'outputs/temporal-bins/complete.json',V4/'validation/accepted.json',PARENT/'outputs/fusion/queries.jsonl',PARENT/'inputs/canonical_truth.jsonl',PARENT/'reference/evaluate_reranker_fusion.py']
paths+=list((ROOT/'code').glob('*.py'))+list((V1/'code').glob('*.py'))+list((PARENT/'code').glob('*.py'))+list(Path(previous['model_path']).iterdir())+list((V3/'outputs/frame-text/queries').glob('*.json'))
policy={'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'hypothesis':'Semantic candidate coverage can complement the accepted temporal5s plus protected text ranking pipeline using a fixed minority allocation.','model_path':previous['model_path'],'parent_commit':'37b321048432ccba5182a66bd39b1ca73c547537','stop_compute_utc':'2026-09-16T23:40:00+00:00','ranking':'Admit first80 temporal5s frames then first20 unique grounded semantic frames, fallback old tail if short. Same protected-first-frame text RRF60 on this admitted100. Compare to accepted v5 pipeline with unchanged100 allocation. No extra rerank pass or parameter sweep.','reuse':'Reuse v5 logits only for identical query hash, frame ID, concatenated text and identical pinned model/tokenizer/inference config. Log reused/new pair counts separately; no fabricated scores.','inference':'Local-only CPU float32, batch2, threads8, max_length1024. No embedding/extraction. New-pair token counts and timing only.','inputs_sha256':{str(p):sha(p) for p in paths if p.is_file()},'coverage':{'unique_frames':len(rows),'nonempty_text':sum(bool(r['text']) for r in rows),'source_files':len(sources),'missing_files':len(missing)}}
write(ROOT/'policy.json',policy)
spec={'argv':[r'C:\Users\minhc\Code\Vecna\.venv\Scripts\python.exe','-X','utf8','-B',str(ROOT/'code/frame_text.py')],'cwd':str(ROOT.parent.parent),'timeout_seconds':12500,'next_action':'Read result/spec and v6 outputs/frame-text complete.json summary.json rankings.jsonl per_query.jsonl and115 query caches. Verify all hashes, exact accepted v5 control, first-frame protection, 100 unique admitted membership and preserved first80 admission prefix, reused query/text/model identities and focused tests. Also compare final arm to exact PR91 control. Preserve all results. Continue substantive Issue92 accuracy research from strongest supported arm until original2026-09-16T23:50Z deadline or evidenced quota exhaustion. No deadline standby, completed-job relaunch, or log instructions.'}
write(ROOT/'frame-text-job.json',spec)
print({'policy_sha256':sha(ROOT/'policy.json'),'coverage':policy['coverage']})
