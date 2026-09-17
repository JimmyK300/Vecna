import datetime
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
assert json.loads((root/'validation/accepted.json').read_text())['status'] == 'passed'
files = {}
for path in sorted(root.rglob('*')):
    if path.is_file() and path.name != 'ARCHIVE_MANIFEST.json' and '__pycache__' not in path.parts:
        files[path.relative_to(root).as_posix()] = {
            'sha256': hashlib.file_digest(path.open('rb'), 'sha256').hexdigest(),
            'bytes': path.stat().st_size,
        }
manifest = {'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'source_commit':'37b321048432ccba5182a66bd39b1ca73c547537',
    'branch':'codex/issue-92-overnight-20260916','uncommitted':True,'files':files,
    'input_contract':'policy.json pins inherited inputs, model and source files; validation checks all source hashes and score reuse identities.'}
with (root/'ARCHIVE_MANIFEST.json').open('x', encoding='utf-8') as f:
    json.dump(manifest, f, indent=2)
print(len(files), hashlib.sha256((root/'ARCHIVE_MANIFEST.json').read_bytes()).hexdigest())
