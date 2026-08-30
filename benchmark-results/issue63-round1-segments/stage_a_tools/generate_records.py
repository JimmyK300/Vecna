"""Issue #63 Stage A record generator: segments/*.yaml + review/index.html."""

from __future__ import annotations

import json
import os
import sys

import yaml

sys.path.insert(0, os.path.dirname(__file__))
from records_final import R as R_FINAL  # noqa: E402
from records_t88 import R as R_T88  # noqa: E402

ROOT = r"C:\Users\minhc\Code\vecna-issue-63\benchmark-results\issue63-round1-segments"
STILLS = os.path.join(ROOT, "review", "stills")

OFFICIAL_TEXT = {
    "p1-1": "KIS: spacecraft intro; 4 astronauts in black; polar-light research",
    "p1-2": "KIS: Southern locality intro with ~3-6 rare tiger/panther cubs",
    "p1-4": "TRAKE: net-casting events E1-E4",
    "p1-5": "KIS: two women feeding goats; white tee + red shoulder garment; striped sleeves",
    "p1-6": "KIS: fresh rolls placed on flower-decorated tray (opening scene)",
    "p1-7": "KIS: forest-floor bird, black-blue head, brown-red body, red eyes",
    "p1-8": "KIS: Japanese food festival; girl with red octopus/squid + paper bag",
    "p1-9": "KIS: Mekong harvest scene; girl in pink + checkered scarf; baskets; blue boat",
    "p1-10": "KIS: handpan trio, white-shirt player between two in black, bookshelves",
    "p1-11": "KIS: shadow-portrait art from wood pieces on a box",
    "p1-12": "KIS: doughnut decorating; white plate on wooden tray; scale; banana; chocolate",
    "p1-13": "KIS: camera cleaning; lens on pink/purple cloth; wipe with cloth",
    "p1-14": "KIS: sand-sculpture festival; youth-sports relief; arch; 2 pink blocks",
    "p1-15": "QA: FANA charity commune in Khanh Hoa; name the commune",
    "p1-16": "TRAKE: lion dance; E1 spin start; E2 4 legs down; E3 at judges; E4 dragon head",
    "p1-17": "KIS: spring-2024 hospital charity; 2 men + 4 children; plaques; red backdrop",
    "p1-18": "TRAKE: mushroom dish; E1 first slices; E2 shiitake; E2dup tofu; E4 sauce+flames",
    "p1-19": "QA: two couplets at Nguyen Trung Truc temple, Kien Giang",
    "p1-20": "KIS: panna cotta; 1 glass on plate; hand adds 2; grapes; mint; 2 flowers",
    "p1-21": "KIS: Lausanne university; bird-flight mechanism for robot design",
    "p1-22": "QA: recipe card with 200g ground pork; give dish title",
    "p1-23": "KIS: coastal town; dangerous marine animal; Spielberg 1975 (Jaws)",
    "p1-24": "KIS: top-down drone; 3 riders in line; white/red/black jerseys",
    "p1-25": "KIS: drone; blue-white rider overtakes 3 then leads to finish",
}


def fps_of(video: str, probes: dict) -> float:
    return probes[video]["fps"]


