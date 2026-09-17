# AGY native-video quality pilot v1

Bounded diagnostic: six preselected clips, three unchanged prompt families, 18 fresh sessions. This is separate from the frozen API experiment. Native AGY view_file processing has unknown/uncontrolled frame sampling, resolution, and audio semantics. No API-equivalence claim.

Selection is fixed in run_pilot.py before generation: p0_q04 (fine detail), p0_q13 (OCR/count), p0_q19 (speech QA), p1_q02 (slides/sequence), p2_q14 (motion), p2_q25 (negation). Selection is not a representative statistical sample. Each caption context receives only the generic adapter instruction, original frozen prompt, and a neutral clip.mp4 in an isolated directory. No query, answer, tag, or scoring inputs are supplied. Fresh AGY sessions still have global agent/tool scaffolding; exact effective context is not fully observable.

Runner saves source commit/dirty state, clip and prompt hashes, raw event streams, final caption, tool-access audit, usage, and request/caption hashes. Existing API successes remain unchanged. Clip inputs stay at exact paths with SHA-256 in manifest.json. This version refuses to overwrite an initialized pilot.

Reproduction: run `python run_pilot.py` from a fresh versioned archive path on the same host with AGY authenticated. Requires existing hash-matched clips and unchanged parent prompt files. No retrieval, index, or corpus changes. Caption inference/access semantics change to AGY native viewing.

After caption freeze: inspect authoritative query decomposition and independently review visual evidence, important OCR/count/action claims, omissions and contradictions. Audio claims remain unverified unless independently checked. Record all disagreements. Do not treat model self-reports or a same-model judge as independent validation. Do not launch the full batch from pilot output alone. Final quality report, provenance, focused checks and output hashes are pending.

Execution retry v2: v1 failed its first AGY account eligibility check on DNS resolution before inference (zero usage). v1 retained unchanged. DNS resolution succeeded before this single retry. Same clip and prompt selection; no successful captions duplicated.

Execution revision v3: v2 never accessed media because native view_file requires an absolute path and active workspace context was absent. v2 retained unchanged. This revision supplies a neutral absolute clip path and forbids guessing; rejects any tool errors. No successful captions duplicated.
