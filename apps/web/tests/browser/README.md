This is the real browser gate for the disposable localhost Compose stack. It
uses the pinned Playwright Chromium binary, real Keycloak authorization code +
PKCE, BFF cookies/CSRF, PostgreSQL and RabbitMQ. It has no route interception,
mock issuer, external market data downloads or test HTTP endpoints.

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
