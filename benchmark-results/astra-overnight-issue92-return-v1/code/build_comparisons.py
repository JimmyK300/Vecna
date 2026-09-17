"""Run after the last arm is verified. Recompute every arm against exact PR91.

Exclusive outputs: preserve this archive and choose a new version to rerun.
No retrieval, inference, truth mutation or policy selection is performed here.
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT.parent
V1 = BENCH/'astra-overnight-issue92-v1'
sys.path.insert(0, str(V1/'code'))
from architecture_common import evaluate, read_json, read_jsonl, unique_index, write


def main():
    original = unique_index(read_jsonl(V1/'outputs/packet-e/rankings.jsonl'))
    diagnostic = read_json(V1/'outputs/diagnostics-v2/arms.json')
    sources = [(f'v1/{name}', V1/'outputs'/item['folder'], item['arm'])
               for name, item in diagnostic.items()]
    folders = {2:'semantic-crossencoder', 3:'frame-text', 4:'temporal-bins',
               5:'frame-text', 6:'frame-text', 7:'', 8:'', 9:'frame-text',
               10:'frame-text', 11:'frame-text'}
    for version, folder in folders.items():
        archive = BENCH/f'astra-overnight-issue92-v{version}'
        out = archive/'outputs'/folder
        if not (out/'rankings.jsonl').exists():
            assert version == 11, f'Missing completed arm: {version}'
            continue
        arm_names = set(read_jsonl(out/'rankings.jsonl')[0]['arms']) - {'control'}
        assert len(arm_names) == 1
        sources.append((f'v{version}', out, arm_names.pop()))
    results = {}
    for label, source, arm in sources:
        rankings = read_jsonl(source/'rankings.jsonl')
        assert {r['query_id'] for r in rankings} == set(original)
        bound = [{'query_id':r['query_id'], 'arms':{
            'control':original[r['query_id']]['arms']['control'],
            arm:r['arms'][arm]}} for r in rankings]
        out = ROOT/'comparisons'/label.replace('/', '_')
        out.mkdir(parents=True, exist_ok=False)
        summary = evaluate(bound, out, arm)
        write(out/'summary.json', summary)
        results[label] = {'arm':arm, 'source':str(source.resolve()),
            'source_rankings_sha256':hashlib.file_digest((source/'rankings.jsonl').open('rb'),'sha256').hexdigest(),
            'metrics':summary['metrics']['distinct_video'][arm],
            'paired_vs_pr91':summary['paired']['distinct_video'],
            'coverage_vs_pr91':summary['coverage']}
    write(ROOT/'ALL_ARMS_VS_PR91.json', results)
    print(f'Recomputed {len(results)} arms against exact PR91; selection requires the sequential parent guardrail, not this common-control table.')


if __name__ == '__main__':
    main()
