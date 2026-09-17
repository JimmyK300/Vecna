"""Bounded, sequential AGY native-video quality pilot; no query-aware caption input."""
import hashlib
import json
import shutil
import subprocess
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent
IDS = ['p0_q04', 'p0_q13', 'p0_q19', 'p1_q02', 'p2_q14', 'p2_q25']
FAMILIES = ['dense-natural', 'structured-evidence', 'structured-temporal']
AGY = Path('C:/Users/minhc/AppData/Local/agy/bin/agy.EXE')
SANDBOXES = Path('C:/Users/minhc/.codex/media-sandboxes/issue95-quality-v3')
PREFIX = '''Open clip.mp4 in your current working directory using your native view_file tool, then carry out the caption instructions below. You must actually view the media. Do not inspect any other files or directories, use commands, external APIs, web search, other agents, or prior conversations. Do not write files. Use only native video viewing and return your caption in the final response. If media viewing fails, report that failure instead of inventing content. Media sampling/resolution is controlled by the native tool; do not claim a configured fps or resolution.\n\n'''

def sha(path):
    return hashlib.file_digest(Path(path).open('rb'), 'sha256').hexdigest()

def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

def main():
    clips = {r['query_id']: r for r in map(json.loads, (BASE/'clips/clips.jsonl').read_text(encoding='utf-8').splitlines())}
    manifest = {
        'schema': 'agy-native-video-quality-pilot-v1', 'query_ids': IDS,
        'selection': 'Fixed before output: fine detail, OCR/count, speech QA, slides/sequence, motion, negation.',
        'families': FAMILIES, 'model': 'gemini-3.8-flash-high',
        'route': 'AGY CLI native view_file; fps/resolution/audio pipeline not controlled or proven API-equivalent',
        'source_commit': subprocess.check_output(['git','rev-parse','HEAD'], cwd=BASE, text=True).strip(),
        'dirty_state': subprocess.check_output(['git','status','--short'], cwd=BASE, text=True),
        'code_sha256': sha(__file__), 'prefix': PREFIX,
        'clips': [clips[q] for q in IDS],
        'prompt_sha256': {f:sha(BASE/'prompts'/f'{f}.txt') for f in FAMILIES},
        'evaluation_plan': 'After freeze, inspect authoritative requirements and videos. Record atom support, missing evidence, contradictions, OCR/count accuracy and unverifiable audio. Audit concrete claims independently with frames; same-model judging alone is not verification. Six clips are diagnostic, not population estimates. No full-batch launch from this pilot without review.'
    }
    if (ROOT/'manifest.json').exists():
        raise RuntimeError('Non-overwriting pilot already initialized; inspect saved state before resuming.')
    save(ROOT/'manifest.json', manifest)
    outcomes = []
    for q in IDS:
        assert sha(clips[q]['clip_path']) == clips[q]['clip_sha256']
        for family in FAMILIES:
            sandbox = SANDBOXES / uuid.uuid4().hex
            sandbox.mkdir(parents=True)
            shutil.copyfile(clips[q]['clip_path'], sandbox/'clip.mp4')
            dest = ROOT/'outputs'/f'{q}__{family}'
            dest.mkdir(parents=True, exist_ok=False)
            prompt = ('The exact absolute video path is: ' + str(sandbox/'clip.mp4') + '\nCall view_file with AbsolutePath set to exactly this path. Do not guess paths. If this exact path fails, stop and report the error immediately.\n\n' + PREFIX + (BASE/'prompts'/f'{family}.txt').read_text(encoding='utf-8'))
            (dest/'request.txt').write_text(prompt, encoding='utf-8')
            args = [str(AGY),'--model','gemini-3.8-flash-high','--effort','high','--output-format','stream-json','--print-timeout','6m','--print',prompt]
            started = time.time()
            with (dest/'stdout.jsonl').open('wb') as out, (dest/'stderr.log').open('wb') as err:
                proc = subprocess.Popen(args, cwd=sandbox, stdout=out, stderr=err, stdin=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
                try:
                    rc = proc.wait(timeout=390)
                except subprocess.TimeoutExpired:
                    subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'], capture_output=True)
                    proc.wait(timeout=15)
                    rc = -1
            events = []
            for line in (dest/'stdout.jsonl').read_text(encoding='utf-8', errors='replace').splitlines():
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
            results = [e['result'] for e in events if e.get('event') == 'result']
            result = results[-1] if results else {}
            calls = [e['step_update']['tool_info'] for e in events if e.get('step_update',{}).get('tool_info')]
            viewed = any(c.get('name') == 'view_file' and str(c.get('parameters',{}).get('AbsolutePath','')).replace('\\','/').lower() == str(sandbox/'clip.mp4').replace('\\','/').lower() for c in calls)
            unexpected = [c for c in calls if not (c.get('name') == 'view_file' and str(c.get('parameters',{}).get('AbsolutePath','')).replace('\\','/').lower() == str(sandbox/'clip.mp4').replace('\\','/').lower())]
            caption = result.get('response','')
            (dest/'caption.txt').write_text(caption, encoding='utf-8')
            row = {'query_id':q,'family':family,'returncode':rc,'status':result.get('status'),'view_file_called':viewed,'unexpected_tools':unexpected,'elapsed_s':time.time()-started,'conversation_id':result.get('conversation_id'),'sandbox':str(sandbox),'clip_sha256':clips[q]['clip_sha256'],'request_sha256':sha(dest/'request.txt'),'caption_sha256':sha(dest/'caption.txt'),'usage':result.get('usage')}
            row['tool_errors'] = [c['error'] for c in calls if c.get('error')]
            row['candidate_valid'] = rc == 0 and result.get('status') == 'SUCCESS' and bool(caption.strip()) and viewed and not unexpected and not row['tool_errors']
            save(dest/'record.json', row)
            outcomes.append(row)
            save(ROOT/'progress.json', outcomes)
            print(json.dumps({'query_id':q,'family':family,'candidate_valid':row['candidate_valid']}), flush=True)
            if not row['candidate_valid']:
                save(ROOT/'terminal.json', {'state':'needs_review','records':outcomes})
                return 2
    save(ROOT/'terminal.json', {'state':'captions_frozen_pending_quality_review','records':outcomes})
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
