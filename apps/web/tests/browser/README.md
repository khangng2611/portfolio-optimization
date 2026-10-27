This is the real browser gate for the disposable localhost Compose stack. It
uses the pinned Playwright Chromium binary, real Keycloak authorization code +
PKCE, BFF cookies/CSRF, PostgreSQL and RabbitMQ. It has no route interception,
mock issuer or test HTTP endpoints. The default DEMO gate does not download
market data; the separate P1 gate below deliberately calls the trusted KBS source.

After bootstrapping, building, migrating and starting the local stack:

```sh
cd apps/web
npm ci
npx --no-install playwright install chromium
E2E_DISPOSABLE_STACK=1 npm run test:browser
```

The test explicitly registers immutable synthetic `DEMO` bundles using
`scripts/browser_fixture.py ready --disposable`. An expired latest bundle tests
freshness gating without deleting historical artifacts. The runner restores a
fresh `DEMO` catalog entry in its `finally` block. Session expiry deletes only
the current test's encrypted Redis session; the opaque cookie travels through
stdin, never command arguments or logs. Use this gate only on a disposable local
stack: it creates portfolios, proposals and a target and changes the `DEMO`
catalog. It preserves credentials, existing data and volumes.

Restart `web`, Portfolio and Quant API/worker processes using Compose, wait for
health, then run:

```sh
E2E_DISPOSABLE_STACK=1 npm run test:browser:persistence
```

The second run logs in again and checks the exact target/proposal identifiers,
allocation SHA-256 and owner-scoped history against the private receipt in
`infra/local/.generated/browser-receipt.json`; it creates no business records.
CI performs both runs around an actual process restart.

Credentials come only from the ignored generated accounts file and never enter
the report. Traces, videos, storageState, automatic screenshots and default raw
error reporters are disabled. The custom reporter records static test names,
status and a safe phase; screenshots are explicit post-login product captures
with the account name masked. CI uploads only the named files in
`output/playwright/sanitized/`, never raw results or generated local config.
Vitest excludes this entire directory. To inspect discovery without logging in,
use `npm run test:browser -- --list --reporter=list`.


## P1 real provider, model and risk gate

Use an updated, migrated disposable stack with `market-refresh`, `ml-api`,
`ml-worker` and `quant-publication` running. Generated accounts must include
`data-operator`, `model-reviewer` and `alice`. No source fixture preparation is
needed: this gate fetches current KBS FPT/MWG/VCB data through the real refresh
worker. It depends on upstream availability and truthful freshness/quality checks.

From `apps/web`:

```sh
E2E_DISPOSABLE_STACK=1 npm run test:browser:p1
```

The lifecycle UI-creates a disabled schedule and manually refreshes it, then
UI-creates a second enabled schedule and waits for a real automatic timer job
without posting a manual job for that schedule. It disables the automatic
schedule after completion and attempts cleanup in `finally` on failure. Manual
and automatic jobs must produce PASS quality and real snapshot pins. The manual
snapshot remains pinned for explicit worker training, independent reviewer
approval, approved-model-ID publication, investor EW history/pending proposal,
risk preview/confirmation and fresh BL_ML acceptance. Role denial, key replay/body
conflict, stale risk If-Match, rejected old proposal and unchanged old allocation
hash are checked. There are no HTTP mocks, copied source aliases, SQL writes,
fabricated job results or automatic model approvals in this gate.

After a successful lifecycle, restart actual application processes from repo root
without deleting data, credentials, artifacts or volumes:

```sh
docker compose --env-file infra/local/.generated/.env -f infra/local/compose.yaml restart web portfolio-api portfolio-consume portfolio-dispatch quant-api quant-consume quant-dispatch quant-publication market-api market-consume market-dispatch market-refresh ml-api ml-worker
docker compose --env-file infra/local/.generated/.env -f infra/local/compose.yaml up -d --wait
cd apps/web
E2E_DISPOSABLE_STACK=1 npm run test:browser:p1:persistence
```

The persistence script sets `P1_VERIFY_RECEIPT=1`. It signs in again, verifies the
same manual/automatic schedules and jobs, snapshot/model/publication hashes,
review decision, risk UUID and both target allocations, then explicitly replays
stored idempotent intents. Create-receipt replay must not re-enable a disabled
schedule or enqueue another automatic job. It does not perform a new source
refresh or train a new model.

The token-free private receipt is
`infra/local/.generated/p1-browser-receipt.json`; keep it with the matching local
volumes/artifacts. Safe report files are
`output/playwright/sanitized/p1-lifecycle.json` and `p1-persistence.json`, alongside
explicit masked product screenshots. Do not enable raw Playwright traces,
HTML/JSON error reporters, storageState dumps or auth-page screenshots. Only
safe static phase names and assertion line numbers enter the reporter. These
commands passed locally on 27 October 2026, including the same P1 receipt after
restarting 14 application processes. P0/Market lifecycle and persistence gates
passed in the same verification run; GitHub CI has not run this P1 gate.
