"""Issue #63 Stage A wide-context sheets: +-100s @10s (singles), +-40s @5s (trake events)."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from stage_a_filmstrips import ROOT, STILLS, sheet  # noqa: E402


def main() -> int:
    with open(os.path.join(ROOT, "anchors.json"), encoding="utf-8") as fh:
        records = json.load(fh)
    with open(os.path.join(ROOT, "review", "provenance.json"), encoding="utf-8") as fh:
        probes = json.load(fh)["video_probes"]

    for rec in records:
        if rec.get("blocker"):
            continue
        vp = rec["video_path"]
        info = probes[vp]
        fps, dur = info["fps"], info["duration_s"]
        sub, qid = rec["submission"], rec["query_id"]
        qdir = os.path.join(STILLS, sub, qid, "wide")
        os.makedirs(qdir, exist_ok=True)
        anchors = rec["anchor_frames"]
        if len(anchors) == 1:
            a = anchors[0] / fps
            tiles = [(round((a + dt) * fps), a + dt) for dt in range(-100, 101, 10)]
            out = os.path.join(qdir, f"wide_{anchors[0]:06d}.jpg")
            title = (f"WIDE {sub} {qid} {rec['submitted_type']}  {rec['video_id']}"
                     f"  anchor f={anchors[0]} t={a:.2f}s  dur={dur:.0f}s")
            sheet(tiles, vp, fps, dur, out, [anchors[0]], title)
        else:
            for ei, afr in enumerate(anchors, start=1):
                a = afr / fps
                tiles = [(round((a + dt) * fps), a + dt) for dt in range(-40, 41, 5)]
                out = os.path.join(qdir, f"wide_E{ei}_{afr:06d}.jpg")
                title = (f"WIDE {sub} {qid} trake E{ei}/{len(anchors)}  {rec['video_id']}"
                         f"  anchor f={afr} t={a:.2f}s  dur={dur:.0f}s")
                sheet(tiles, vp, fps, dur, out, [afr], title)
        print("wide done", sub, qid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
