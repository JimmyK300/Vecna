import test from "node:test";
import assert from "node:assert/strict";

import { getEvaluationIdAPI, signIn, submitAnswerAPI } from "../src/services/auth.js";

test("event retrieval auth and submission APIs are inert by default", async () => {
  const responses = await Promise.all([
    signIn("user", "password"),
    getEvaluationIdAPI("session"),
    submitAnswerAPI("session", { query_id: "QA", video_id: "video-1", time: 1 }),
  ]);
  assert.deepEqual(responses.map((response) => response.status), [0, 0, 0]);
});
