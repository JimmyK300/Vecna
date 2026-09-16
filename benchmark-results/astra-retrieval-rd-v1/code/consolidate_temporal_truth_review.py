#!/usr/bin/env python3
"""Validate and consolidate the 31 source-review records without changing truth.

Requires jsonschema (Draft 2020-12). Run from any directory:
  python code/consolidate_temporal_truth_review.py
  python code/consolidate_temporal_truth_review.py --check

Only the consolidated ledger, validation report, and publication manifest are
written. Reviewer rows are copied verbatim, in canonical inventory order. There
is no network access, retrieval input, source-video write, or canonical rewrite.
"""
from __future__ import annotations

import argparse
from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import zipfile

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
OUT_REL = Path('outputs/temporal-truth-review')
OUT = ROOT / OUT_REL
MEDIA = OUT / 'vecna82-temporal-truth-source'
CANONICAL_SHA256 = '63f80eb6ff54ef3c623f6ae4926eba404dac8bb5543b86e31f8fa0da842b4c9f'
SCHEMA_SHA256 = '1081a213df2672cec7ae092bfffc25a1fa3201d6ae87f3fd677378308d5a2e22'
TEMPLATE_SHA256 = 'd048510cb76526f87a1fb3aca07840e3bb8e2561464bec025d1f31921f7382c0'
INDEX_SHA256 = '4bb01f83f3f133b3d94e17703f993c62aec479aeebfd0e54447188c4c856f213'
PLAN_FILE_SHA256 = '55e2797ffe9cb1a6069849acf5378cc78f552540040a4c4c554e1fd6e8f75fc6'
METADATA_FILE_SHA256 = 'fc16ea88ec93465406b07063e906798b85b8d69297ff8fc3be03f94987939e28'
ARCHIVE_PINS = {
    'source-evidence-1.zip': '4644b948ed1dfd7b4074fb43081f1a8dd7d923114527a8cb4f2066f94e872c3d',
    'source-evidence-2.zip': 'fea5ef485bec67cdd160823b65e133fc6b51e9b2f701a9e221828932aa514a6e',
}
REVIEW_FILES = ['review_p0.jsonl', 'review_p1_p2.jsonl', 'review_p3.jsonl']
MUTABLE_FIELDS = {'source_media_inspected', 'review_status', 'prior_point_disposition',
                  'proposed_locator', 'video_decision', 'event_decision',
                  'order_decision', 'source_timebase', 'review'}
BOUNDARIES = ['start_frame', 'start_time_seconds', 'end_frame', 'end_time_seconds']
POLICY_FALSE = ['canonical_truth_replaced', 'existing_scoring_contract_changed',
                'truth_tier_promoted', 'new_temporal_iou_eligibility',
                'new_event_order_metric_eligibility']


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_bytes())


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_bytes().splitlines() if line]


def json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode('utf-8')


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def checked_local_path(relative: str) -> Path:
    path = ROOT / relative
    require(not Path(relative).is_absolute(), f'Absolute artifact path: {relative}')
    require(path.resolve().is_relative_to(ROOT), f'Artifact escapes package: {relative}')
    require(path.is_file() and not path.is_symlink(), f'Missing or linked artifact: {relative}')
    return path


