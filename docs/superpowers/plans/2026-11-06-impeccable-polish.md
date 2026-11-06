# Impeccable Operate polish

Scope is refinement of the current Figma V2.1 / implemented product, not a redesign. No design-system change is proposed: keep Be Vietnam Pro, semantic green palette, type roles, radii and existing token values. Preserve API, ownership, risk scoring, explicit proposal/accept decisions, consent and all unrelated dirty work.

Priorities from source and the rendered localhost app:

- [x] P1: short-height chat clips its controls and leaves no usable transcript (reproduced at 844×390). Remove inherited text-input min-height from the consent checkbox and use the existing compact menu pattern at short intermediate viewports, without losing navigation/logout/context.
- [x] P2: breadcrumb destinations and active navigation disagree with task context. Fix in the shared shell, preserving portfolio context and role gates.
- [x] P2: empty/single-page results show unnecessary disabled pagination. Preserve a concise count and keep previous-page recovery when an offset is still active.
- [x] P2: expose a pending status while a consent write is in flight, preserving pessimistic checkbox state and the submission guard.
- [x] Verify representative desktop/mobile/intermediate/short-height states and long content with sanitized browser fixtures; tests/types/production build; run Impeccable's required detector once after edits; deploy only the existing local web service.

Impeccable context ran once for apps/web/src/app/home.tsx. It found no PRODUCT.md/DESIGN.md/surface brief; this narrow pass uses the explicit product brief, existing code/tokens and current Figma design as authority. No new-product interview or design-system rewrite is needed. No prior critique snapshot was returned. This is a polish pass with its own triage, not a formal scored critique command.

Outcome: 120 tests / 24 files, TypeScript, production build and one Impeccable detector scan passed (0 findings). Production Chromium fixture checks passed at six viewport sizes, including short landscape screens; disclosure bounds and keyboard focus verified. Only the existing local web container was recreated; four backend container IDs stayed identical. Browser checks used sanitized fixtures, not real backend/LLM E2E. Evidence: `output/playwright/impeccable-polish/verification.json`.
