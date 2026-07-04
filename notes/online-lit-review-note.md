visione is much more developer friendly (simpler architechure)
But visione doesn't have the sketch and such
visione has like more custom text query options tho
But vitrivr has query by sketches or human frame
VERGE seems quite old, it might be outdated

Should seriously consider building from one of these base

v0 will be testing all of these bases, then scoring them and finally evaluating how much we need to build on top of existing base or whether we need to build our own prototype

 v1 will then be building the feature that we deem missing (or build the prototype if a satisfactory base does not exist)

v2 then will be addtional add-ons/plugins/tricks we will implement to further boost our performace

we then need to roughly sketch out how we are going to measure our performace


Your notes are good. The upgraded framing should be:

> **v0 is not implementation. v0 is adoption testing.**
> Test vitrivr, VISIONE, and maybe VERGE/diveXplore as candidate bases; score them; then decide whether to build on one or create a minimal custom prototype.

That is stronger than jumping directly into UI coding.

## Source list for your table

Use these as your current source pool.

| Source                                               | Type                                        | Why include it                                                                                                                                                                                                                                                                                                        |
| ---------------------------------------------------- | ------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **VISIONE GitHub**                             | Open-source system                          | Most important for adoption testing. It has Web UI, multilingual text-to-video retrieval, image search, temporal queries, object/color queries, video/keyframe browsing, Dockerized GPU analysis, and a clear 5-step flow: init → import → analyze → index → serve. ([GitHub][1])                                 |
| **VISIONE paper / system description**         | System paper                                | Explains VISIONE’s design: textual keywords, object/color spatial search, image similarity, and combination of modalities through text-engine-style indexing. ([arXiv][2])                                                                                                                                           |
| **VISIONE 5.0 / VBS2024**                      | VBS system evidence                         | VBS Teams page lists VISIONE 5.0 as**Overall Winner** for VBS2024, so it is strong evidence for serious consideration. ([videobrowsershowdown.org][3])                                                                                                                                                          |
| **vitrivr official architecture**              | System architecture                         | Shows vitrivr as a full stack: UI, retrieval engine, and Cottontail DB. Cineast handles shot segmentation, feature extraction, and query generation. ([vitrivr.org][4])                                                                                                                                               |
| **vitrivr getting started**                    | Setup-risk evidence                         | Shows setup requirements: Java 17+, Git, Docker option, FFmpeg, web server/static media serving, and recommended 8+ GB RAM. Good for adoption-risk scoring. ([vitrivr.org][5])                                                                                                                                        |
| **Cineast GitHub**                             | Retrieval engine                            | Important because it supports multimedia retrieval over images/audio/video/3D and query modes including edge/color sketches, motion sketches, and example objects. ([GitHub][6])                                                                                                                                      |
| **vitrivr-engine 2025**                        | Modern vitrivr direction                    | Adds feature-driven video segmentation, advanced querying, and compatibility with additional storage backends/vector DB systems. ([dbis.dmi.unibas.ch][7])                                                                                                                                                            |
| **VERGE official page**                        | Older system / comparison                   | Hybrid interactive image/video retrieval system with visual similarity, concept retrieval, text-to-video matching, face detection, captioning, activity recognition, clustering, multimodal fusion, and temporal search. Stack looks older: HTML/CSS/JS/jQuery, PHP, Java, Python, Apache, MongoDB. ([m4d.iti.gr][8]) |
| **VBS Teams & Papers**                         | Source index                                | Use this to justify that these are real VBS systems and to find more papers. It collects participating systems across years. ([videobrowsershowdown.org][3])                                                                                                                                                          |
| **VBS 2025 results report**                    | Evaluation context                          | Useful for explaining why speed, usability, and interactive retrieval matter. VBS 2025 had 17 teams and nearly 4,000 hours of video. ([arXiv][9])                                                                                                                                                                     |
| **VBS 2024 results report**                    | Evaluation context                          | Useful because VISIONE won VBS2024, and this report gives the competition context for that year. ([arXiv][10])                                                                                                                                                                                                        |
| **Fusionista2.0**                              | Multimodal fusion / efficiency              | Strong support for fast keyframe extraction, OCR, ASR, lightweight VLMs, responsive UI, and efficiency-first design. ([arXiv][11])                                                                                                                                                                                    |
| **NII-UIT VBS2025**                            | Query expansion / advanced system           | Useful as evidence for LLM query expansion and dynamic temporal search, but likely future-stage rather than v0. ([ACM Digital Library][12])                                                                                                                                                                           |
| **H-EAGLE**                                    | Hierarchical retrieval                      | Useful future idea: hierarchical semantic video retrieval instead of flat index search. Probably too complex for v0. ([DORAS][13])                                                                                                                                                                                    |
| **PraK / relevance feedback success analysis** | Feedback/reranking                          | Useful for future interactive reranking; the VBS success paper mentions Bayes/Rocchio relevance feedback, video summary, reset actions, and interaction analysis. ([ACM Digital Library][14])                                                                                                                         |
| **diveXplore 2024**                            | Query server / result merging / browsing UI | It integrates OpenCLIP, free-text and visual similarity search, query distribution/merging, fast browsing UI, and exploration view. ([arXiv][15])                                                                                                                                                                     |
| **GQE**                                        | Query expansion method                      | Formal support for LLM-generated diverse query expansion and query selection in text-video retrieval. ([arXiv][16])                                                                                                                                                                                                   |
| **RRF original paper**                         | Rank fusion method                          | Core source for Reciprocal Rank Fusion. It is simple, unsupervised, and combines rankings from multiple retrieval systems. ([cormack.uwaterloo.ca][17])                                                                                                                                                               |
| **MMMORRF**                                    | Multimodal weighted RRF                     | Very relevant to your CLIP/OCR/ASR fusion idea: it combines visual, audio/speech, and text-overlay signals using modality-aware weighted RRF. ([arXiv][18])                                                                                                                                                           |
| **Faiss docs**                                 | Vector-search implementation                | Use only as implementation reference. Faiss is for efficient similarity search over dense vectors, not a full retrieval system. ([Faiss][19])                                                                                                                                                                         |

