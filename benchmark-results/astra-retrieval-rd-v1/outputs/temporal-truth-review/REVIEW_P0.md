All 12 P0 anchors in `p0_q22`, `p0_q23`, and `p0_q24` have been inspected against the recovered source media. The three source-video identities and the order of the inspected action passages are supported. Six prior points are retained as representative frames of visible actions; six exact event locators remain unknown. No exact first occurrence is certified, no interval is proposed, and no canonical truth or metric eligibility changes.

The machine-readable record is `review_p0.jsonl`, using `proposed_truth.schema.json`. `CONFIRMED_PRIOR_POINT` in this review means that the existing frame is a useful representative of the observed action. Every such record explicitly leaves `first_occurrence_verified` null and states the limits of the first-frame claim. All 12 original canonical rows, source and submission provenance, query hashes, printed event labels, prior frames, prior proxy windows, and truth tiers remain verbatim in the ledger. The repeated printed `E2` label in the third positional event of `p0_q24` remains unchanged.

| Anchor | Prior frame / source time | Source observation | Proposed locator |
|---|---:|---|---|
| `p0_q22:e1` | 4707 / 188.280 s | The previous wide view cuts to a close-up of flour falling onto asparagus in the bowl. The pour is already visible in the first close-up frame. | Representative point 4707. Physical onset across the edit and first occurrence elsewhere remain unverified. |
| `p0_q22:e2` | 5139 / 205.560 s | A battered asparagus piece moves toward the pan. The preceding wide shot obscures its lower end behind the rim; the anchor close-up directly shows the oil-contact action. | Representative point 5139. The first directly visible contact and the earlier obscured physical contact need a precise interpretation. |
| `p0_q22:e3` | 5427 / 217.080 s | The first visible removal is underway. During the native-frame sequence, the piece rises from near the oil and then clears the pan. | Unknown. Lift onset, full oil separation, and clearance of the pan rim are different possible predicates; the anchor does not resolve them. |
| `p0_q22:e4` | 5865 / 234.600 s | The final visible transfer lowers a stalk onto the loaded plate. The anchor and its immediate neighbors already show the stalk resting there while the chopsticks finish adjusting or withdrawing. | Representative point 5865 for the completed-transfer state. The earliest fully-resting frame and the absolute ordinal “last” are not certified. |
| `p0_q23:e1` | 15945 / 531.500 s | The lion turns while balancing at the numbered poles and then jumps down. Gradual head/body changes occur before and through the anchor. | Unknown. Preparatory movement and the onset of the intended whole-body pivot cannot be cleanly separated at this resolution. |
| `p0_q23:e2` | 16006 / 533.533 s | The lion descends into a crouched landing, then rises. Costume and viewpoint obscure individual feet. | Unknown. The first simultaneous complete contact of all four feet cannot be resolved. |
| `p0_q23:e3` | 16354 / 545.133 s | After landing, the performers face the judges and bow. The rear performer bends visibly; the front performer remains partly hidden by the lion head. | Unknown. An exact first joint bowing frame is not established. |
| `p0_q23:e4` | 16901 / 563.367 s | The lion later approaches the dragon; the dragon head changes orientation in the bounded sequence. Differences around the anchor are subtle. | Unknown. The first deliberate head motion cannot be distinguished confidently from prior small motion and compression. |
| `p0_q24:e1` | 2466 / 98.640 s | A wide cooking view cuts to mushrooms beneath the knife, with sliced pieces already present. | Representative point 2466 for mushroom cutting. First physical cutting and first visible cutting elsewhere remain unverified. |
| `p0_q24:e2` | 3133 / 125.320 s | The close-up shows julienning a white ingredient with cut matchsticks already present; the nearby visible caption reads `CỦ NĂNG CẮT SỢI`. | Representative point 3133 for water-chestnut cutting. The edited close-up does not establish first physical onset. |
| `p0_q24:e3` — printed `E2` | 3420 / 136.800 s | The close-up shows the knife on tofu and subsequent cuts; the nearby visible caption reads `ĐẬU HŨ CẮT KHỐI`. | Representative point 3420 for tofu cutting, with the canonical printed label preserved. First onset remains unverified. |
| `p0_q24:e4` | 3800 / 152.000 s | The pan is placed on the burner and the chef operates the knob. The original still at 3799 already shows blue flame under the pan. | Unknown. The exact ignition frame precedes or is unresolved by the anchor; no correction is inferred from the compressed clip. |

