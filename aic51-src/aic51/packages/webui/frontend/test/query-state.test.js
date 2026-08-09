import test from "node:test";
import assert from "node:assert/strict";

import {
  clearQueryHistory,
  groupTemporalCandidates,
  loadQueryHistory,
  normalizeTemporalQuery,
  rememberQuery,
  restoreAllRejectedState,
  restoreRejectedState,
  resetTriageState,
  saveQueryHistory,
  serializeQueryState,
  updateTriageState,
} from "../src/utils/queryState.js";

test("serializes a search without unsupported exclude-video filtering", () => {
  assert.deepEqual(
    serializeQueryState({
      query: "ocr:ticket;asr:open",
      params: { limit: 10, nprobe: 512 },
      includeVideo: "a,b",
      offset: 20,
    }),
    {
      limit: 10,
      nprobe: 512,
      offset: 20,
      q: "ocr:ticket;asr:open",
      include_video: "a,b",
    },
  );
  assert.equal(normalizeTemporalQuery(" first | second\\third "), "first;second;third");
});

test("groups temporal paths into one storyboard candidate", () => {
  const candidates = groupTemporalCandidates([
    {
      id: "video-1#0042",
      video_id: "video-1",
      frame_id: "0042",
      time_line: ["0042", "0060"],
      time_line_scores: [{ final: 0.9 }, { final: 0.8 }],
    },
    {
      id: "video-2#0010",
      video_id: "video-2",
      frame_id: "0010",
      time_line: ["0010"],
    },
  ]);

  assert.equal(candidates.length, 2);
  assert.deepEqual(candidates[0].keyframes, ["0042", "0060"]);
  assert.equal(candidates[0].timelineScores[1].final, 0.8);
});

test("history and triage state stay query-scoped", () => {
  const storage = new Map();
  storage.getItem = storage.get.bind(storage);
  storage.setItem = (key, value) => storage.set(key, value);
  storage.removeItem = storage.delete.bind(storage);

  let history = rememberQuery("red car", []);
  history = rememberQuery("blue car", history);
  history = rememberQuery("red car", history);
  saveQueryHistory(history, storage);
  assert.deepEqual(loadQueryHistory(storage), ["red car", "blue car"]);

  let triage = updateTriageState({}, "red car", "video-1#42", "shortlist");
  triage = updateTriageState(triage, "blue car", "video-1#42", "reject");
  assert.equal(Object.keys(triage).length, 2);
  triage = resetTriageState(triage, "red car");
  assert.equal(Object.keys(triage).length, 1);
  triage = updateTriageState(triage, "red car", "video-2#10", "reject");
  assert.equal(Object.keys(restoreRejectedState(triage, "red car", "video-2#10")).length, 1);
  assert.equal(Object.keys(restoreAllRejectedState(triage, "blue car")).length, 1);
  assert.deepEqual(clearQueryHistory(storage), []);
});