---

## Candidate evaluation table

This is the table I’d actually use for `query_ranking_ui_candidates.csv`.

| Candidate                                | Query handling                                                                          | Ranking/fusion                                                     | UI/display                                |                       Code/demo | Similarity | Achievability | Usefulness | Verdict                                      |
| ---------------------------------------- | --------------------------------------------------------------------------------------- | ------------------------------------------------------------------ | ----------------------------------------- | ------------------------------: | ---------: | ------------: | ---------: | -------------------------------------------- |
| **VISIONE**                        | Text, image, temporal, object/color positional queries                                  | Combines multimodal query parts through index/search engine design | Web UI, keyframe/video browsing, playback |                             Yes |          5 |             5 |          5 | **Top adoption candidate**             |
| **vitrivr / Cineast / vitrivr-ng** | Textual descriptions, query-by-example, query-by-sketch, motion sketch, example objects | Engine + DB retrieval stack, supports multiple query modes         | Web UI / VR UI                            |                             Yes |          5 |             3 |          5 | **Powerful but setup-heavy candidate** |
| **vitrivr-engine 2025**            | Advanced querying, feature-driven segmentation                                          | More modern vector-DB-compatible direction                         | Modular UI direction                      |                      Yes/likely |          5 |             3 |          5 | Audit after classic vitrivr                  |
| **VERGE**                          | Visual similarity, concept retrieval, text-to-video, temporal search                    | Multimodal fusion                                                  | Interactive image/video engine            | Some info, unclear current code |          4 |             2 |          3 | Reference only; likely outdated              |
| **diveXplore 2024**                | Free-text and visual similarity search                                                  | Query server distributes and merges queries                        | Fast browsing UI + exploration view       |                         Unclear |          4 |             3 |          4 | Copy ideas, not base                         |
| **Fusionista2.0**                  | Direct retrieval, efficiency-focused                                                    | Multimodal retrieval with OCR/ASR/VLM components                   | Redesigned responsive UI                  |                         Unclear |          5 |             3 |          4 | Good v1/v2 design reference                  |
| **NII-UIT VBS2025**                | LLM query expansion + temporal search                                                   | Multimodal ranking/search                                          | VBS-style interactive UI                  |                         Unclear |          5 |             2 |          4 | Future query expansion reference             |
| **H-EAGLE**                        | Hierarchical semantic retrieval                                                         | Hierarchical instead of flat indexing                              | Interactive retrieval system              |                         Unclear |          4 |             2 |          3 | Future architecture reference                |
| **PraK / relevance feedback**      | User feedback after result interaction                                                  | Bayes/Rocchio-style feedback/reranking                             | Interactive feedback UI                   |                         Unclear |          4 |             2 |          3 | Future reranking idea                        |
| **GQE**                            | LLM-generated diverse query expansion + query selection                                 | Improves retrieval by expanding query representations              | No UI focus                               |                     Method only |          4 |             3 |          4 | v2 query expansion                           |
| **RRF**                            | Not query handling                                                                      | Simple rank-list fusion                                            | No UI focus                               |                     Method only |          5 |             5 |          5 | Strong v1 fusion method                      |
| **MMMORRF**                        | Multimodal search over user needs                                                       | Modality-aware weighted RRF                                        | No UI focus                               |                    Method/paper |          5 |             4 |          5 | Best fusion-method reference                 |
| **Custom minimal prototype**       | Original query first; query expansion later                                             | Weighted fusion or RRF                                             | Keyframe grid + click timestamp           |                        We build |          5 |             4 |          4 | Fallback if base adoption fails              |

