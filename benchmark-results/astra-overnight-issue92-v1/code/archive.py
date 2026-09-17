"""Build/read-only verify a bounded research archive; never rerun inference."""
import argparse
import datetime
import hashlib
import importlib.metadata
import json
import platform
import subprocess
from pathlib import Path
from architecture_common import *
from diagnostics import FOLDERS


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()


def usage():
    import os
    thread=os.environ['CODEX_THREAD_ID']
    files=list((Path.home()/'.codex/sessions/2026/09/16').glob('*'+thread+'*'))
    assert len(files)==1
    tokens=[];models=set();compactions=[]
    for line in files[0].open(encoding='utf-8'):
        x=json.loads(line);p=x.get('payload',{})
        if x.get('type')=='turn_context':models.add(str(p.get('model')))
        if x.get('type')=='compacted':compactions.append(x.get('timestamp'))
        if x.get('type')=='event_msg' and p.get('type')=='token_count':
            tokens.append({'timestamp':x.get('timestamp'),'info':p.get('info'),'rate_limits':p.get('rate_limits')})
    before=[t for t in tokens if t['timestamp']<'2026-09-16T15:50:00Z']
    baseline=before[-1] if before else None
    latest=tokens[-1] if tokens else None
    delta={}
    if baseline and latest:
        delta={k:v-baseline['info']['total_token_usage'][k] for k,v in latest['info']['total_token_usage'].items()}
    return {'captured_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'thread':thread,'source_session':str(files[0]),'models_observed':sorted(models),
        'research_start_utc':'2026-09-16T15:50:00Z','hard_deadline_utc':'2026-09-16T23:50:00Z',
        'pre_start_latest_counter':baseline,'latest_counter':latest,'counter_delta_since_pre_start_event':delta,
        'token_counter_events':len(tokens),'request_count':'unavailable; token events are not asserted to be API requests',
        'compaction_events':compactions,'quota_terminal_error':'none observed',
        'interpretation':'Harness counters include repeated/cached context and earlier transport setup in cumulative totals. Delta is bracketed by recorded events, not an exact isolated research bill. No wall-time token estimation. Dollar cost and remaining paid credits unavailable.'}


