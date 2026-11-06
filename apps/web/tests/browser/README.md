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

## Chat MVP real stack gates

Use the updated, migrated localhost stack with Chat API/worker, Portfolio/Quant,
Keycloak, Redis, PostgreSQL and RabbitMQ running. Publish a fresh **real-price MVO**
universe through the existing Market refresh/publication flow first. This gate
rejects missing or expired real inputs; it does not substitute DEMO data. Run the
API gate before the browser lifecycle, from the repository root:

```sh
.venv-software/bin/python scripts/smoke_chat.py
E2E_DISPOSABLE_STACK=1 npm --prefix apps/web run test:browser:chat
```

The browser signs in through real PKCE, creates its own portfolio and conversation,
reviews the server's confirmation card, waits for allocation through Portfolio →
RabbitMQ → Quant, compares canonical facts/hashes, and explicitly accepts the
proposal through the existing target UI. It temporarily stops/restarts only
`chat-worker` to observe a persisted SSE event, disconnects/reloads the browser,
and verifies the same job/history without duplicate submissions. Additional cases
expire the current Redis session and require explicit confirmation retry after a
fresh login, and delay genuine Chromium network responses to check stale refresh
and conversation-navigation races. There is no HTTP response interception or SQL
result fabrication. Run serially, without other tests mutating these receipts.

After a successful lifecycle, restart actual application processes, preserving the
tracing overlay when it is enabled:

```sh
docker compose --env-file infra/local/.generated/.env -f infra/local/compose.yaml -f infra/local/compose.tracing.yaml restart chat-api chat-worker web portfolio-api portfolio-consume portfolio-dispatch quant-api quant-consume quant-dispatch
docker compose --env-file infra/local/.generated/.env -f infra/local/compose.yaml -f infra/local/compose.tracing.yaml up -d --wait
.venv-software/bin/python scripts/smoke_chat.py --verify-receipt
E2E_DISPOSABLE_STACK=1 npm --prefix apps/web run test:browser:chat:persistence
```

Provider outage requires a genuinely unavailable provider configured on the
**worker**. Create an override outside Git, for example
`/tmp/chat-provider-outage.yaml`, containing:

```yaml
services:
  chat-worker:
    environment:
      CHAT_PROVIDER_URL: http://127.0.0.1:9/explain
```

Then apply it and run the outage gates:

```sh
docker compose --env-file infra/local/.generated/.env -f infra/local/compose.yaml -f infra/local/compose.tracing.yaml -f /tmp/chat-provider-outage.yaml up -d --no-deps chat-worker
.venv-software/bin/python scripts/smoke_chat.py --provider-outage
E2E_DISPOSABLE_STACK=1 npm --prefix apps/web run test:browser:chat:outage
```

The API gate replaces `chat-api-receipt.json`, so archive the normal receipt under
an ignored filename first if both are needed. Outage and normal browser receipts
are separate. Restore the normal worker configuration even if a gate fails:

```sh
docker compose --env-file infra/local/.generated/.env -f infra/local/compose.yaml -f infra/local/compose.tracing.yaml up -d --no-deps chat-worker
# After another actual process restart, verify the outage browser receipt:
E2E_DISPOSABLE_STACK=1 CHAT_PROVIDER_OUTAGE=1 npm --prefix apps/web run test:browser:chat:persistence
```

Persistence reads saved resources and hashes; it requires no active provider
outage. Reports are `output/playwright/sanitized/chat-lifecycle.json`,
`chat-outage.json`, `chat-persistence.json` and `chat-outage-persistence.json`.
Token-free receipts stay in `infra/local/.generated/chat-api-receipt.json`,
`chat-browser-receipt.json` and `chat-browser-outage-receipt.json`. Explicit
screenshots mask the account name. Keep screenshots, logs and design dumps out of
Git; do not enable raw auth traces, storageState or unfiltered reporters.

On 4 November 2026, four normal cases, one actual outage case and both receipt
checks after restarting nine application processes passed. Desktop and 390px
screenshots were inspected. A separate real authorization gate observes actual
five-minute delegation expiry, revoke, current account/role checks, binding,
stale versions and expired real inputs:

```sh
E2E_DISPOSABLE_STACK=1 .venv-software/bin/python scripts/smoke_chat_authorization.py
```

It creates Bob-owned test records and temporarily disables Bob, restoring the
enabled state in `finally`. Credentials/grants remain in memory. Do not run this
gate concurrently with another test using Bob. It neither accepts a target nor
modifies existing investor data. Local acceptance is separate from GitHub CI or
production certification.

## Chat LLM paid gate

Use `infra/local/compose.chat-llm.yaml` after applying the Chat migration. Store
OPENAI_API_KEY only in the ignored worker env file; do not enable Auto Recharge.
Consent defaults off per conversation. See
[OpenAI setup](../../../../docs/software/SETUP_AND_API_TESTING.md#openai-dialogue--phương-án-b-05112026).

```sh
E2E_DISPOSABLE_STACK=1 npm --prefix apps/web run test:browser:chat:llm
```

One successful lifecycle uses five Responses calls: initial intent, contextual
strategy answer, explanation, recommendation follow-up intent and its explanation.
Confirmations, replay, consent revocation and explicit accept spend no extra calls.
The gate uses the real publication in `.generated/chat-real-input-receipt.json`,
creates a separate investor portfolio and checks only one recommendation. No
HTTP interception or fabricated SQL. Stop and inspect safe job metadata before
rerunning a failed paid lifecycle: a fresh lifecycle would spend more credits.

After a real restart of Chat API/worker/web:

```sh
E2E_DISPOSABLE_STACK=1 npm --prefix apps/web run test:browser:chat:llm:persistence
```

This reads `.generated/chat-llm-browser-receipt.json`, replays original durable
requests and checks resources/hashes/history and per-purpose job usage. It makes
no new provider calls. Reports are `chat-llm-lifecycle.json` and
`chat-llm-persistence.json`; explicit masked screenshots are
`chat-llm-grounded-*.png` in ignored `output/playwright/sanitized/`.

On 5 November, the paid browser flow reached explicit accept with five calls
VERIFIED: 1786 input + 196 output tokens, conservatively estimated $0.00032125.
The final usage assertion initially missed interpretation inside the follow-up
explanation job. A regression now reads `provider_usage` from the job ledger.
Original requests/IDs were recovered from read-only persisted evidence; the
same-receipt browser gate passed after restart without repeating the paid flow.
A real exhausted daily budget returned TEMPLATE without a sixth invocation.