---

## Your source-candidate conclusion

Your current conclusion should be:

> **VISIONE and vitrivr are the only serious “build-from-base” candidates.**
> VISIONE is more developer-friendly and already fits text/image/object/temporal video search. vitrivr is more powerful and has richer query paradigms like sketch/example-object search, but it has a heavier architecture. VERGE is useful as evidence for old multimodal retrieval design, but probably not a base.

That conclusion is fair from the sources.

---

## v0/v1/v2 plan

Use this version.

| Version                                                    | Goal                                                                   | Output                                                             |
| ---------------------------------------------------------- | ---------------------------------------------------------------------- | ------------------------------------------------------------------ |
| **v0 — Base adoption test**                         | Try VISIONE, vitrivr, maybe VERGE/diveXplore if runnable               | Score each base: setup, query features, UI, extensibility, speed   |
| **v1 — Build missing feature / fallback prototype** | If one base is good, extend it. If not, build minimal custom prototype | Working query → ranked keyframes → click video timestamp         |
| **v2 — Performance add-ons**                        | Add tricks after the base works                                        | Query expansion, RRF, OCR/ASR fusion, relevance feedback, grouping |

This is exactly the right direction.

---

## How to measure v0 adoption performance

For each base, score from 1–5:

| Criterion                      | Meaning                                                      |
| ------------------------------ | ------------------------------------------------------------ |
| **Setup success**        | Can we run it locally/server?                                |
| **Time to first search** | How fast from clone to first query?                          |
| **Data import fit**      | Can it ingest our videos or contest-like format?             |
| **Query support**        | Text/image/object/temporal/sketch/OCR/ASR                    |
| **UI quality**           | Does the result UI help fast search?                         |
| **Extensibility**        | Can we add CLIP/SigLIP/OCR/ASR/fusion/custom ranking?        |
| **Stack fit**            | Does it match our team’s Python/React/Faiss/Milvus comfort? |
| **Performance**          | Is search fast enough on sample data?                        |
| **Documentation**        | Can teammates understand and modify it?                      |
| **Contest fit**          | Does it resemble VBS/AI Challenge usage?                     |

Suggested decision rule:

```text
If VISIONE or vitrivr scores ≥ 35/50 and can run a real sample dataset, build on top of it.

If both score < 35/50 or require too much modification, build a custom minimal prototype using:
CLIP/SigLIP + Faiss/Milvus + OCR/ASR text search + RRF + keyframe grid UI.
```

---

## Immediate next step

Before writing the final doc, test only these two:

```text
1. VISIONE
2. vitrivr/Cineast/vitrivr-ng
```

VERGE should stay as “reference only” unless someone proves it is actively maintainable and easy to run.

[1]: https://github.com/aimh-lab/visione
[2]: https://arxiv.org/abs/2008.02749?utm_source=chatgpt.com
[3]: https://videobrowsershowdown.org/teams/?utm_source=chatgpt.com
[4]: https://vitrivr.org/vitrivr.html?utm_source=chatgpt.com
[5]: https://vitrivr.org/getting_started.html
[6]: https://github.com/vitrivr/cineast
[7]: https://dbis.dmi.unibas.ch/publications/2025/feature-driven-video-segmentation-and-advanced-querying-with-vitrivr-engine/?utm_source=chatgpt.com
[8]: https://m4d.iti.gr/verge-interactive-image-video-retrieval-engine/
[9]: https://arxiv.org/html/2509.12000v1?utm_source=chatgpt.com
[10]: https://arxiv.org/html/2502.15683v1?utm_source=chatgpt.com
[11]: https://arxiv.org/abs/2511.12255?utm_source=chatgpt.com
[12]: https://dl.acm.org/doi/10.1007/978-981-96-2074-6_38?utm_source=chatgpt.com
[13]: https://doras.dcu.ie/32449/1/Heagle.pdf?utm_source=chatgpt.com
[14]: https://dl.acm.org/doi/10.1145/3805622.3810635?utm_source=chatgpt.com
[15]: https://arxiv.org/abs/2508.20560?utm_source=chatgpt.com
[16]: https://arxiv.org/abs/2408.07249?utm_source=chatgpt.com
[17]: https://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf
[18]: https://arxiv.org/abs/2503.20698
[19]: https://faiss.ai/index.html?utm_source=chatgpt.com