def build_report():
    arms=read_json(ROOT/'outputs/diagnostics-v2/arms.json')
    arm_bundle={'selected':'PR91 current control','promotion_gate':'R20 increases, MRR20 does not decrease, complete-target count does not decrease',
        'arms':arms,'skipped_reranker':read_json(ROOT/'outputs/reranker-compatibility/summary.json'),
        'invalid_excluded':['outputs/segment: string vs integer frame-map mismatch; corrected by segment-v2']}
    if (ROOT/'arms.json').exists():assert read_json(ROOT/'arms.json')==arm_bundle
    else:write(ROOT/'arms.json',arm_bundle)
    if not (ROOT/'usage_report.json').exists():write(ROOT/'usage_report.json',usage())
    versions={}
    for name in ['numpy','torch','transformers','sentencepiece','safetensors']:
        try:versions[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:versions[name]='unavailable'
    if not (ROOT/'runtime.json').exists():write(ROOT/'runtime.json',{'python':platform.python_version(),'platform':platform.platform(),'packages':versions,
        'device':'CPU; BGE float32 threads8; translation float32 threads8','obvious_process_at_last_inventory':'grok.exe; no Python/ffmpeg heavy worker before translation launch; not killed',
        'timing_limit':'No claim of isolated hardware or generalizable speed; one session, caches/order/contention may affect timings.'})
    reports=ROOT/'reports';reports.mkdir(exist_ok=True)
    table=['| Arm | R1 | R5 | R10 | R20 | MRR20 | Complete targets in100 | Verdict |',
           '|---|---:|---:|---:|---:|---:|---:|---|',
           '| PR91 control |49|77|82|87|0.529989016565|78|selected|']
    for folder,record in arms.items():
        name=record['arm'];metrics=record['metrics']['distinct_video'][name]['metrics'];paired=record['paired']['distinct_video']['metrics']
        values=[str(int(metrics[k]['sum'])) for k in ['R@1','R@5','R@10','R@20']]
        cov=record['coverage']
        cov={k:{**v,'arm_sum':v.get('arm_sum',v.get('e1_sum'))} for k,v in cov.items()}
        table.append('|'+folder+'|'+'|'.join(values)+f"|{metrics['MRR@20']['mean']:.12f}|{cov['all_required_targets_present']['arm_sum']}|{record['verdict']}|")
        lines=[f'# {folder}: {record["verdict"]}', '', 'All counts use113 scoreable queries;115 canonical input rows. Parent control unchanged.', '',
            f'Video metrics: {json.dumps(metrics)}', '', f'Workload: {json.dumps(record["workload"])}', '',
            'Paired changes (query bootstrap10000, seed82; exploratory, no pristine holdout):']
        for metric,d in paired.items():
            lines += ['',f'- {metric}: delta={d["mean_delta"]}; CI={d["bootstrap"]["percentile_95_ci"]}; rescues={d["improved_query_ids"]}; regressions={d["regressed_query_ids"]}.']
        for field,v in cov.items():
            lines += ['',f'- Pool {field}: {v["control_sum"]}->{v["arm_sum"]}; rescues={v["rescues"]}; regressions={v["regressions"]}.']
        lines += ['', 'All capability/truth/task/phase slices, diversity and failure classes: ../outputs/diagnostics-v2/arms.json and per_query.jsonl.',
            'Frozen frame/range/event and frame-position-video metrics remain separate in the machine-readable summary.']
        (reports/(folder.replace('/','-')+'.md')).write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (ROOT/'METRICS.md').write_text('# Exploratory results\n\nR counts are out of113; full precision and paired evidence in arms.json.\n\n'+'\n'.join(table)+'\n',encoding='utf-8')
    print('reports written',len(arms))


def manifest():
    excluded={'ARCHIVE_MANIFEST.json','CHECKPOINT.md','closing-job.json'}
    files={str(p.relative_to(ROOT)).replace('\\','/'):{'sha256':sha(p),'bytes':p.stat().st_size}
           for p in sorted(ROOT.rglob('*')) if p.is_file() and str(p.relative_to(ROOT)).replace('\\','/') not in excluded and '__pycache__' not in p.parts}
    write(ROOT/'ARCHIVE_MANIFEST.json',{'schema':'vecna92-archive-v1','source_commit':'37b321048432ccba5182a66bd39b1ca73c547537',
        'branch':'codex/issue-92-overnight-20260916','tracked_research_commit':'uncommitted checkpoint',
        'excluded_operational_files':sorted(excluded),'files':files,
        'input_contract':'Parent control_manifest hashes plus policy-specific external hashes; binary embeddings are included. New closing audit/return files may be added separately without rewriting this snapshot.'})
    print('manifest files',len(files),'bytes',sum(v['bytes'] for v in files.values()))


def verify(output):
    manifest=read_json(ROOT/'ARCHIVE_MANIFEST.json')
    for name,proof in manifest['files'].items():
        p=ROOT/name
        assert p.stat().st_size==proof['bytes'] and sha(p)==proof['sha256'],name
    pins=read_json(ROOT/'control_manifest.json')
    for name,digest in pins['sha256'].items():assert sha(PARENT/name)==digest,name
    from verify_published_ledger import verify as parent_verify
    parent=parent_verify(PARENT)
    truth=unique_index(read_jsonl(PARENT/'inputs/canonical_truth.jsonl'))
    scorer=load_scorer(PARENT/'reference/evaluate_reranker_fusion.py')
    base=unique_index(read_jsonl(ROOT/'outputs/packet-e/rankings.jsonl'))
    rows=0
    for folder in FOLDERS:
        path=ROOT/'outputs'/folder
        rankings=unique_index(read_jsonl(path/'rankings.jsonl'))
        scores=unique_index(read_jsonl(path/'per_query.jsonl'))
        assert set(rankings)==set(truth) and set(scores)=={q for q,t in truth.items() if t['scoreable']}
        for qid,result in rankings.items():
            assert result['arms']['control']==base[qid]['arms']['control']
            for name,arm in result['arms'].items():
                fs=arm['frames'];assert len(fs)<=100 and len({f['frame_id'] for f in fs})==len(fs)
                if qid in scores:assert score_arm(fs,arm['videos'],truth[qid],scorer)==scores[qid]['arms'][name]
            rows+=1
    result={'status':'passed','verified_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'archive_manifest_sha256':sha(ROOT/'ARCHIVE_MANIFEST.json'),'archive_files':len(manifest['files']),
        'parent_input_hashes':parent['published_input_files_verified'],'parent_ledger_byte_rebuild':True,
        'arms_verified':len(FOLDERS),'ranking_rows':rows,'paired_score_rows':len(FOLDERS)*113,
        'new_inference_or_retrieval_calls':0,'selected_arm':'PR91 current control'}
    if output:write(Path(output),result)
    print(json.dumps(result))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['report','manifest','verify','usage']);parser.add_argument('--output')
    args=parser.parse_args()
    if args.action=='report':build_report()
    elif args.action=='manifest':manifest()
    elif args.action=='usage':write(Path(args.output),usage())
    else:verify(args.output)
