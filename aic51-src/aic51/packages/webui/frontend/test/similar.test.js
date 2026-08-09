import test from "node:test";
import assert from "node:assert/strict";

import { buildSimilarNavigation, getSimilarId } from "../src/utils/similar.js";

test("preserves the source ID while paginating Similar mode", () => {
  const query = { id: "video-7#0099" };
  const params = { limit: 10, nprobe: 512 };
  assert.equal(getSimilarId(query), "video-7#0099");
  assert.deepEqual(buildSimilarNavigation(getSimilarId(query), params, 10), {
    id: "video-7#0099",
    limit: 10,
    nprobe: 512,
    offset: 10,
  });
});
