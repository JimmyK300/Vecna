import test from "node:test";
import assert from "node:assert/strict";

import { getSearchShortcutAction, getVideoShortcutAction } from "../src/utils/keyboardShortcuts.js";

test("Search restores candidate navigation, triage, and quick-open shortcuts", () => {
  assert.deepEqual(getSearchShortcutAction({ key: "j" }), { type: "candidate-previous" });
  assert.deepEqual(getSearchShortcutAction({ key: "k" }), { type: "candidate-next" });
  assert.deepEqual(getSearchShortcutAction({ key: "s" }), { type: "toggle-shortlist" });
  assert.deepEqual(getSearchShortcutAction({ key: "x" }), { type: "toggle-reject" });
  assert.deepEqual(getSearchShortcutAction({ key: "1", shiftKey: true }), { type: "quick-open", index: 0 });
  assert.deepEqual(getSearchShortcutAction({ key: "0", shiftKey: true }), { type: "quick-open", index: 9 });
  assert.equal(getSearchShortcutAction({ key: "s" }, { isInput: true }), null);
});

test("Video keeps playback shortcuts and uses S for answer-frame selection", () => {
  assert.deepEqual(getVideoShortcutAction({ key: "k" }), { type: "toggle-play" });
  assert.deepEqual(getVideoShortcutAction({ key: "s" }), { type: "toggle-select-frame" });
  assert.deepEqual(getVideoShortcutAction({ key: "ArrowLeft", shiftKey: true }), { type: "frame-previous" });
  assert.deepEqual(getVideoShortcutAction({ key: "/", shiftKey: true }), { type: "focus-answer" });
  assert.equal(getVideoShortcutAction({ key: "s" }, { isInput: true }), null);
});