def main(check: bool) -> dict:
    pins = {
        ROOT / 'inputs/canonical_truth.jsonl': CANONICAL_SHA256,
        OUT / 'proposed_truth.schema.json': SCHEMA_SHA256,
        OUT / 'proposed_truth.template.jsonl': TEMPLATE_SHA256,
        MEDIA / 'evidence-index.json': INDEX_SHA256,
        OUT / 'capture_plan.json': PLAN_FILE_SHA256,
        OUT / 'source_metadata_capture_inputs.json': METADATA_FILE_SHA256,
    }
    pins.update({OUT / name: expected for name, expected in ARCHIVE_PINS.items()})
    for path, expected in pins.items():
        require(digest(path) == expected, f'Pinned input changed: {path}')
    schema = read_json(OUT / 'proposed_truth.schema.json')
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    templates = read_jsonl(OUT / 'proposed_truth.template.jsonl')
    template_by_id = {row['anchor_id']: row for row in templates}
    inventory_path = ROOT / 'outputs/dataset-audit/temporal_inventory.jsonl'
    requests_path = ROOT / 'outputs/dataset-audit/temporal_evidence_requests.jsonl'
    inventory = read_jsonl(inventory_path)
    order = [f'{q["query_id"]}:e{event["event_index"]}' for q in inventory for event in q['events']]
    require(len(order) == 31 and len(set(order)) == 31, 'Inventory must contain exactly 31 unique anchors')
    require(set(order) == set(template_by_id), 'Inventory/template anchor mismatch')
    require(len(inventory) == 8, 'Inventory must contain eight queries')
    rows, raw_rows, row_sources = {}, {}, {}
    for name in REVIEW_FILES:
        for raw in (OUT / name).read_bytes().splitlines(keepends=True):
            require(raw.endswith(b'\n') and b'\r' not in raw, f'Non-LF reviewer row in {name}')
            row = json.loads(raw)
            aid = row['anchor_id']
            require(aid not in rows, f'Duplicate reviewed anchor: {aid}')
            rows[aid], raw_rows[aid], row_sources[aid] = row, raw, name
    require(set(rows) == set(order), 'Reviewed anchors do not match the complete inventory')
    merged = [rows[aid] for aid in order]
    validator.validate(merged)
    payload = b''.join(raw_rows[aid] for aid in order)
    index = read_json(MEDIA / 'evidence-index.json')
    plan = read_json(OUT / 'capture_plan.json')
    metadata = {x['video_id']: x for x in read_json(OUT / 'source_metadata_capture_inputs.json')}
    require(index['truth_sha256'] == CANONICAL_SHA256 == plan['canonical_truth_sha256'], 'Capture truth pin mismatch')
    require(index['captured_anchor_count'] == 31 and index['retrieval_input_used'] is False, 'Capture scope is not exact source-only 31-anchor review')
    require(index['plan_sha256'] == plan['plan_sha256'], 'Capture plan digest mismatch')
    require(plan['inventory_sha256'] == digest(inventory_path), 'Capture inventory digest mismatch')
    require(index['code_sha256'] == digest(ROOT / 'code/capture_temporal_truth_media.py'), 'Executed capture code changed')
    require(index['full_source_video_hashes'] == 'not_computed', 'Unexpected full-source hash claim')
    require(len(index['queries']) == 8, 'Capture index must contain eight queries')
    query_index = {q['query_id']: q for q in index['queries']}
    event_index, assets = {}, {}
    for q in index['queries']:
        md = metadata[q['video_id']]
        require(q['metadata_blob_sha1'] == md['git_blob_sha1'], f'Metadata blob mismatch: {q["query_id"]}')
        require(q['metadata_sha256'] == md['content_sha256'], f'Metadata content pin mismatch: {q["query_id"]}')
        require(q['source_path'] == md['timing']['source_video_path'], f'Metadata source path mismatch: {q["query_id"]}')
        require(q['source_size_mtime_unchanged'] is True, f'Source stat changed: {q["query_id"]}')
        require(q['source_timebase_check'] == 'all clip frames and filmstrip samples matched observed source PTS', f'Source PTS check missing: {q["query_id"]}')
        stream = q['source_ffprobe']['streams'][0]
        require(stream['r_frame_rate'] == stream['avg_frame_rate'] == q['archived_fps'], f'FPS mismatch: {q["query_id"]}')
        current_assets = [q['filmstrip_asset']]
        for ev in q['anchor_evidence']:
            aid = ev['evidence_id']
            require(aid not in event_index, f'Duplicate captured anchor: {aid}')
            event_index[aid] = ev
            current_assets += [ev['motion_clip'], *ev['adjacent_frames']]
            clip = ev['motion_clip']
            require(clip['all_source_frames_retained'] is True, f'Clip drops source frames: {aid}')
            require(clip['source_frames_inclusive'] == clip['end_source_frame'] - clip['start_source_frame'] + 1, f'Clip count mismatch: {aid}')
        for asset in current_assets:
            path = checked_local_path(relative(MEDIA / asset['path']))
            require(path.stat().st_size == asset['bytes'], f'Asset byte count mismatch: {path}')
            require(digest(path) == asset['sha256'], f'Asset hash mismatch: {path}')
            key = relative(path)
            require(key not in assets, f'Duplicate media asset: {key}')
            assets[key] = asset
    require(set(event_index) == set(order), 'Captured anchors do not match reviewed anchors')
    require(len(assets) == 132, 'Expected exactly 132 media assets')
    captured_files = {relative(p) for p in MEDIA.rglob('*') if p.is_file()}
    index_rel = relative(MEDIA / 'evidence-index.json')
    require(captured_files == set(assets) | {index_rel}, 'Unmanifested or missing capture files')
    expected_members = {(ROOT / rel).relative_to(OUT).as_posix(): rel for rel in captured_files}
    archives, seen_members = [], set()
    for name in ARCHIVE_PINS:
        archive_path = OUT / name
        require(archive_path.stat().st_size < 8_000_000, f'Archive exceeds publication binary-size budget: {name}')
        archive_members = []
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
            require(names and len(names) == len(set(names)), f'Empty archive or duplicate archive members: {name}')
            require(set(names) <= set(expected_members), f'Unexpected source archive members: {name}')
            require(not seen_members.intersection(names), f'Source archives overlap: {name}')
            seen_members.update(names)
            for member in sorted(names):
                rel = expected_members[member]
                info = archive.getinfo(member)
                require(info.flag_bits & 1 == 0, f'Encrypted source archive member: {member}')
                require(not info.is_dir(), f'Unexpected source archive directory: {member}')
                expected_sha = assets[rel]['sha256'] if rel in assets else INDEX_SHA256
                expected_bytes = assets[rel]['bytes'] if rel in assets else (ROOT / rel).stat().st_size
                require(info.file_size == expected_bytes, f'Archive member byte mismatch: {member}')
                require(hashlib.sha256(archive.read(member)).hexdigest() == expected_sha, f'Archive member hash mismatch: {member}')
                archive_members.append({'member': member, 'unpacked_path': rel, 'bytes': expected_bytes, 'sha256': expected_sha})
        archives.append({'path': relative(archive_path), 'sha256': digest(archive_path), 'bytes': archive_path.stat().st_size, 'extract_into': OUT_REL.as_posix(), 'members': archive_members})
    require(seen_members == set(expected_members) and len(seen_members) == 133, 'Source archive union must contain each exact capture member once')
    evidence_paths = set()
    for row in merged:
        aid = row['anchor_id']
        prior = template_by_id[aid]
        for key, value in prior.items():
            if key not in MUTABLE_FIELDS:
                require(row[key] == value, f'Immutable field changed: {aid}.{key}')
        for key in ['previous_anchor_id', 'next_anchor_id']:
            require(row['order_decision'][key] == prior['order_decision'][key], f'Canonical event order changed: {aid}')
        for key in POLICY_FALSE:
            require(row['metric_policy'][key] is False, f'Truth/metric promotion: {aid}.{key}')
        require(row['metric_policy']['evaluation_use'] == 'REVIEW_ONLY_NOT_SCORING_INPUT', f'Scoring input promotion: {aid}')
        require(row['review_status'] == 'SOURCE_MEDIA_REVIEWED' and row['source_media_inspected'] is True, f'Unreviewed source anchor: {aid}')
        require(row['review']['filmstrip_inspected'] is True and row['review']['motion_clip_inspected'] is True, f'Missing visual or motion review: {aid}')
        require(row['event_decision']['first_occurrence_verified'] is not True, f'Unsupported first occurrence promotion: {aid}')
        require(row['order_decision']['proposed_event_index'] is None, f'Reordered event: {aid}')
        loc = row['proposed_locator']
        require(loc['kind'] in ['point', 'unknown'], f'Unexpected promoted locator: {aid}')
        require(all(loc[key] is None for key in BOUNDARIES), f'Invented interval boundary: {aid}')
        require(row['review']['coverage']['original_request_fulfilled'] is False, f'False ±15-second coverage claim: {aid}')
        q, ev = query_index[row['query_id']], event_index[aid]
        require(q['canonical_query'] == row['canonical_query'] and q['canonical_query_sha256'] == row['canonical_query_sha256'], f'Query identity changed: {aid}')
        require(hashlib.sha256(row['canonical_query'].encode('utf-8')).hexdigest() == row['canonical_query_sha256'], f'Query hash invalid: {aid}')
        require(q['video_id'] == row['prior_anchor']['video_id'] and ev['prior_anchor']['frame'] == row['prior_anchor']['point_frame'], f'Prior source point mismatch: {aid}')
        require(row['canonical_source']['temporal_inventory_sha256'] == digest(inventory_path), f'Inventory lineage mismatch: {aid}')
        require(row['canonical_source']['evidence_requests_sha256'] == digest(requests_path), f'Evidence-request lineage mismatch: {aid}')
        fps = Fraction(q['source_ffprobe']['streams'][0]['avg_frame_rate'])
        tb = Fraction(q['source_ffprobe']['streams'][0]['time_base'])
        st = row['source_timebase']
        require(st['status'] == 'VERIFIED' and st['source_video_id'] == q['video_id'], f'Unverified source timebase: {aid}')
        require(Fraction(st['fps_numerator'], st['fps_denominator']) == fps, f'Review FPS mismatch: {aid}')
        require(Fraction(st['time_base_numerator'], st['time_base_denominator']) == tb, f'Review time-base mismatch: {aid}')
        require(st['frame_numbering'] == 'zero_based_decoded_frame_index', f'Wrong source frame numbering: {aid}')
        for art in row['review']['evidence_artifacts']:
            path = checked_local_path(art['path'])
            require(digest(path) == art['sha256'], f'Review evidence hash mismatch: {aid}:{art["path"]}')
            require(art['inspected'] is True, f'Uninspected claimed artifact: {aid}:{art["path"]}')
            require(art['path'] in assets or art['path'] == index_rel, f'Unexpected review evidence authority: {aid}:{art["path"]}')
            evidence_paths.add(art['path'])
        row_evidence_paths = {art['path'] for art in row['review']['evidence_artifacts']}
        own_required_paths = {index_rel, relative(MEDIA / q['filmstrip_asset']['path']), relative(MEDIA / ev['motion_clip']['path'])}
        own_required_paths.update(relative(MEDIA / a['path']) for a in ev['adjacent_frames'])
        require(own_required_paths <= row_evidence_paths, f'Review row lacks its own source evidence: {aid}: {sorted(own_required_paths - row_evidence_paths)}')
        require(aid in row['review']['reviewed_evidence_ids'], f'Review row does not identify its own inspected anchor: {aid}')
        if loc['kind'] == 'point':
            frame = row['prior_anchor']['point_frame']
            require(loc['video_id'] == row['prior_anchor']['video_id'] and loc['point_frame'] == frame, f'Unaccepted point correction: {aid}')
            require(abs(loc['point_time_seconds'] - float(Fraction(frame) / fps)) < 1e-9, f'Proposed point time mismatch: {aid}')
            require(row['event_decision']['status'] == 'CONFIRMED_PRIOR_POINT', f'Inconsistent representative point: {aid}')
            for role, delta in [('before', -1), ('at', 0), ('after', 1)]:
                adjacent = row['review']['adjacent_frame_evidence']['point'][role]
                actual = next(x for x in ev['adjacent_frames'] if x['source_frame'] == frame + delta)
                require(adjacent['frame'] == actual['source_frame'] and adjacent['source_pts'] == actual['source_pts_ticks'], f'Wrong adjacent source frame/PTS: {aid}:{role}')
    require(evidence_paths == captured_files, 'Every captured media asset/index must be accounted for by reviewer evidence')
    require(digest(ROOT / 'inputs/canonical_truth.jsonl') == CANONICAL_SHA256, 'Canonical truth changed during validation')
    counts = Counter(row['proposed_locator']['kind'] for row in merged)
    per_query = []
    for q in inventory:
        qr = [row for row in merged if row['query_id'] == q['query_id']]
        qi = query_index[q['query_id']]
        per_query.append({'query_id': q['query_id'], 'video_id': qi['video_id'], 'source_media_reviewed': len(qr), 'events': len(qr), 'representative_points': sum(r['proposed_locator']['kind'] == 'point' for r in qr), 'unknown_locators': sum(r['proposed_locator']['kind'] == 'unknown' for r in qr), 'video_statuses': sorted({r['video_decision']['status'] for r in qr}), 'order_statuses_as_reviewed': sorted({r['order_decision']['status'] for r in qr}), 'filmstrip': relative(MEDIA / qi['filmstrip_asset']['path'])})
    validation = {
        'schema': 'temporal-source-review-validation-v2', 'status': 'PASS',
        'validator': 'jsonschema.Draft202012Validator + FormatChecker',
        'canonical_truth_sha256': CANONICAL_SHA256, 'canonical_truth_unchanged': True,
        'schema_sha256': SCHEMA_SHA256, 'template_sha256': TEMPLATE_SHA256,
        'evidence_index_sha256': INDEX_SHA256,
        'source_archives': [{key: value for key, value in archive.items() if key != 'members'} | {'exact_members_verified': len(archive['members'])} for archive in archives],
        'merged_ledger_sha256': hashlib.sha256(payload).hexdigest(),
        'review_rows_copied_verbatim': True, 'canonical_inventory_order': order,
        'review_inputs': [{'path': (OUT_REL / n).as_posix(), 'sha256': digest(OUT / n), 'rows': sum(v == n for v in row_sources.values())} for n in REVIEW_FILES],
        'counts': {'queries': 8, 'anchors': 31, 'source_media_reviewed': 31,
                   'representative_points': counts['point'], 'unknown_locators': counts['unknown'],
                   'intervals': 0, 'first_occurrence_certifications': 0, 'truth_promotions': 0,
                   'new_event_order_metric_eligibility': 0, 'new_temporal_iou_eligibility': 0,
                   'verified_media_assets': len(assets), 'verified_capture_files_including_index': len(captured_files)},
        'checks': {'formal_full_schema': True, 'immutable_fields': True, 'query_hashes': True,
                   'canonical_point_identity': True, 'all_media_hashes_and_bytes': True,
                   'all_review_artifact_hashes': True, 'proposed_point_source_pts_neighbors': True,
                   'each_row_contains_own_clip_filmstrip_neighbors_index': True,
                   'archive_exact_member_names_hashes_and_bytes': True,
                   'archive_union_exact_133_without_overlap': True,
                   'each_archive_under_8000000_bytes': True,
                   'metadata_and_timebase_pins': True, 'null_interval_boundaries': True,
                   'no_truth_or_metric_promotion': True, 'retrieval_independent_capture': True,
                   'capture_code_matches_executed_sha256': True},
        'per_query': per_query,
        'scope_note': 'Source inspection is complete for all captured anchors. Exact first occurrence, unresolved semantics, and organizer adjudication are not claimed. P0 order confirmations refer only to inspected passage order; no new order metric eligibility is granted.',
    }
    generated = {OUT / 'proposed_truth.reviewed.jsonl': payload,
                 OUT / 'source_review_validation.json': json_bytes(validation)}
    selected = {
        ROOT / 'code/capture_temporal_truth_media.py': 'executed_source_capture_code',
        Path(__file__).resolve(): 'review_consolidation_and_validation_code',
        ROOT / 'code/dataset_audit.py': 'mechanical_inventory_producer',
        ROOT / 'inputs/canonical_truth.jsonl': 'frozen_canonical_truth_reference_not_modified',
        ROOT / 'inputs/temporal_truth_media_broker.json': 'verified_capture_transport_receipt',
        inventory_path: 'frozen_mechanical_inventory', requests_path: 'frozen_evidence_requests',
    }
    for name in ['capture_plan.json', 'source_metadata_capture_inputs.json', 'proposed_truth.schema.json', 'proposed_truth.template.jsonl', *REVIEW_FILES, 'REVIEW_P0.md', 'REVIEW_P1_P2.md', 'REVIEW_P3.md', 'SOURCE_REVIEW.md', 'proposed_truth.reviewed.jsonl', 'source_review_validation.json']:
        selected[OUT / name] = 'source_review_codebook_ledger_or_report'
    # Two independent archives preserve the exact capture member union while
    # staying below the connector request limit after base64 encoding.
    # Keep eight filmstrips directly accessible at the original paths.
    selected.update({OUT / name: 'lossless_source_media_and_index_archive_part' for name in ARCHIVE_PINS})
    selected.update({MEDIA / q['filmstrip_asset']['path']: 'direct_query_filmstrip_preview' for q in index['queries']})
    entries = []
    for path in sorted(selected, key=relative):
        data = generated[path] if path in generated else path.read_bytes()
        entries.append({'path': relative(path), 'role': selected[path], 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    manifest = {
        'schema': 'temporal-source-review-publication-manifest-v2',
        'purpose': 'Durable source review supporting JimmyK300/official-dataset-control#16 and JimmyK300/Vecna#82; review only, no canonical repair.',
        'path_base': 'benchmark-results/astra-retrieval-rd-v1 in the Vecna working branch, or this package root',
        'canonical_truth_sha256': CANONICAL_SHA256,
        'media_files': len(assets), 'capture_files_including_index': len(captured_files),
        'source_media_bytes': sum(a['bytes'] for a in assets.values()),
        'selected_file_count_excluding_this_manifest': len(entries),
        'selected_bytes_excluding_this_manifest': sum(e['bytes'] for e in entries),
        'publish_manifest_itself': (OUT_REL / 'source_publication_manifest.json').as_posix(),
        'self_hash_policy': 'This manifest is included in publication but does not recursively hash itself. The final Git tree/commit identifies it.',
        'no_canonical_replacement': True, 'no_full_source_video_copies': True,
        'no_retrieval_outputs_required_for_review': True,
        'transport': 'Two independent lossless ZIP archives, each under 8,000,000 binary bytes, whose nonoverlapping union contains all 133 capture files. Extract both into the same directory. Eight filmstrips are also published directly at their original paths.',
        'archives': archives,
        'extraction_commands_from_package_root': [f'python -m zipfile -e {(OUT_REL / name).as_posix()} {OUT_REL.as_posix()}' for name in ARCHIVE_PINS],
        'excluded_local_intermediates': [(OUT_REL / 'source-evidence.zip').as_posix()],
        'gitignore_note': 'Keep this exact manifest list when staging. The repository data*/ rule can ignore outputs/dataset-audit/; the two frozen inventory/request references are intentional publication inputs and must be force-added if ignored. outputs/temporal-truth-review/ is the source-media prefix.',
        'files': entries,
    }
    generated[OUT / 'source_publication_manifest.json'] = json_bytes(manifest)
    for path, data in generated.items():
        if check:
            require(path.is_file() and path.read_bytes() == data, f'Generated artifact is stale: {path}')
        else:
            path.write_bytes(data)
    # Relative evidence links in the consolidated report must resolve locally.
    report = (OUT / 'SOURCE_REVIEW.md').read_text(encoding='utf-8')
    for target in re.findall(r'\]\(([^)]+)\)', report):
        if '://' not in target and not target.startswith('#'):
            require((OUT / target).is_file(), f'Broken report link: {target}')
    return {'status': 'PASS', 'check_only': check, 'counts': validation['counts'],
            'merged_ledger_sha256': validation['merged_ledger_sha256'],
            'selected_publication_files_plus_manifest': len(entries) + 1,
            'selected_bytes_excluding_manifest': manifest['selected_bytes_excluding_this_manifest']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Validate and fail if consolidated outputs or manifest are stale; write nothing.')
    args = parser.parse_args()
    print(json.dumps(main(args.check), ensure_ascii=False, sort_keys=True))
