"""Assemble the final local handoff; no inference or policy search."""
import datetime
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];BENCH=ROOT.parent
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(p,v):
    with p.open('x',encoding='utf-8') as f:json.dump(v,f,indent=2)

partial=BENCH/'astra-overnight-issue92-v11'
assert read(partial/'validation/incomplete_verified.json')['status']=='INCOMPLETE_VERIFIED'
if not (partial/'ARCHIVE_MANIFEST.json').exists():
    write(partial/'ARCHIVE_MANIFEST.json',{'status':'INCOMPLETE','source_commit':'37b321048432ccba5182a66bd39b1ca73c547537',
        'branch':'codex/issue-92-overnight-20260916','uncommitted':True,
        'files':{p.relative_to(partial).as_posix():{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(partial.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}})
proof={};total=0
for i in range(1,12):
    folder=BENCH/f'astra-overnight-issue92-v{i}';manifest=folder/'ARCHIVE_MANIFEST.json';m=read(manifest)
    for name,record in m['files'].items():
        p=folder/name;digest=record if isinstance(record,str) else record['sha256']
        assert sha(p)==digest,str(p)
        if isinstance(record,dict) and 'bytes' in record:assert p.stat().st_size==record['bytes']
    size=sum(p.stat().st_size for p in folder.rglob('*') if p.is_file());total+=size
    proof[f'v{i}']={'manifest_sha256':sha(manifest),'verified_files':len(m['files']),'all_archive_bytes':size}
write(ROOT/'ARCHIVE_INTEGRITY.json',{'status':'passed','archives':proof,'archive_bytes':total,'limit_bytes':30_000_000_000})
assert total<30_000_000_000
arms=read(ROOT/'ALL_ARMS_VS_PR91.json');usage=read(ROOT/'usage_final.json')
lines=['# Vecna Issue92 overnight results','','Accepted exploratory arm: **v5, temporal5s deduplication plus protected-first full100 OCR/ASR text reranking**. All21 complete arms were re-scored against exact PR91. ASR-only v11 stopped at the planned compute cutoff with104/115 caches and is incomplete; no partial benchmark score is reported.','',
'Source: PR91 / btl/issue-82-failure-ledger-and-proposal at37b321048432ccba5182a66bd39b1ca73c547537. Research branch codex/issue-92-overnight-20260916; worktree C:/Users/minhc/Code/Vecna-issue92-overnight. No research commit, push or production merge. No remote SHA for these changes. Inherited Packet0-D inputs and ledger were reused, not rerun.','',
'## Accepted result against exact PR91','',
'Counts R1/R5/R10/R20: **49/77/85/90**, versus **49/77/82/87**. MRR@20 **0.5406434596816525**, versus0.5299890165650186; delta **+0.01065444311663386**. R20 delta **+3/113 (+2.654867 percentage points)**. Candidate accepted-video coverage92→94; complete-target coverage78→80.','',
'R20 rescues: **p2_q07, p2_q16, p3_q15, p3_q35**. Regression: **p3_q34**. MRR paired95% bootstrap interval[-0.004895938213255127,0.026729442161474538]; R20 interval[-0.008849557522123894,0.07079646017699115]. Both include zero. Repeated benchmark with no pristine holdout; exploratory point improvement, not proven generalization.','',
'100 frames retained. Original fusion scoring remains unchanged; admission uses one frame per video/time5s bin, followed by the explicitly tested protected-first text rank stage. No answer-dependent thresholds or query-specific tuning. Grounded semantic arms v6/v9 reach92/113 but lose complete-target coverage against v5 (80→79/78); neither passes the original sequential-parent guardrail.','',
'## Complete-arm table','',
'All recall counts out of113. The source control is49/77/82/87, MRR0.5299890165650186. Common-control deltas do not override each arm\'s frozen sequential-parent guardrail.','',
'| Arm | R1 | R5 | R10 | R20 | MRR20 | R20 delta | MRR delta | Complete targets |',
'|---|---:|---:|---:|---:|---:|---:|---:|---:|']
workloads={}
for label,r in arms.items():
    m=r['metrics']['metrics'];p=r['paired_vs_pr91']['metrics'];c=r['coverage_vs_pr91']['all_required_targets_present']
    lines.append('|'+label+'|'+'|'.join(str(int(m[k]['sum'])) for k in ('R@1','R@5','R@10','R@20'))+f"|{m['MRR@20']['mean']:.15f}|{p['R@20']['sum_delta']:+g}|{p['MRR@20']['mean_delta']:+.15f}|{c['arm_sum']:g}|")
    source=Path(r['source']);s=read(source/'summary.json') if (source/'summary.json').exists() else {}
    workloads[label]=s.get('workload',{})
write(ROOT/'WORKLOADS.json',workloads)
lines+=['','## Evidence and limits','',
'ALL_ARMS_VS_PR91.json contains full-precision metrics and all metric/coverage rescue and regression IDs. comparisons/ retains21 complete ranking/per-query/summary comparisons including frame/range/event layers, distinct-video layers, and paired bootstrap evidence. Prior source manifests bind runnable code, tests, configurations and immutable input paths/hashes. ARCHIVE_INTEGRITY.json verifies every manifested file in all11 archives. WORKLOADS.json preserves available arm workload records; full source summaries remain authoritative.','',
'Packet E was negative: R20 87→83, losses p1_q25,p2_q25,p3_q19,p3_q34, no rescues; complete-target coverage78→71. Existing segment mapping was too sparse; the initial padding-mismatch output is retained as invalid and excluded, with corrected segment-v2 used. Historical multimodal reranker caches did not match the current candidates, so no fresh multimodal result was fabricated.','',
'All canonical115 queries retain provenance. Scoring excludes p0_q15/p3_q09, leaving113; inherited41 provisional/proxy qualifications remain. No truth, corpus or index mutations. One permitted semantic embedding job used2956 documents+115 queries; no additional extraction/embedding job or model download. Text reranking used the existing BGE model, CPU float32, batch2, threads8, max1024. v5:10823 pair scores,8524 new/2299 reused,12 new truncated,4970.1720394 same-session seconds. Timing is noisy and not an isolated production speed comparison.','',
'v11 reached104/115 saved query caches. Partial counts and lower-bound timing are in ../astra-overnight-issue92-v11/validation/incomplete_verified.json. Work within the interrupted next query is not measured. The frozen policy prose accidentally says "v5 ASR+ASR"; executable code and input hashes reference the actual combined OCR+ASR v5 control. This prose typo is disclosed without changing the frozen policy.','',
'Focused tests and arm-specific independent verification passed as recorded in each archive. Final common-control rescoring covers21×113 scored rows and21×115 saved rankings. ASR partial verification checks source/policy hashes, exact text transformation, query ordering, finite scores and reuse identities; it is not scientific acceptance of a complete arm.','',
'## Usage, duration and transport','',
'Authorized window2026-09-16T15:50Z–23:50Z, compute cutoff23:40Z. v11 exited23:40:02Z after respecting cutoff; no new inference was launched. Closure performed within the original bound. Completion callbacks resumed the exact originating thread; terminal exit0 was verified separately from task acceptance. Earlier deadline standby was superseded by the user and substantive work resumed. All negative results remain archived.','',
'Latest harness counter delta since the last pre-start event: `'+json.dumps(usage['counter_delta_since_pre_start_event'])+'`. These counters include repeated/cached context and are not a dollar bill or exact API request count. Full rate-limit evidence, timestamps, model identifiers and source session are in usage_final.json. No quota-terminal error observed; termination reason is the time bound.','',
f'Experiment archive storage: {total} bytes, below30GB. No model downloads.','',
'## Hashes and reproduction','',
'Exact parent input SHA256: provider rankings d6223381ea8cbf4b4efcb0cc295f60dccfcae36afe0d9fac004438410c152a82; study ba47bd96eb842d0bb57811e247cbd2ea29de8794c5dd3b289dce24a3032c10b1; run identity f0d32893564111064d47f6f2f72f7b03dbb14ebbfbb3d05c48e49e30ef165755.','',
'Accepted v5 policy SHA2561ebb454de5206d425efec699933a940d4a519277a7c4a487b5f16d9e0058b867; archive manifest SHA256'+proof['v5']['manifest_sha256']+'. Full manifest hashes for all arms: ARCHIVE_INTEGRITY.json.','',
'Use the existing C:/Users/minhc/Code/Vecna/.venv/Scripts/python.exe with -X utf8 -B. Each arm README has preparation, inference and focused-test commands. code/build_comparisons.py reconstructs this common-control comparison from saved rankings. Outputs use exclusive creation; reproduce in a fresh versioned directory, never overwrite this evidence. The external model/dataset paths must still match their SHA256 pins.','',
'Dirty-state caveat: parent PUBLICATION_CHECKPOINT.json metadata changed with unknown ownership and is preserved; v1/provenance contains its snapshot/diff. The expected hydrated raw-provider and study files are untracked but hash-verified. No friend/browser branch was modified. The old v1 return selecting the control predates subsequent research and is superseded by this report.']
with (ROOT/'REPORT.md').open('x',encoding='utf-8') as f:f.write('\n'.join(lines)+'\n')
write(ROOT/'ARCHIVE_MANIFEST.json',{'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':{
    p.relative_to(ROOT).as_posix():{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(ROOT.rglob('*')) if p.is_file() and p.name!='ARCHIVE_MANIFEST.json'}})
print(json.dumps({'arms':len(arms),'archive_bytes':total,'report':str(ROOT/'REPORT.md'),'return_manifest_sha256':sha(ROOT/'ARCHIVE_MANIFEST.json')}))
