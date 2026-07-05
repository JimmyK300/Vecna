# Online Baseline Decision

## Decision principle

The project should **evaluate existing frameworks first** rather than immediately building a custom retrieval system. The first baseline decision is therefore not “which architecture should we invent,” but “is there an existing framework that already gives us enough retrieval, ranking, and UI capability to serve as a base?”

## Candidate-first strategy

The strongest current framework candidates are:

1. **VISIONE**
2. **vitrivr / Cineast / vitrivr-ng**

| Candidate | Link(s) | Why it is being tested |
| --- | --- | --- |
| VISIONE | GitHub: https://github.com/aimh-lab/visione; Paper: https://arxiv.org/abs/2008.02749 | Most developer-friendly current candidate and strongest first adoption test. |
| vitrivr / Cineast / vitrivr-ng | vitrivr: https://vitrivr.org/vitrivr.html; Setup: https://vitrivr.org/getting_started.html; Cineast: https://github.com/vitrivr/cineast | Richer query paradigms, but heavier architecture and higher setup risk. |
| VERGE | https://m4d.iti.gr/verge-interactive-image-video-retrieval-engine/ | Comparison/reference only unless it proves actively maintainable. |

## Decision rule

The baseline choice should follow this rule:

- If an existing framework is suitable, we build on top of it.
- If no existing framework is suitable, we build our own minimal prototype.

“Suitable” here means more than just having interesting retrieval features. A framework must be runnable, understandable, extensible, and compatible with the team’s development constraints.

## Evaluation guideline

Each candidate should be scored with a simple evaluation similar across all options:

- setup success
- time to first search
- data import fit
- query support
- UI quality
- extensibility
- stack fit
- performance
- documentation quality
- task fit

This evaluation should be applied to:

- VISIONE
- vitrivr
- a custom minimal prototype, if framework adoption fails

Using the same criteria keeps the baseline decision fair and evidence-driven.

## If a framework is suitable

If VISIONE or vitrivr proves suitable, the project should:

- adopt that framework as the baseline
- document its missing features
- implement only the smallest necessary extension on top of it

This makes the baseline an **extended existing system**, not a fresh reimplementation.

## If no framework is suitable

If both main candidates are unsuitable, the fallback should be a **minimal custom prototype** with a narrow goal:

- dense visual-text retrieval using CLIP or SigLIP
- OCR/ASR as optional extra text signals
- simple rank fusion such as RRF
- lightweight result grid UI
