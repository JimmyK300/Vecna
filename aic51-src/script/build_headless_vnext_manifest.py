#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'benchmark-results' / 'issue63-stage-b' / 'reconstructed-truth.json'
AUTHORITY = ROOT / 'benchmark-results' / 'headless-vnext' / 'canonical-query-texts.json'
OUT = ROOT / 'benchmark-results' / 'headless-vnext' / 'manifest.json'
EXPECTED_SOURCE_SHA256 = '92a4c14cdb075f43a444e7e105cc7680a491188e307cfe2562fff2b51cfe6603'
EXPECTED_AUTHORITY_SHA256 = '512c5a0f1dc44ef4318d2205dd76a7c80af7be797c9450764c51854e40a55c9c'
ODC_COMMIT = '646ec85c75141bb68078fa94ec26b9a1dbef6d04'
ISSUE63_HEAD = 'ec4a38d397c9a3a49a821812b37db47f52327049'
ISSUE75_CONTRACT = '2344023ea4e2a152d1e9dc15778d8feb436dc396'
SOURCE_MAP = {
    'testing88_submission633': {
        'canonical_source_id': 'test_round_8_8', 'operational_phase': 'P0',
        'official_dataset_control_path': 'Official-Queries/current-rounds/p0-test-round-8.8.md',
        'official_dataset_control_blob_sha': '7d1688f94ba6a47eee9f6e2928c1ce52fe91f181',
        'query_text_path': 'Official-Queries/aic-2025/preliminary-groupA-p1.md',
        'query_text_blob_sha': '7c05c0e27b91739a62b802327f8cd131c013af6c',
    },
    'final_round1_10_4of13': {
        'canonical_source_id': 'actual_p1_10_4', 'operational_phase': 'P1',
        'official_dataset_control_path': 'Official-Queries/current-rounds/p1-actual-round-10.4.md',
        'official_dataset_control_blob_sha': '2e56009d2a2fd09ead2b468a2394b3434417953e',
        'query_text_path': 'Official-Queries/current-rounds/p1-actual-round-10.4.md',
        'query_text_blob_sha': '2e56009d2a2fd09ead2b468a2394b3434417953e',
    },
}

def sha256_bytes(data: bytes) -> str: return hashlib.sha256(data).hexdigest()
def sha256_text(text: str) -> str: return sha256_bytes(text.encode('utf-8'))

def load_authority(authority_path: Path = AUTHORITY) -> tuple[dict[str, Any], str]:
    raw = authority_path.read_bytes()
    digest = sha256_bytes(raw)
    if digest != EXPECTED_AUTHORITY_SHA256:
        raise ValueError(f'canonical query-text projection hash mismatch: {digest}')
    doc = json.loads(raw)
    if doc.get('official_dataset_control_commit') != ODC_COMMIT:
        raise ValueError('canonical query-text projection is not pinned to the reconciled ODC commit')
    for sm in SOURCE_MAP.values():
        source_id = sm['canonical_source_id']
        source = doc.get('sources', {}).get(source_id)
        if not source:
            raise ValueError(f'missing authority source metadata: {source_id}')
        expected = {
            'registry_path': sm['official_dataset_control_path'],
            'registry_blob_sha': sm['official_dataset_control_blob_sha'],
            'query_text_path': sm['query_text_path'],
            'query_text_blob_sha': sm['query_text_blob_sha'],
        }
        for key, value in expected.items():
            if source.get(key) != value:
                raise ValueError(f'authority source metadata mismatch {source_id}.{key}: {source.get(key)!r} != {value!r}')
    queries = doc.get('queries', {})
    p0 = queries.get('test_round_8_8', {})
    p1 = queries.get('actual_p1_10_4', {})
    if len(p0) != 23 or len(p1) != 25:
        raise ValueError(f'authority query count mismatch: P0={len(p0)} P1={len(p1)}')
    return doc, digest

