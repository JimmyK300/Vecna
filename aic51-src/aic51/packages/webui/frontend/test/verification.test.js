import test from "node:test";
import assert from "node:assert/strict";

import {
  applyFrameOcrFallback,
  hasFrameOcrEvidence,
  mergeFrameEvidence,
} from "../src/utils/verification.js";

test("verification keeps candidate evidence when frame metadata is sparse", () => {
  const candidate = { video_id: "video-1", frame_id: "0042", ocr: "ticket", evidence: { source: "search" } };
  const merged = mergeFrameEvidence(candidate, { time: 12.5, frame_id: "0042", ocr: "", ocr_bboxes: [] });
  assert.equal(merged.ocr, "ticket");
  assert.deepEqual(merged.evidence, { source: "search" });
  assert.equal(merged.time, 12.5);
  assert.equal(hasFrameOcrEvidence(merged), true);
});

test("verification applies frame OCR only as a fallback", () => {
  const merged = applyFrameOcrFallback(
    { video_id: "video-1", frame_id: "0042" },
    { ocr: "fallback text", ocr_bboxes: [{ bbox: [1, 2, 11, 12] }] },
  );
  assert.equal(merged.ocr, "fallback text");
  assert.equal(merged.ocr_bboxes.length, 1);
  assert.equal(hasFrameOcrEvidence(merged), true);
});
