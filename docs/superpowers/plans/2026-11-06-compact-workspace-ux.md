# Compact Workspace UX Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task by task.

**Goal:** Reduce wasted space and scrolling to actions; make chat a viewport workspace with an always available composer.
**Architecture:** Keep existing React/Next, API handlers, risk answers, consent and mutation gates. Add a shared action dock inside existing forms, a bounded chat transcript with deliberate scroll following, and compact task layouts. Reuse green/Be Vietnam Pro and the approved product flow. Continue in the existing dirty checkout, preserving unrelated work.
**Spec:** User feedback and attached screenshots, 2026-11-06; previous V2 plan and business constraints remain in force. User previously delegated layout decisions without another design approval round.

## Choices and constraints

- Use a persistent form action dock with reserved bottom space; do not shrink controls below useful hit areas. Readiness, conflicts and explicit create/accept confirmations remain authoritative.
- Chat uses its own scrollable transcript and a compact composer; navigation/context collapse on small screens. Keep full privacy/source information in disclosures and consent visible/off by default.
- Do not hide blocking warnings, auto-send, auto-accept, call LLM, change APIs/scoring, or alter backend data.
- Update only the local web container after checks; preserve secrets, volumes and backend containers. Current localhost:3000 container predates host UI changes.

## Tasks

- [x] Compact shell, context/readiness, method cards and risk forms. Add shared form/review action dock, and move list/compare actions where they are discoverable.
- [x] Chat: bounded transcript, compact composer, contextual title, deliberate follow/jump behavior, and smaller context/navigation regions.
- [x] Verify tests/types/build, desktop/mobile short viewport action visibility, focus, long chat history and user scroll position; inspect screenshots.
- [x] Rebuild/recreate only local web, verify the served bundle and health; record limitations separately from backend E2E.

## Execution and verification

- Shared TaskActions retains form ownership and disabled/confirmation guards. Risk, request, review, edit and comparison actions stay visible with bottom space reserved. List creation and comparison selection are available before long tables.
- Chat uses a bounded transcript, compact composer, contextual title and mobile menu overlay. Initial/latest history follows only when the reader is near the end; older page reading is preserved across incoming-page boundaries.
- Read-only reviewer found an automatic pagination jump and a keyboard consent-save bypass; both were fixed. Three scroll regressions passed after observing failures; browser checks cover the pending consent/native submit guard.
- 113 Vitest tests in 22 files, TypeScript and Docker production build passed. Production UI checked on localhost:3000 at 1440×800, 1280×720, 1024×768, 768×1024, 390×844 and 375×667. Screenshots and repeatable sanitized fixture scripts are in output/playwright/compact-ux.
- Ruling: rebuild/recreate only the existing web container using its existing Compose overlay list, because port 3000 was serving the previous image. Web is healthy with HTTP 200 liveness; backend container IDs are unchanged. Secrets, volumes and data were preserved.
- Runtime health and browser fixtures establish served UI/interaction evidence; no claim of a fresh real-backend PKCE/persistence E2E run.
