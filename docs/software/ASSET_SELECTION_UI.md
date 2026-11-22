# Asset basket · V2.6

[Editable Figma desktop, mobile and empty state](https://www.figma.com/design/YKRbiOAJNoVA9DaSZHc7Wc/?node-id=203-8271), updated 2026-11-21. Earlier designs are preserved. New rows reuse one native component; typography, colors and controls reuse the existing file's styles and variables.

The supported-assets pane contains only assets absent from the selected basket. A row button moves one asset between panes. Each pane has a fixed height and independent scrolling; the panes stack on small screens. Search covers ticker, name and description and filters only the supported-assets pane. Bulk add acts on visible results; clearing the basket removes all selections. Moving a row keeps keyboard focus in its source pane. The selected count is announced through a live status region.

When `selection_enabled` is true, onboarding uses the basket directly. The redundant "Cách chọn tài sản" switch is removed. When the feature is disabled or the catalog is absent, the existing universe-based flow remains available. Candidate ordering, request payloads, server validation and readiness checks are preserved.

## Metadata ownership

The supported model universe remains in `portfolio_contracts.assets`: 30 equities plus the pinned GOLD/VFF instruments, structural kind/unit information and canonical ordering. It no longer contains company names or business descriptions. Candidate hashing, model coverage and admission rules are unchanged.

Market owns nullable `asset.display_name`, `description`, `metadata_source`, `metadata_source_symbol` and `metadata_fetched_at` columns. Migration `687eb623cafd` adds them without rewriting asset identities, price revisions or snapshots. `GET /api/v1/market/assets` reads these columns. The authenticated BFF exposes only GET on that fixed route to application readers. The UI merges metadata into the model-supported catalog by identifier, without adding unsupported Market assets or overwriting Quant readiness. During a metadata outage, it uses the ticker and the explicit missing-description state, rather than descriptions embedded in code. Long source descriptions are visually clamped to three lines and retained as accessible text.

`python -m market_service.asset_metadata` runs a one-shot sync, also available as Compose's `market-metadata-sync` profile. It uses vnstock 6.0.1 / vnstock-oapi 0.1.2 for equity `Reference("fhsc").company(symbol).info()`. It validates the returned symbol, bounded nonempty name/profile, strips HTML, and commits each successful record atomically. Upstream failures preserve the last good record and its timestamp. CLI reports contain bounded error codes, never raw credential-bearing vendor exceptions. It exits nonzero when any requested asset cannot be refreshed.

Vnstock's current fund/retail schemas do not provide the required description for the exact existing VFF/GOLD instruments. The sync therefore uses the sources already verified by Market for these two assets and labels their provenance separately:

- VFF: Fmarket product 21, code VFF, owner VINACAPITAL and BOND type must all match. Name/description come from that verified fund record (`fmarket:vff:21`).
- GOLD: the current Giavang monthly archive must match SJC 1L/10L/1KG sell/HCM. Name and explanatory reference text are extracted from its page (`giavang:sjc-sell-hcm`). The existing VND/tael price identity is preserved; foreign gold and other SJC products cannot replace it.

The user confirmed no FHSC source key is available. The old deployed descriptions are retained once in Market DB with `metadata_source="legacy-static"` and no fabricated fetch timestamp. They are not represented as successful vnstock synchronization. An actual equity sync remains blocked until FHSC credentials are supplied; VFF/GOLD can refresh independently using their verified public sources. No source failure silently substitutes another equity provider.

For a future sync, store `FHSC_API_KEY` in the ignored, private `infra/local/.generated/vnstock-metadata.env`; do not send it in chat. Add that file as the last Compose `--env-file`, retain the existing environment/overlay arguments, then run `run --rm --no-deps market-metadata-sync`. To refresh only those instruments, override the command with `market-metadata-sync python -m market_service.asset_metadata --asset-ids GOLD VFF`. No background retry schedule is started while credentials are absent.

Official references: [vnstock Reference](https://www.vnstocks.com/docs/vnstock/v6/tham-chieu-reference), [source keys](https://www.vnstocks.com/docs/vnstock/v6/cai-dat), and [v6 schema changes](https://www.vnstocks.com/docs/vnstock/v6/chuyen-doi/tu-the-he-5).

## Verification · metadata deployment, 2026-11-21

The local `portfolio-auth-demo` stack serves the production build on `http://127.0.0.1:3100`, using its existing port/chat overlays and persisted `USER_SELECTED_ASSETS_ENABLED=true`. Web, Portfolio, Quant and Market images were rebuilt. Existing credentials, volumes, portfolio history, model artifacts and research inputs were preserved. This change does not migrate the separate research environment or root vnstock 4.x requirements.

- Migration `687eb623cafd` applied successfully. All 54,327 price revisions were retained, and the model candidate hash was unchanged.
- A real one-shot sync returned two UPDATED results (VFF/GOLD) and 30 `VNSTOCK_CREDENTIAL_MISSING` results. The 30 old equity descriptions remained unchanged in DB with `legacy-static` provenance and a null fetch timestamp. This is a partial source sync, not a successful vnstock equity fetch.
- Offline: 38 relevant Python tests, 156 web tests and TypeScript checks passed. Production Docker builds passed for all four affected images; the Market container's dependency check passed. Tests cover database reads, successful sync, failed-source preservation, identity mismatch, HTML normalization, unknown/model-unsupported assets, BFF reader authorization and metadata outage fallback.
- Browser/BFF lifecycle: seven tests passed, with only the restart-only test deferred. Individual/keyboard transfers, ticker/description and kind filters, no results, filtered bulk add, clear and empty validation passed on the actual backend. Desktop and mobile viewport checks found no horizontal overflow.
- The browser verified that the model catalog contains only structural identities, while names/descriptions come from the Market endpoint. Market's extra unsupported asset did not expand the 32-asset model basket. A 32-asset portfolio saved, edited to 31, restored to 32 at version 3, reloaded, ran real MVO and accepted the target. Another owner received 404.
- Two explicit BL + ML cases (4 and 10 candidates) and five MVO recommendation jobs succeeded with `USER_SELECTION_REQUIRE_POSITIVE=1`. Admission failures, idempotency, revision conflicts and a genuinely queued job retaining its confirmed risk policy were checked.
- Restart persistence: three tests passed; five mutation tests were intentionally skipped. After restarting nine application/worker services, all eight old/new proposals, selection/risk history, accepted target and all 32 Market metadata records (including provenance/timestamps) matched their saved receipts. Exact-zero allocation rows stayed absent and all three columns sorted correctly in both directions.

The tests reused the existing eligible serving bundle, immutable snapshot `8c2dc496-7d83-4cb2-bc3f-aee78732ee73` and already-approved schema-5 model `70716105-ef74-4203-bfa6-9657f756e0b6`. No retraining, model approval, freshness bypass or new publication was needed for this metadata deployment. BL + ML receipts verify real-data provenance and pinned snapshot/model/input hashes; this is not a research/backtest validation.

Host disk pressure interrupted an initial parallel build. Docker was recovered, builds were then completed individually, and cleanup was scoped to unused build cache, this task's temporary probe environment and superseded images created in this chat. No volume, credential or research-data reset was performed. The earlier Docker memory setting remains 4 GiB. Browser contexts are closed after each case to reduce memory pressure.

Sanitized reports: `output/playwright/sanitized/user-selection-lifecycle.json` and `user-selection-persistence.json`. Actual-stack captures: `output/playwright/asset-transfer-v26-real/`. Token-free private sync/migration/database/deployment evidence is in ignored `infra/local/.generated/asset-metadata-deployment/`; browser receipts are in `infra/local/.generated/user-selection/`, with earlier receipts archived. Earlier isolated component captures (320–2560px) are separate evidence in `output/playwright/asset-transfer-v26/`.
