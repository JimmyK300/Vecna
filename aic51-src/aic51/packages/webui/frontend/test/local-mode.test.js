import test from "node:test";
import assert from "node:assert/strict";

import { EVENT_RETRIEVAL_ENABLED, isExternalSubmissionEnabled } from "../src/utils/localMode.js";

test("external event retrieval is opt-in and disabled in the default test environment", () => {
  assert.equal(EVENT_RETRIEVAL_ENABLED, false);
  assert.equal(isExternalSubmissionEnabled(), false);
});
