# Step 1 Readiness Implementation Plan

> Execution: inline, in the existing research workspace. User authorized continuing the proposed fixes without instructor approval. Implementation inline, independent reviewer required by executing-plans skill; no integration commits, or changes to software services.

**Goal:** Produce a new auditable April2026 baseline with defined input availability and return conventions, and mark READY only for the scope actually validated.

**Architecture:** Preserve the04/10 baseline and historical snapshots. Build a separate candidate input bundle; attach observation time, availability time, source identity and staleness to each record. A fail-closed loader selects only records available by the explicit decision cutoff. Keep model/policy parameters unchanged. Portfolio performance is a frictionless valuation-proxy study; physical fund orders, costs and point-in-time membership remain later experiments.

**Tech stack:** Existing research Python/pandas/XGBoost/CVXPY, unittest, primary/archival source manifests, Markdown and the existing Google Doc.

## Decisions under the user's authorization

- Decision cutoff:18:00 Asia/Ho_Chi_Minh; execution proxy at the next observed session's18:00 valuation. Never call this actual fund execution.
- Equity returns: provider-native adjusted-close price returns. No separate cash dividend credit; do not label this cash-ledger total return. Freeze source/version and use raw provider precision.
- GOLD: one declared archival SJC1L/10L/1KG-HCM provider across the entire period, bid/ask and carry flags retained. Freeze daily close; make it eligible only after its source day ends. PNJ primary samples are comparison evidence, not values spliced into the series.
- VFF: prefer explicit official publication dates matched to actual NAV records. The complete official catalog could not be retrieved from the protected dynamic route. Ruling: use a fixed five-observed-session publication buffer, additionally guarded by any later FMarket record timestamp, for the declared valuation-proxy protocol. This is an a-priori model assumption, not verified first-publication evidence. Strict historical certification remains false.
- Separate information and valuation panels: optimization/features use only information eligible at18:00; portfolio P&L uses subsequent ex-post valuation prices. Do not pretend that a stale known NAV is the actual execution price.
- Readiness distinguishes source claims/assumptions from implementation checks. Do not promote an incomplete input bundle or a hypothetical lag to certified historical availability.

## Tasks

1. Freeze full-period GOLD archive and recover official NAV publication catalog; validate coverage, identity, precision and record matches. Stop on rate limits; retain failed attempts.
2. Write meaningful failing tests for time gating, duplicate/conflicting records, unavailable data, absence of backward fill, future-record invariance and readiness rejection for missing evidence.
3. Implement the small availability/contract loader and prepare the candidate bundle. Keep old inputs and policy params immutable.
4. Run the candidate only after input gates pass; store fresh manifest/source/config/seed/environment. Verify NAV/weights/constraints/turnover, actual ML/BL/selection provenance, and deterministic repeat.
5. Update report and Google Doc with measured outcomes and explicit scope. Replace instructor-confirmation blockers with resolved decisions or concrete missing evidence. Promote READY only if the documented gates pass.

## Required outputs

`outputs/step1/readiness_20261012/`: source manifests, normalized quote/NAV records, availability ledger, input-validation result, accepted-decision record and final readiness checklist. New run artifacts remain separate from the old April exports. Numerical report tables change only after a successful validated run.

## Completion evidence

All five tasks completed for the declared valuation-proxy protocol.35 tests/42 independent checks/21 repeat checks pass. Complete official NAV first-publication archive remains unavailable and is explicitly not certified. Numeric source and33 original inputs preserved. See readiness_status.json and both new run manifests.