def main() -> int:
    with open(os.path.join(ROOT, "anchors.json"), encoding="utf-8") as fh:
        anchors = json.load(fh)
    with open(os.path.join(ROOT, "review", "provenance.json"), encoding="utf-8") as fh:
        probes = json.load(fh)["video_probes"]
    anchor_by_key = {(a["submission"], a["query_id"]): a for a in anchors}

    segdir = os.path.join(ROOT, "segments")
    os.makedirs(segdir, exist_ok=True)

    html_rows = []
    for R in (R_T88, R_FINAL):
        for r in R:
            key = (r["submission"], r["qid"])
            a = anchor_by_key.get(key)
            vp = a.get("video_path") if a else None
            fps = probes[vp]["fps"] if vp else None
            dur = probes[vp]["duration_s"] if vp else None
            ranges_out = []
            for (s, e) in r["ranges"]:
                item = {"start_s": round(s, 2), "end_s": round(e, 2)}
                if fps:
                    item["start_frame"] = int(round(s * fps))
                    item["end_frame"] = int(round(e * fps))
                ranges_out.append(item)
            times = a["derived_anchor_times_s"] if a else None
            doc = {
                "query_id": r["qid"],
                "query": OFFICIAL_TEXT.get(r["qid"]),
                "query_text_status": r["text_status"],
                "source_submission": r["submission"],
                "source_submission_sha256": a["csv_sha256"] if a else None,
                "source_csv": a["source_csv"] if a else None,
                "submitted_type": r["qtype"],
                "video_id": r["video"],
                "video_path": a.get("video_path") if a else None,
                "video_duration_s": round(dur, 2) if dur else None,
                "video_fps_projection": fps,
                "frame_time_projection_note": "t = frame_id / ffprobe_avg_fps; provenance v1 marks legacy_time_projection_quality unknown; drift possible",
                "submitted_anchor_frames": a["anchor_frames"] if a else None,
                "submitted_timestamps_s": times,
                "qa_answer_verbatim": a.get("qa_answer_verbatim") if a else None,
                "proposed_correct_ranges": ranges_out,
                "confidence": r["confidence"],
                "boundary_reasoning": r["reasoning"],
                "conflict_notes": r["conflicts"],
                "reviewer_note": r["note"],
                "review_status": "NEEDS_MINH_REVIEW",
                "stage": "A",
                "benchmark_writeback": "FORBIDDEN_UNTIL_MINH_REVIEW",
            }
            if not ranges_out:
                doc["blocker"] = "no_range_proposed"
            with open(os.path.join(segdir, f"{r['submission']}__{r['qid']}.yaml"), "w",
                      encoding="utf-8") as fh:
                yaml.safe_dump(doc, fh, allow_unicode=True, sort_keys=False)

            sub_lbl = "final(10.4/13)" if r["submission"].startswith("final") else "633(8.8)"
            sheets = []
            qdir = os.path.join(STILLS, r["submission"], r["qid"])
            if os.path.isdir(qdir):
                for f in sorted(os.listdir(qdir)):
                    rel = os.path.relpath(os.path.join(qdir, f), ROOT).replace("\\", "/")
                    if f.endswith(".jpg"):
                        sheets.append(rel)
            wide = [s for s in sheets if "wide" in s]
            fine = [s for s in sheets if "wide" not in s]
            rng = "; ".join(f"[{s:.0f}-{e:.0f}s]" for (s, e) in r["ranges"]) or "BLOCKER"
            html_rows.append(f"""
<tr class='{"blocker" if not ranges_out else ""}'>
<td>{r['qid']}<br><small>{r['qtype']}</small></td>
<td>{sub_lbl}</td>
<td>{r['video']}</td>
<td>{', '.join(str(f) for f in (a['anchor_frames'] if a else []))}<br>
    <small>{', '.join(f'{t:.1f}s' for t in times) if times else ''}</small></td>
<td>{rng}</td>
<td>{r['confidence']}</td>
<td class='why'>{r['reasoning']}<br><b>Conflicts:</b> {r['conflicts']}
    {('<br><b>Note:</b> ' + r['note']) if r['note'] else ''}</td>
<td>{''.join(f"<a href='{s}'><img src='{s}' loading='lazy'></a>" for s in fine[:1])}
    {''.join(f"<a href='{s}'><img src='{s}' loading='lazy'></a>" for s in wide[:1])}</td>
</tr>""")

    official = {k: v for k, v in OFFICIAL_TEXT.items()}
    html = f"""<!DOCTYPE html><html><head><meta charset='utf-8'>
<title>Issue #63 Stage A - Round-1 segment review (HARD GATE)</title>
<style>
body{{font-family:Segoe UI,Arial;background:#111;color:#ddd;margin:20px}}
h1{{color:#ffd24a}} h2{{color:#8fd}} .gate{{background:#5b0000;border:2px solid #ff5b5b;padding:12px;border-radius:8px;font-weight:600}}
table{{border-collapse:collapse;width:100%;font-size:13px}}
td,th{{border:1px solid #444;padding:6px;vertical-align:top}}
th{{background:#222;position:sticky;top:0}}
tr.blocker td{{background:#3a0d0d}}
img{{width:220px;margin:2px;border:1px solid #555}}
.why{{max-width:560px}}
a{{color:#7cf}}
</style></head><body>
<h1>Issue #63 - Stage A review packet</h1>
<div class='gate'>HARD HUMAN GATE: Stage A only. No benchmark ground truth was created,
modified, merged, or regenerated. All ranges are PROPOSALS with
review_status=NEEDS_MINH_REVIEW. Stage B is forbidden until Minh accepts/corrects ranges.</div>
<h2>Inputs (provenance)</h2>
<ul>
<li><b>final_round1_10_4of13</b> = <code>Downloads\\submission-final-round1.zip</code>
(SHA-256 802732A492A3AA1C09189720D248BA430132AEB55B2913E0A4665BCDCBBA0158, 25 CSVs incl. p1-3-qa)</li>
<li><b>testing88_submission633</b> = <code>Downloads\\submission-testing8.8\\submission\\</code>
(24 CSVs; described in issue as 'submission 633 / submission testing 8.8 / 8.8 result';
per-CSV SHA-256 in anchors.json)</li>
<li>Videos: <code>Code\\Official-Dataset\\videos\\L*\\*.mp4</code> (L26 split across L26A-E).
Frame&rarr;time: t=frame/fps (ffprobe). L21/L24/L29/L30 mostly 30fps; L30_V046 25fps.</li>
</ul>
<h2>Global findings</h2>
<ul>
<li>The two submissions disagree on nearly every query: different videos AND different task
types (p1-4 kis/trake, p1-17 kis/qa, p1-18 kis/trake, p1-19 kis/qa, p1-22 kis/qa).
The final zip also contains <b>query-p1-3-qa.csv</b>, absent from the official 24-query list,
and duplicates the p1-8 answer for p1-14.</li>
<li>testing8.8's types match the official test-round list; final's types do not. No Round-1
query text exists locally, so final records are visual-segment proposals only (low confidence).</li>
<li>testing8.8 p1-21 is a <b>blocker</b>: source video L21_V004.mp4 is missing locally.</li>
</ul>
<h2>Official test-round query reference (test-round list only; final may differ)</h2>
<table><tr><th>Query</th><th>Official text (normalized)</th></tr>
{''.join(f'<tr><td>{k}</td><td>{v}</td></tr>' for k, v in official.items())}
</table>
<h2>Per-query review (click stills to enlarge; red tile = submitted anchor)</h2>
<table>
<tr><th>Query</th><th>Submission</th><th>Video</th><th>Anchor frame(s)/t</th>
<th>Proposed range(s)</th><th>Conf</th><th>Reasoning / conflicts</th><th>Stills (fine + wide)</th></tr>
{''.join(html_rows)}
</table>
<p>Machine-readable records: <code>segments/*.yaml</code>; anchors:
<code>anchors.json</code>; hashes/probes: <code>review/provenance.json</code>.</p>
</body></html>"""
    with open(os.path.join(ROOT, "review", "index.html"), "w", encoding="utf-8") as fh:
        fh.write(html)
    print("segments:", len(R_T88) + len(R_FINAL), "-> index.html written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
