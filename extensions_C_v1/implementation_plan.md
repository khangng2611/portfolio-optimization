# Additional experiments C implementation plan

Specification: exact supplied experiment_1.md; detailed numeric choices in protocol_frozen.md. User requested execution and a new folder; reuse the current checkout and isolate all additions under extensions_C_v1. No new repository worktree, dependency install or edits to frozen evidence are needed.

- [x] Freeze and snapshot resolved permitted inputs, reference docs, source/environment and timestamps before C results; reconcile B1/B2.
- [x] Add tests, implement deterministic seven-asset targets, membership resolution and fail-closed C2 input/alignment helpers; reuse verified pure accounting from experiments_core by hashed source snapshot.
- [x] Execute C1 twice, compare to B1/B2 including costs and paired bootstrap, independently replay actual units and all trade unions.
- [x] Verify C2 source, vintage and rights; either run an aligned total-return comparison or deliver the protocol-required feasibility stop with exact gaps and a tested future ingestion path.
- [x] Produce 5–10 page report, identification table, charts, dictionary, validations, issues and optional C3–C6 proposals. Verify packaging and upload to a separate folder if accessible.

Design choices already fixed by the assignment: C1 rule and frozen selector/calendar; same gross/event-cost semantics; no new optimizer or training. C2 is externally sourced and cannot use the existing price-only VNINDEX data. Implementation uses source-verified local inputs rather than reconstructing state from manuscript prose.

Delivery completed 2026-11-04: 19 files visibly verified in the new Drive folder. See submission_receipt.json. Pre-result plan remains unchanged in both run source snapshots.
