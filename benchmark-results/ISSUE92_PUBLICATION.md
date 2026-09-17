# Issue 92 publication

The user authorized renaming the research branch to `issue-92` and pushing it
after the overnight run. Historical archive metadata retains the branch name
and uncommitted state at capture time; those frozen files were not rewritten.

Start with `astra-overnight-issue92-return-v1/REPORT.md`. All 11 experiment
archives, the final comparison archive, and the two hash-bound hydrated PR91
ranking/study inputs are included. Model weights and external dataset files
remain external at the immutable paths and SHA-256 bindings in the policies.

Publication checks: 32 focused tests passed; the inherited PR91 control check
verified 49 input hashes and rebuilt the saved study and ledger exactly.
All 2958 archive manifest entries matched their saved bytes before staging.
The local `.gitattributes` preserves evidence bytes, including Windows line
endings, and required ignored artifacts were explicitly staged.

With CRLF-aware whitespace checking, the sole finding is the original blank
line at EOF in the captured `v1/provenance/git-worktrees.txt`. It is retained
to preserve the frozen source snapshot and its hash.

The unrelated parent `PUBLICATION_CHECKPOINT.json` working-copy modification
is excluded and left intact. Publication does not merge anything to main or
modify the original browser branch.
