# Online Video Retrieval Literature Review

## Goal

This review studies existing interactive video retrieval systems and related retrieval methods to decide whether the project should build on an existing framework or create a minimal custom prototype. The main question is not which system is academically strongest in isolation, but which one gives the best starting point for a usable query-ranking interface under realistic team and resource constraints.

## Core framing

The current project should treat the first phase as **adoption testing**, not implementation. The immediate job is to evaluate strong existing systems, understand their query support, ranking logic, UI quality, extensibility, and setup burden, and then decide whether extending a base is better than building a custom prototype.

This framing matters because the systems in this space differ not only in retrieval capability, but also in architectural complexity and development cost. A framework that is theoretically rich but too heavy to run or modify is less useful than a simpler base that supports fast experimentation.

## Linked source table

See [query_ranking_ui_candidates.csv](./query_ranking_ui_candidates.csv).

## Candidate snapshot

| Candidate | Main links | Position |
| --- | --- | --- |
| VISIONE | GitHub: https://github.com/aimh-lab/visione; Paper: https://arxiv.org/abs/2008.02749 | Top adoption candidate. |
| vitrivr / Cineast / vitrivr-ng | vitrivr: https://vitrivr.org/vitrivr.html; Setup: https://vitrivr.org/getting_started.html; Cineast: https://github.com/vitrivr/cineast | Strong but setup-heavier candidate. |
| VERGE | https://m4d.iti.gr/verge-interactive-image-video-retrieval-engine/ | Reference only unless maintainability is proven. |
| diveXplore 2024 | https://arxiv.org/abs/2508.20560 | UI and orchestration reference rather than a primary base. |
| Fusionista2.0 | https://arxiv.org/abs/2511.12255 | Efficiency/design reference for later stages. |

## Main candidate groups

### 1. Full retrieval systems and frameworks

The strongest framework candidates are **VISIONE** and **vitrivr**.

VISIONE appears to be the most promising adoption candidate. From the collected sources, it supports multilingual text-to-video retrieval, image-based search, temporal queries, object and color queries, keyframe browsing, and a usable web interface. It also has a comparatively understandable workflow: import data, analyze it, index it, and serve the search interface. Its VBS competition record strengthens the case that it is not merely a research artifact but a system that has performed well in real interactive retrieval settings.

vitrivr is the other serious build-from-base option. It is broader and more retrieval-oriented as a platform, with a richer set of query types such as query-by-example, sketches, motion sketches, and example objects through Cineast. However, this power comes with a heavier stack, more setup dependencies, and a steeper architectural surface. It may be a stronger long-term foundation, but it is less obviously the fastest route to a first usable prototype.

VERGE is useful as a comparison point rather than a likely base. It shows that multimodal video retrieval systems have long combined visual similarity, concept retrieval, temporal search, and UI interaction. However, the stack looks older and there is less confidence that it is easy to run, maintain, or extend in a modern workflow. It should therefore be treated mainly as historical or design evidence.

### 2. Systems that are more useful as design references than as bases

Several sources are valuable because they show what strong modern systems do, even if they are not the best starting framework.

**diveXplore 2024** is useful for query orchestration, result merging, and browsing workflow ideas. It seems especially relevant to interface design and interaction speed.

**Fusionista2.0** is useful as an efficiency-focused multimodal reference. It is valuable for later-stage ideas involving OCR, ASR, lightweight vision-language models, and responsive interface design.

**NII-UIT VBS2025** is important as evidence that LLM-based query expansion and temporal search can be effective, but this is more appropriate for a later stage than for the first baseline decision.

**H-EAGLE** is useful as an architectural research direction around hierarchical retrieval, but it is too complex for the initial stage.

### 3. Retrieval and fusion methods

The strongest method-level sources in the current pool are **RRF**, **MMMORRF**, and **GQE**.

RRF is the most practical fusion baseline because it is simple, unsupervised, and easy to implement. It is a strong candidate for an early fusion strategy if a custom prototype is needed.

MMMORRF is especially relevant because it gives a modality-aware extension of rank fusion. It aligns closely with the project’s likely need to combine visual embeddings, OCR text, and ASR speech signals.

GQE is useful as a future method for query expansion. It supports the idea that later iterations could improve retrieval quality by generating multiple reformulations of the same user query, but it should not be treated as a prerequisite for the first working system.

## Comparative synthesis

The source set supports three main conclusions.

First, **VISIONE and vitrivr are the only serious current build-from-base candidates**. Both are real systems, both support interactive video retrieval, and both have enough technical depth to justify adoption testing.

Second, **VISIONE currently looks more developer-friendly**, while **vitrivr looks more powerful but heavier**. VISIONE better fits a fast adoption-test phase because its workflow appears more direct and the system boundary is easier to reason about. vitrivr offers richer retrieval modes, especially sketch-oriented and example-driven querying, but that richness may slow down early progress.

Third, **the project should delay advanced retrieval tricks until after the base decision**. Query expansion, modality-aware reranking, relevance feedback, and hierarchical search are all strong ideas, but they are not the right place to begin if the system still lacks a stable retrieval base and usable query-to-result interface.

## Recommended phase structure

### v0: Base adoption test

v0 should test existing frameworks rather than build new features. The main systems to test are:

1. VISIONE
2. vitrivr / Cineast / vitrivr-ng

VERGE and similar systems should remain reference points unless they prove unusually easy to run and adapt.

The output of v0 should be an adoption scorecard covering:

- setup success
- time to first search
- data import fit
- query support
- UI quality
- extensibility
- stack fit
- performance
- documentation quality
- contest/task fit

### v1: Extend a suitable base or build a minimal custom prototype

If an existing framework is suitable, v1 should add the missing feature on top of that framework rather than rebuild the whole stack.

If no framework is suitable, v1 should build a minimal custom prototype with a narrow goal: query input, ranked keyframes, and click-through to video timestamps. A simple fusion baseline such as RRF should be preferred over more complex learned fusion at this stage.

### v2: Add performance improvements

Only after the base works should the project add:

- query expansion
- OCR/ASR enrichment
- improved rank fusion
- relevance feedback
- grouping or exploration tools

## Baseline decision rule

The working decision rule should be:

- If VISIONE or vitrivr can be run locally, can ingest a realistic sample, and scores strongly on the adoption checklist, extend that framework.
- If both require too much engineering effort or fit the task poorly, build a minimal custom prototype instead.

This keeps the project grounded in evidence rather than jumping too early into custom implementation.

## Next steps

1. Run a focused adoption test on VISIONE.
2. Run a focused adoption test on vitrivr/Cineast/vitrivr-ng.
3. Score both systems using the same evaluation checklist.
4. Record which missing features are genuinely blockers versus nice-to-have features.
5. Make the baseline decision: extend an existing framework if one is suitable; otherwise build a minimal custom prototype.
6. Keep RRF as the default simple fusion baseline if a custom path is needed.

## Working conclusion

At the current stage, the best-supported direction is:

**Evaluate existing frameworks first, especially VISIONE and vitrivr. If one is suitable, build on it. If neither is suitable, build a minimal custom prototype and evaluate it with the same simple criteria used for the framework comparison.**
