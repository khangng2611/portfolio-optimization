# Portfolio V2.2 layout correction

Keep the existing visual system and business flow. Preserve older Figma sections and unrelated dirty work.

- [x] Figma first: add editable desktop/mobile management and context-selection compositions in the same file; use existing tokens, styles and controls. Management uses a centered 1600px lane and compact table. Context selection uses an 864px lane and one link per row, with name, profile and planned capital only. Show realistic list density with marked illustrative data.
- [x] Update code: align headings, context and surfaces; keep bounded filters and current API queries; reduce table row height; replace the choice table with a semantic compact list; clarify portfolio-scoped risk profile.
- [x] Verify search, filters, pagination, retained destination/portfolio IDs, keyboard focus, long names, loading/empty/error, desktop/mobile/ultrawide. Run applicable tests, types and production build. Deploy only local web and inspect the rendered production result with sanitized fixtures.

No tokens, API, scoring, algorithm, model or trading changes. This is a task-layout correction, not a new design system.

Completed: four editable Figma frames, three reused/adapted component assets, correct font, no raster UI or node overflow. Code/types/120 tests and production build passed. Fixture browser checks passed at seven viewports, including 2560px. Only local web was recreated; four backend IDs stayed unchanged. Evidence: output/playwright/portfolio-layout-v22/verification.json.
