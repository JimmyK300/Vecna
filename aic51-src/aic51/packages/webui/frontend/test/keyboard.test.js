import test from "node:test";
import assert from "node:assert/strict";

import { getShortcutAction } from "../src/utils/keyboardShortcuts.js";

test("keeps expert playback shortcuts and adds J/K/S/X triage experiments", () => {
  assert.equal(getShortcutAction({ key: "k" }), "toggle-play");
  assert.equal(getShortcutAction({ key: "j" }), "seek-previous");
  assert.equal(getShortcutAction({ key: "s" }), "toggle-shortlist");
  assert.equal(getShortcutAction({ key: "x" }), "toggle-reject");
  assert.equal(getShortcutAction({ key: "ArrowLeft", shiftKey: true }), "frame-previous");
  assert.equal(getShortcutAction({ key: "/", shiftKey: true }), "focus-answer");
  assert.equal(getShortcutAction({ key: "s" }, { isInput: true }), null);
});
