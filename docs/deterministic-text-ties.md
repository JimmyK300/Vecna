# Deterministic text-result ties (issue #89)

Given identical provider responses, text aggregation now orders exact final-score ties by ascending full canonical frame ID. This is Python's Unicode lexicographic string order, with no locale collation, numeric parsing, score rounding or tolerance. The policy is selected for repeatability independently of benchmark outcomes; it does not claim retrieval improvement.

The production change sorts the frame-ID set before constructing results. Python's existing stable descending score sort then preserves that canonical ID order only within exact score ties. Sparse-only, dense-only and hybrid paths share this aggregation. Provider requests, phrase eligibility and boosting, candidate membership, first-seen entity choice, score accumulation, normalization, final scores and non-tied score order are unchanged for the same responses.

This fixes this component's set-dependent order, not all possible nondeterminism in retrieval or other fusion stages. Providers may still return different candidates across requests. The tie policy is a ranking change and requires review before integration.

## Scope and provenance

- Base: Vecna main commit `95d63a6abf10c598e0e54af7d2071bedbe542d1e`.
- Original searcher LF SHA-256: `6f94bdd147c4b2b29b522a1f4bbbf004fb726fdfdf68a7cb316a4aec9e869e51`.
- Corrected searcher LF SHA-256: `58c053467b1c0fb68090dd2bfb2c3f3352be282c2c5d4d42b060649dbc656764`.
- Original method SHA-256: `8f772e5e97046e2a310c0c680cf7786df1bb6da5232471ee4a02dd3a40c5d409`.
- Corrected method SHA-256: `92a8ff1f7fdca8a6a5b945fdd805690ab175abbb0204ca05c23f1808d246277d`.

Method hashes cover the production function from its indented `def` line through its final return, with LF endings and one trailing newline. The tests reconstruct the original method by reversing only the reviewed loop change and require its exact original hash.

This is a separate issue #89 correctness fix. It does not modify #82's frozen experimental code, captures, scores, proposals or source-review branches. No query truth, benchmark outcome, favorable hash seed or target frame is used to choose the policy.

## Focused validation

From the repository root, with Python 3.10 or newer:

```sh
python aic51-src/tests/test_text_tie_order.py -v
```

The nine unittest methods exercise 13 synthetic fixture cases through the actual production method and its query, phrase and normalization helpers. AST isolation avoids importing the model/database stack. Only provider responses, a fixed dense extractor output, logging and the array-to-list conversion are substituted. There are no external Python dependencies, model loads, database connections, network calls or truth files.

Coverage includes sparse, dense and hybrid exact ties; near-but-unequal full-precision scores whose displayed values round equally; complementary hybrid scores; quoted phrase filtering and boosting; multiple-query accumulation and first-seen entities; nonpositive-score normalization; and the existing empty return. Every candidate's complete entity and unrounded/rounded score record is compared with the original method, as are provider requests and extractor inputs.

The subprocess test launches fresh interpreters with `PYTHONHASHSEED=0,1,82`. All corrected outputs must be identical, while the tied fixture must reproduce differing original-method orders across the seeds. The inherited process seed therefore cannot hide the original failure.

**Execution status:** passed on 2026-09-16 using Windows Python 3.12.1: all nine tests and 13 fixtures, including fresh hash-seed processes 0, 1 and 82. Unittest reported 5.032 seconds; the supervised test subprocess took 5.573 seconds. The production source and tests were executed as exact Git bytes from commit `fc91800b9bb1c280696fe81dbfb76e38598b798e` in a disposable mirrored repository layout. Native HEAD and porcelain status and the disposable execution HEAD remained unchanged. The [validation proof](../benchmark-results/astra-retrieval-rd-v1/tie-fix-validation/validation.json), [complete test log](../benchmark-results/astra-retrieval-rd-v1/tie-fix-validation/stderr.txt), [broker result](../benchmark-results/astra-retrieval-rd-v1/tie-fix-validation/broker-result.json), and [executed task packet](../benchmark-results/astra-retrieval-rd-v1/tie-fix-validation/dispatch.json) preserve this run. The log retains Python 3.12 SyntaxWarnings about an invalid escape in the unchanged production docstring; these are not test failures. No saved benchmark ranking was rescored and no main merge or production deployment is included.
