# Figma V2.7 frontend implementation

Approved scope: the existing V2.7 Figma section `210:8603`, on page `4:212` in file `YKRbiOAJNoVA9DaSZHc7Wc`. Implement inline in the current checkout; preserve all pre-existing working-tree changes.

1. Overview: compact current-plan context and candidate disclosure; preserve accepted capital, historical selection proof and stale warnings; move allocation and the primary next action ahead of secondary content on mobile. Keep all three sortable allocation columns.
2. Shared asset picker: retain both transfer panes, filtering, canonical ordering and focus recovery; add mobile pane shortcuts, compact empty panes, explicit data statuses and a disclosure for technical metadata. Clarify the separate asset-selection and plan-save actions without changing either request.
3. Chat recommendation: retain canonical-fact comparison and all audit data; organize verified result, positive allocation, evidence, constraints and sources. Keep original server prose in a disclosure. Contextual suggestions only fill the draft and require explicit submission.
4. Verify: meaningful SSR regressions first; existing web suite and TypeScript/build checks; read-only real-stack browser checks at 1440, 390 and 375 pixels, plus unsaved picker interactions and keyboard/focus checks. No conversation/message/recommendation/target creation, data refresh, model calls or backend changes.

Reuse existing React components, Be Vietnam Pro, CSS variables and SVG controls. Do not introduce dependencies, change financial computation or invent evidence/accepted status. Existing defaults of shared components remain compatible with proposal/history screens.

Only the web service may need a frontend rebuild for actual-stack verification; preserve its runtime configuration and all other services/volumes. Screenshots and sensitive receipts remain ignored.

## Verification completed

- Full frontend suite: 34 files, 162 tests passed; TypeScript and production Docker web build passed.
- Real-stack Chrome checks passed at 1440×1000, 390×844 and 375×844. Verified sorting, candidate disclosure, mobile allocation visibility, filtered bulk selection, empty basket, keyboard focus recovery, separate save scope, canonical explanation/audit and draft-only suggestions.
- No horizontal page overflow or browser runtime errors. Zero business-write requests; dashboard, selection history, recommendations and conversation messages were unchanged.
- Screenshots and sanitized receipt: `output/playwright/sanitized/v27/verification.json` (ignored local artifacts). Only the existing web service was rebuilt; runtime environment and ports were preserved.
- Read-only review found no actionable issues. Live send/save/accept flows were deliberately not executed against existing data; screen-reader/device testing was not performed.

## Isolated write-flow verification — 22 November 2026

User authorized the four write flows using separate test data. Registered a new investor account with an initially empty portfolio/conversation inventory, then created three clearly labelled `V2.7 TEST` portfolios and three conversations, one per viewport (1440, 390, 375). Existing-account resources were not used for writes; the new account received 404 when reading the prior V2.6 fixture.

All four flows passed through the real UI/BFF/services:

- Asset save: 201, If-Match and idempotency present, new selection revision/version; unsaved name/capital were not persisted.
- Plan save: 200 with the reviewed version; unsaved basket changes were not persisted and selection history stayed unchanged. Both save scopes survived reload.
- Explain: 202 then SUCCEEDED, canonical facts matched, explanation opened, all 31 weights (including zero rows) remained inspectable. No new recommendation or acceptance occurred. A suggestion stayed draft-only until explicit Ctrl+Enter and continued explaining the old 120m result after current capital became 135m.
- Accept: explanation CTA opened proposal review; explicit acceptance returned 200, advanced portfolio/target to version4 while allocation retained input version3. Reload retained the target and disabled repeat acceptance. Subsequent plan/asset changes preserved the original target/result hashes and showed the stale-input warning. Holdings stayed NOT_TRACKED.

A two-tab stale plan write returned 412 without changing data; explicit reload recovered the latest inputs and subsequent save succeeded without overwriting the competing asset revision.

Found and fixed one frontend-only defect: the recommendation-ID HTML pattern used an unescaped hyphen, invalid under Chrome's Unicode Sets `v` flag. The exact browser regression failed before the single-character escape and passed on the rebuilt deployment, rejecting malformed IDs and accepting the canonical ID. Intended validation characters, API validation and business behavior are unchanged. Full web suite (162 tests), TypeScript, production Docker build and diff whitespace check passed after the fix. Only web was recreated; environment and port bindings were unchanged.

Receipt/screenshots: `output/playwright/sanitized/v27-write/verification.json` and adjacent PNGs. Four configured provider calls returned VERIFIED, estimated total USD 0.000977875. Test fixtures remain separate for inspection. No market refresh, model training, provider-policy change or dependency change was made. Service restart/outage and physical-device tests were not run.