def build(source_path: Path = SOURCE, authority_path: Path = AUTHORITY) -> dict[str, Any]:
    raw = source_path.read_bytes()
    digest = sha256_bytes(raw)
    if digest != EXPECTED_SOURCE_SHA256:
        raise ValueError(f'Issue #63 reconstructed truth hash mismatch: {digest}')
    source_doc = json.loads(raw)
    authority_doc, authority_digest = load_authority(authority_path)
    authoritative_queries = authority_doc['queries']
    records = []
    used_authority_ids: set[str] = set()
    for row in source_doc['records']:
        if not row.get('scoreable'):
            continue
        prov = row['source_qualified_id']
        source_id = row['source_submission']
        if source_id not in SOURCE_MAP:
            raise ValueError(f'unmapped Issue #63 source: {source_id}')
        sm = SOURCE_MAP[source_id]
        canonical_source_id = sm['canonical_source_id']
        raw_query_id = row['query_id']
        canonical_query_id = f'{canonical_source_id}::{raw_query_id}'
        authority_entry = authoritative_queries.get(canonical_source_id, {}).get(raw_query_id)
        if authority_entry is None:
            raise ValueError(f'missing authoritative query text: {canonical_query_id}')
        task = str(row.get('task_type') or '').lower()
        authoritative_task = str(authority_entry.get('task_type') or '').lower()
        if authoritative_task != task:
            raise ValueError(f'authoritative task-type mismatch {canonical_query_id}: {authoritative_task} != {task}')
        text = str(authority_entry.get('query_text') or '')
        if not text.strip():
            raise ValueError(f'empty authoritative query text: {canonical_query_id}')
        used_authority_ids.add(canonical_query_id)

        is_trake = task == 'trake'
        anchors = [int(x) for x in (row.get('submitted_anchor_frames') or [])]
        event_truth = []
        if is_trake:
            if not anchors:
                raise ValueError(f'TRAKE anchors unavailable: {prov}')
            event_truth = [
                {
                    'event_index': i + 1,
                    'submitted_frame': f,
                    'proxy_window': {'start_frame': max(0, f - 5), 'end_frame': f + 25},
                    'truth_tier': 'provisional_submission_anchor',
                    'truth_note': 'Submission-derived development proxy; not organizer GT and replaceable by reviewed event truth.',
                }
                for i, f in enumerate(anchors)
            ]
        record = {
            'canonical_query_id': canonical_query_id,
            'operational_phase': sm['operational_phase'],
            'canonical_source_id': canonical_source_id,
            'vecna_provenance_id': prov,
            'raw_query_id': raw_query_id,
            'task_type': task,
            'query_text': text,
            'query_text_sha256': sha256_text(text),
            'accepted_video_id': row['video_id'],
            'accepted_ranges': [] if is_trake else row.get('reviewed_ranges', []),
            'reviewed_semantic_ranges_preserved': row.get('reviewed_ranges', []) if is_trake else None,
            'trake_event_truth': event_truth,
            'scoreability': {'video': True, 'range': not is_trake, 'trake_event': is_trake, 'qa_answer': False},
            'qa_answer': {'status': 'not_evaluated'},
            'provenance': {
                'issue63_truth_commit': ISSUE63_HEAD,
                'issue63_truth_path': 'benchmark-results/issue63-stage-b/reconstructed-truth.json',
                'issue63_truth_sha256': EXPECTED_SOURCE_SHA256,
                'issue63_segment_source_path': row.get('segment_source_path'),
                'issue63_segment_source_sha256': row.get('segment_source_sha256'),
                'source_csv': row.get('source_csv'),
                'source_csv_sha256': row.get('source_csv_sha256'),
                'submitted_anchor_frames': anchors,
                'official_dataset_control_commit': ODC_COMMIT,
                'official_dataset_control_path': sm['official_dataset_control_path'],
                'official_dataset_control_blob_sha': sm['official_dataset_control_blob_sha'],
                'official_dataset_control_query_text_path': sm['query_text_path'],
                'official_dataset_control_query_text_blob_sha': sm['query_text_blob_sha'],
                'canonical_query_text_projection_path': str(AUTHORITY.relative_to(ROOT)).replace('\\', '/'),
                'canonical_query_text_projection_sha256': authority_digest,
            },
        }
        records.append(record)
    records.sort(key=lambda r: r['canonical_query_id'])
    expected_authority_ids = {
        f'{source_id}::{raw_id}'
        for source_id, queries in authoritative_queries.items()
        for raw_id in queries
    }
    if used_authority_ids != expected_authority_ids:
        missing = sorted(expected_authority_ids - used_authority_ids)
        extra = sorted(used_authority_ids - expected_authority_ids)
        raise ValueError(f'authority coverage mismatch: missing={missing} extra={extra}')
    counts = {
        'execution_rows': len(records),
        'video_scoreable': sum(r['scoreability']['video'] for r in records),
        'range_scoreable_non_trake': sum(r['scoreability']['range'] for r in records),
        'trake_rows': sum(r['scoreability']['trake_event'] for r in records),
        'p0_rows': sum(r['operational_phase'] == 'P0' for r in records),
        'p1_rows': sum(r['operational_phase'] == 'P1' for r in records),
        'p2_rows': sum(r['operational_phase'] == 'P2' for r in records),
        'trake_events': sum(len(r['trake_event_truth']) for r in records),
    }
    expected = {'execution_rows': 48, 'video_scoreable': 48, 'range_scoreable_non_trake': 44, 'trake_rows': 4, 'p0_rows': 23, 'p1_rows': 25, 'p2_rows': 0}
    for k, v in expected.items():
        if counts[k] != v: raise ValueError(f'count invariant failed {k}: {counts[k]} != {v}')
    ids = [r['canonical_query_id'] for r in records]
    provs = [r['vecna_provenance_id'] for r in records]
    if len(ids) != len(set(ids)) or len(provs) != len(set(provs)):
        raise ValueError('manifest identities are not unique')
    return {
        'schema_version': 2,
        'benchmark_id': 'headless-main-vnext-p0-p1-v1',
        'purpose': 'Frozen 48-row P0/P1 scoring manifest for retrieval-independent Headless vNext.',
        'contract_commit': ISSUE75_CONTRACT,
        'issue63_truth': {'commit': ISSUE63_HEAD, 'path': str(SOURCE.relative_to(ROOT)).replace('\\','/'), 'sha256': EXPECTED_SOURCE_SHA256},
        'query_text_authority': {
            'projection_path': str(AUTHORITY.relative_to(ROOT)).replace('\\', '/'),
            'projection_sha256': authority_digest,
            'official_dataset_control_commit': ODC_COMMIT,
            'sources': authority_doc['sources'],
        },
        'official_dataset_control': {'commit': ODC_COMMIT},
        'trake_proxy_contract': {'window_offsets_frames': [-5, 25], 'truth_tier': 'provisional_submission_anchor', 'organizer_ground_truth': False},
        'counts': counts,
        'records': records,
    }

def main() -> int:
    doc = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(doc['counts'], sort_keys=True))
    return 0
if __name__ == '__main__': raise SystemExit(main())
