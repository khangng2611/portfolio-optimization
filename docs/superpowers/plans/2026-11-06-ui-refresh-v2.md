# Portfolio UI V2 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task by task.

**Goal:** Align the existing MVP frontend with the approved editable Figma V2 design.

**Architecture:** Reuse the current client workspace, API contracts, ownership checks, hash routes and request lifecycle. Extract presentation of proposal review, accepted plan and proposal configuration from Home; keep mutations in their existing owner. Use the existing Be Vietnam Pro, green semantic tokens and SVGs, with responsive task-specific layouts.

**Tech Stack:** Next.js 16.3.6, React 19.3.0, TypeScript, plain CSS, Vitest and existing browser tools.

**Spec:** Figma YKRbiOAJNoVA9DaSZHc7Wc, section 89:148175; docs/TECHNICAL_SPECIFICATION_PHASE_2.md sections 11–12 and docs/software/IMPLEMENTATION_STATUS.md.

## Global Constraints

- Keep user edits in this dirty checkout; no backend, algorithm, risk scoring or API contract changes.
- Use live API values, never Figma sample numbers or hypothetical performance metrics.
- Confirm creating a recommendation separately from accepting target weights.
- Preserve stale/conflict/readiness checks, explicit EW fallback, consent off by default and role restrictions.
- No new RAG, trading, holdings or model lifecycle features.

## Review Focus

- Reordered and missing assets: deterministic union and signed B-minus-A percentage-point differences.
- Pending/stale/accepted proposals: prevent invalid accepts and repeated requests.
- Confirmation becomes invalid after a portfolio/input/readiness change.
- Compact chat results must retain canonical facts, sources, explicit review link and LLM consent.
- Mobile tables, context panels, long Vietnamese text, keyboard focus and reduced motion.

## Tasks

- [x] 1. Allocation and comparison: stacked allocation + editable semantic tables, capital and totals first, technical metadata in disclosure; test missing/reordered assets and delta sign/units.
- [x] 2. Proposal and overview: allocation/decision split, accepted target first, request method cards → review → explicit submit; test confirmations and accept states.
- [x] 3. Onboarding, shell and chat: risk choices without changing values, guided layout, concise chat cards, conversation navigation/context and collapsed advanced options; preserve source and consent behavior.
- [x] 4. Responsive visual system and operations: shared density/tokens, semantic statuses and responsive tables without inventing functionality.
- [x] 5. Verify: existing web suite, new meaningful behavior regressions, typecheck, production build, browser screenshots at desktop/mobile and critical interactions. Document visual-only fixture validation separately from real-stack integration.

## Execution notes

- Reuse codex/core-evidence-sprint in place: current uncommitted Chat and lifecycle work is necessary context; moving to a clean checkout would omit it.
- Official Figma design-context read is rate limited on Starter. Read current native nodes/screenshots through figma-mcp-go and cross-check prior V2 exports; do not copy raster UI or temporary asset URLs into code.
- Use self-review unless a final read-only reviewer is dispatched; no commits or deployment requested.

## Verification outcome

- TypeScript, all 110 Vitest tests in 21 files and production build pass. Existing Playwright gates discover 13 tests in four files; their real Compose/PKCE/persistence runs were not executed for this UI task.
- Production browser checks used isolated, sanitized API fixtures. Review/confirm/accept separation, signed deltas, explicit fallback, stale/expiry/conflict guards, role boundaries and chat source/consent paths passed.
- Tested 375, 390, 768, 1024 and 1440 px for page overflow, plus keyboard radio/focus/disclosure behavior. Native initial toggle events could race mobile effects; both chat disclosures now start closed and expand from the desktop media query. Reproduced failure before the fix and passed the targeted browser regression afterward.
- Screenshots, repeatable CLI fixture/check scripts and verification.json are under output/playwright/ui-refresh-v2 (ignored QA artifacts). They are visual/interaction evidence, not backend or investment-result evidence.
- Existing uncommitted application/backend work was retained. No commit or deployment performed.
