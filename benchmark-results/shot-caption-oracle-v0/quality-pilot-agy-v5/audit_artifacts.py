"""Offline integrity/format audit. No inference and no semantic auto-scoring."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def classify(text, family):
    if "This request was blocked by Gemini's filters." in text:
        return 'filter_response', None
    if family == 'dense-natural':
        return 'prose_requires_manual_review', None
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and 'overview' in obj:
            return 'strict_json', obj
    except ValueError:
        pass
    # Last complete overview object is a review aid only, never raw-format acceptance.
    objects = []
    for i, char in enumerate(text):
        if char == '{':
            try:
                obj, _ = json.JSONDecoder().raw_decode(text[i:])
                if isinstance(obj, dict) and 'overview' in obj:
                    objects.append(obj)
            except ValueError:
                pass
    return ('json_with_extra_text', objects[-1]) if objects else ('invalid_output', None)

def main():
    terminal = json.loads((ROOT/'terminal.json').read_text())
    manifest = json.loads((ROOT/'manifest.json').read_text())
    assert len(terminal['records']) == 18
    assert len({(r['query_id'], r['family']) for r in terminal['records']}) == 18
    for clip in manifest['clips']:
        assert sha(clip['clip_path']) == clip['clip_sha256']
    for family, digest in manifest['prompt_sha256'].items():
        assert sha(ROOT.parent/'prompts'/f'{family}.txt') == digest
    results = []
    for record in terminal['records']:
        key = f"{record['query_id']}__{record['family']}"
        path = Path(record.get('reused_from', ROOT/'outputs'/key))
        assert sha(path/'caption.txt') == record['caption_sha256']
        assert sha(path/'request.txt') == record['request_sha256']
        events = [json.loads(s) for s in (path/'stdout.jsonl').read_text(encoding='utf8').splitlines() if s.strip()]
        calls = [e['step_update']['tool_info'] for e in events if e.get('step_update', {}).get('tool_info')]
        expected = (Path(record['sandbox'])/'clip.mp4').as_posix().lower()
        assert calls and all(c['name'] == 'view_file' and c['parameters']['AbsolutePath'].replace('\\','/').lower() == expected and not c.get('error') for c in calls)
        final = [e['result'] for e in events if e.get('event') == 'result'][-1]
        text = (path/'caption.txt').read_text(encoding='utf8')
        assert final['response'] == text and final['status'] == 'SUCCESS'
        category, obj = classify(text, record['family'])
        results.append({'query_id': record['query_id'], 'family': record['family'], 'raw_sha256': sha(path/'caption.txt'), 'source': path.relative_to(ROOT.parent).as_posix(), 'format': category, 'integrity_pass': True, 'content_acceptance': 'not_implied_by_integrity'})
        if obj:
            dest = ROOT/'review'/'parsed_for_review'
            dest.mkdir(exist_ok=True)
            (dest/f'{key}.json').write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf8')
    (ROOT/'review'/'artifact_audit.json').write_text(json.dumps(results, indent=2), encoding='utf8')
    from collections import Counter
    print(dict(Counter(r['format'] for r in results)))

if __name__ == '__main__':
    main()