The stove event illustrates a material evidence limit. In the low-bitrate clip, blue flame becomes much more conspicuous around frames 3800–3802. The independently captured original still at 3799 shows blue already present. Comparing the originals prevents a false claim that the compressed clip proves first ignition at 3800 or 3802. A short, higher-resolution source sequence before 3799 is needed to establish an exact onset.

All 51 distinct media assets used here passed SHA-256 and byte-count checks against `vecna82-temporal-truth-source/evidence-index.json`: three query filmstrips, twelve motion clips, and thirty-six original adjacent stills. Each per-anchor ledger record identifies the inspected files and hashes. Query text hashes, prior anchor identities, source-video IDs, and the pinned canonical truth SHA-256 `63f80eb6ff54ef3c623f6ae4926eba404dac8bb5543b86e31f8fa0da842b4c9f` were checked before writing the review. The evidence index reports unchanged source size/mtime after capture; no full source-video hash is claimed.

| Query | Exact source path | Source FPS | Source time base | Clip coverage per event |
|---|---|---:|---:|---|
| `p0_q22` | `videos/L26B/L26_V194.mp4` | 25/1 | 1/12800 | Anchor ±5 s, 251 native frames |
| `p0_q23` | `videos/L24/L24_V033.mp4` | 30/1 | 1/15360 | Anchor ±5 s, 301 native frames |
| `p0_q24` | `videos/L26A/L26_V072.mp4` | 25/1 | 1/12800 | Anchor ±5 s, 251 native frames |

The capture manifest verifies all clip source PTS and labelled samples against zero-based decoded source-frame indices. Source ffprobe reports start time zero and matching average/reported frame rates. Local ffprobe checks confirmed that all twelve delivered MP4s have the expected native frame count and FPS. This establishes the frame mapping for the inspected coverage, without claiming an independent full-video constant-frame-rate audit.

I inspected every query filmstrip and all original anchor−1, anchor, and anchor+1 images. Motion inspection used ordered dense sequences decoded from each bounded clip, selecting every sixth source frame for the 25 FPS clips and every eighth source frame for the 30 FPS clips, plus the exact anchor neighbors. This was frame-sequence inspection, not real-time video playback. No interpolated frames or timestamp seeking were used. Additional comparisons inspected every native frame in these narrow transition windows:

| Anchor | Every-frame inspection | Purpose |
|---|---:|---|
| `p0_q22:e3` | 5418–5448 | Lift onset and separation from oil/pan |
| `p0_q22:e4` | 5838–5870 | Lowering, resting on plate, chopstick withdrawal |
| `p0_q23:e1` | 15939–15961 | Preparatory motion versus rotation |
| `p0_q23:e2` | 15994–16012 | Landing and foot-contact visibility |
| `p0_q23:e3` | 16342–16368 | Positioning and bow onset |
| `p0_q23:e4` | 16891–16920 | Dragon-head motion, including enlarged head crop |
| `p0_q24:e4` | 3790–3810 | Burner ignition, including enlarged burner crop and separate original-still comparison |

The analysis contact sheets are disposable derivatives of the hash-verified clips. Their source-frame ranges and selection rule are recorded above and in the ledger; they introduce no new source evidence. The original ±15-second request was not fulfilled by the ±5-second first pass, and every ledger record says so. Additional context, higher resolution, or a clearer event predicate is required before exact first-occurrence promotion. A camera cut or occluded body part may remain ambiguous even with more surrounding time.

Review status is `SOURCE_MEDIA_REVIEWED` for all twelve records, including unresolved locators. This records that the available source evidence was inspected; it does not make these twelve points organizer truth or resolve every semantic ambiguity. The observed passage sequence is supported separately from exact onset: flour → oil contact → removal → plating; pole turn → landing → judges-facing bow → dragon greeting; mushroom → water chestnut → tofu → stove. Retrieval outputs, candidate ranks, and benchmark results were not consulted for any decision.

Validation passed with `jsonschema` Draft 2020-12 and format checking after overlaying the twelve reviewed rows on the complete 31-row template. Immutable canonical and prior fields were separately compared against the template, all 51 asset identities were checked, all proposed interval boundaries are null, and no first-occurrence field is true. Review ledger SHA-256: `8f0f55d74cc4aac8b37c935d37f9388d8ea8e05305ddb0831c0687bb639a6585`.
