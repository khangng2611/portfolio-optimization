# Contextual filters and table spacing

**Goal:** Redesign in the supplied Figma file first, then implement bounded control widths, consistent table gutters and context-specific portfolio selection.
**Scope:** Existing palette/font/business/API behavior. Preserve all dirty user work and original Figma versions.

- [x] Inspect existing tokens and components. Create editable V2.1 Figma designs for management filters, contextual portfolio selection and allocation table at desktop/mobile, with reusable toolbar/row assets. Inspect screenshots before code.
- [x] Management toolbar: search 320 px, risk 184 px, sort 192 px; 40 px desktop and 44 px mobile controls. Context selection uses search and choose, without management filters. Keep existing paging/debounce/API semantics.
- [x] Allocation: bounded analysis lane, 16 px horizontal gutters, approximately 50 px rows; right-aligned fixed numeric columns, same inset for headers/body/totals. Mobile preserves readable card structure.
- [x] Implement the reviewed Figma proposal, then verify routing/filter behavior and screenshots at desktop/ultrawide/mobile. Rebuild only the local web container with existing overlays, preserving backend/data/secrets.

User delegated layout decisions previously; this follow-up requests design-before-code sequencing. Produce the concrete Figma revision before implementation. No new business/API, scoring, trading or performance metrics.

## Outcome

- Figma section 97:194420 contains six desktop/mobile frames and five native reusable assets. Original V2 is preserved. Native structure and bounds checks found no overflow; final screenshots were inspected before code implementation and after the mobile alignment polish.
- Implemented context-specific PortfolioList mode and task-preserving destinations, compact bounded management controls, a bounded allocation lane and aligned numeric columns/gutters. Mobile portfolio items keep essential values together instead of tall label/value stacks.
- Regression first failed when the contextual picker still rendered management filters, then passed after implementation. All 115 tests in 23 files, TypeScript and Docker production build pass. Read-only review found no actionable issue.
- Actual served production UI on localhost:3000 checked with sanitized intercepted API fixtures at 375/390/1440/2064 px: filters, search debounce/page reset, sort, destination retention, no contextual management controls, table bounds/gutters and page overflow. No fresh real-backend PKCE/persistence E2E claimed.
- Only the existing local web service was recreated; health and HTTP 200 confirmed; backend container IDs unchanged. Secrets, volumes and business data were preserved.
- Artifacts: output/playwright/contextual-filters/verification.json and figma/ (ignored QA files).
