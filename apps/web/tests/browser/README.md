This is the real browser gate for the disposable localhost Compose stack. It
uses the pinned Playwright Chromium binary, real internal Auth registration and login, BFF cookies/CSRF, PostgreSQL and RabbitMQ. It has no route interception,
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
with the account name masked or with the capture limited to the synthetic list.
CI uploads only the named sanitized reports and screenshots.
Vitest excludes this entire directory. To inspect discovery without logging in,
use `npm run test:browser -- --list --reporter=list`.

## Portfolio list, context picker and asset picker visual regression

Enable `USER_SELECTED_ASSETS_ENABLED=true` on the disposable portfolio and quant APIs, then run from `apps/web`:

```sh
E2E_DISPOSABLE_STACK=1 npm run test:browser:portfolio-list -- --update-snapshots=none
```

Set `PLAYWRIGHT_BASE_URL` if the web app uses a different localhost port. The
tests use fresh accounts on the real BFF. They compare the list, context picker
and basket controls at 1440 and 390 px and exercise the narrow layout at 320 px.
The basket capture shows ACB selected and VFF available. Only live asset
names, descriptions and price status are omitted from the capture. The test
exercises the populated rows by keyboard, saves the basket and reopens it. The same Linux amd64 Chromium container is used locally
and in CI.

For an approved visual change, rerun using `--update-snapshots=changed` and review
the six PNGs in `portfolio-list.e2e.ts-snapshots/` before including them in the
change. CI compares against the committed PNGs and retains the actual and diff
images for any visual mismatch.


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
Auth, Redis, PostgreSQL and RabbitMQ running. Publish a fresh **real-price MVO**
universe through the existing Market refresh/publication flow first. This gate
rejects missing or expired real inputs; it does not substitute DEMO data. Run the
API gate before the browser lifecycle, from the repository root:

```sh
.venv-software/bin/python scripts/smoke_chat.py
E2E_DISPOSABLE_STACK=1 npm --prefix apps/web run test:browser:chat
```

The browser signs in through real login, creates its own portfolio and conversation,
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

## Vietnamese Chat status and pinned evidence

On the local `portfolio-auth-demo` stack at port 3100, select a new receipt directory and run from `apps/web`. The baseline opens the owner’s saved conversation and proposal from `output/concise-explanation/paid-final-receipt.json` and checks the recorded facts, allocation and evidence hashes.

```sh
export PLAYWRIGHT_BASE_URL=http://127.0.0.1:3100 E2E_DISPOSABLE_STACK=1
export RAG_STATUS_OUTPUT="$(mktemp -d)"
RAG_STATUS_MODE=baseline npx --no-install playwright test chat.e2e.ts --grep 'real Chat paused followups'
```

Run the exchange on a paused stack with the updated Chat, Web and Portfolio services. The single acceptance worker must have `CHAT_LLM_ENABLED` disabled and `CHAT_PROVIDER_URL` unset. The test opens a legacy failed turn when the signed-in fixture owner has one, opens a new paused turn, asks why, checks current readiness, changes portfolio, asks a knowledge question and reloads the saved proposal. A second owner checks the same four protected resources. The receipt records a null legacy job ID when the first owner has no matching historical turn.

```sh
RAG_STATUS_MODE=exercise npx --no-install playwright test chat.e2e.ts --grep 'real Chat paused followups'
```

After a service restart using the same database volumes, open both conversations and check the original hashes again.

```sh
RAG_STATUS_MODE=verify npx --no-install playwright test chat.e2e.ts --grep 'real Chat paused followups'
```

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

## Knowledge sources and consent

```sh
E2E_DISPOSABLE_STACK=1 npm run test:browser:knowledge
# After actual Chat/Knowledge/Web restart, without regenerating receipts:
E2E_DISPOSABLE_STACK=1 npm run test:browser:knowledge:persistence
```

These use real login/BFF/Chat/Knowledge/Portfolio/Quant. They cover sources,
keyboard/mobile, explicit consent renewal/revoke, missing evidence, canonical
facts and explicit UI acceptance. The allocation case creates its **own**
onboarded portfolio and checks that the API baseline portfolio was unchanged.
Receipts are `knowledge-browser-receipt.json` and
`knowledge-canonical-browser-receipt.json` under ignored `.generated`.
Persistence can also read the initial combined canonical receipt for compatibility.
Provider calls remain disabled; these are lexical gates, not paid semantic RAG
or a completed 60-case conversation evaluation. See the
[full runbook](../../../../docs/software/KNOWLEDGE_RAG.md) and dated status for
recorded limitations, including the initial API-fixture acceptance incident.

## Full Phase 1 K5 + GOLD + VFF gate

This separate gate preserves the equity-only Phase 1 gate. Use the real full
snapshot and reviewed v4 native model on the disposable localhost stack. It does
not ingest synthetic prices, alter availability policy, or increase the seven-day
freshness limit. The accounts file remains the only credential source.

For a genuinely ready date, save the real snapshot receipt as
`infra/local/.generated/phase1-full-snapshot-receipt.json` with a `snapshot` object
(the gate checks its READY/PASS state and the fixed 32-asset order), then run from
`apps/web` with the actual candidate UUID:

```sh
E2E_DISPOSABLE_STACK=1 PHASE1_FULL_MODEL_ID=<candidate-uuid> npm run test:browser:phase1-full
```

`PHASE1_FULL_SNAPSHOT_RECEIPT` can point to another real snapshot receipt. The gate
reviews the candidate through the UI, publishes with max age 7, creates a portfolio
through onboarding, leaves EW fallback unchecked, and waits for the real broker
job to succeed. It checks full output order, all 25 inactive weights equal zero,
K5/selection/fit/model pins, observation availability, effective constraints versus
the requested profile, and stores the exact proposal in the private
`phase1-full-browser-receipt.json`.

When the current **eligible** VFF NAV is older than seven days, run the explicit
stale gate instead:

```sh
E2E_DISPOSABLE_STACK=1 npm run test:browser:phase1-full:stale
```

Supply `PHASE1_FULL_MODEL_ID=<candidate-uuid>` in stale mode to run the reviewer
and publication UI first, using the same real snapshot receipt. The lifecycle
then requires `VFF_STALE`, writes `phase1-full-stale-publication-browser-receipt.json`,
and stops before creating a positive proposal. Without the model environment
variable, stale mode inspects the existing catalog only.

This requires a real catalog response with `VFF_STALE`; it never fabricates stale
prices or changes the system clock. Because unavailable universes are absent from
the onboarding selector, it creates only its own full-universe portfolio through
the authenticated BFF. In the browser it checks the exact seven-day NAV message,
the initially unchecked fallback, and the disabled submit button even after
checking fallback. No recommendation POST may occur. Its separate private receipt
is `phase1-full-stale-browser-receipt.json`; it leaves the successful receipt intact.

After an actual restart of application processes, without deleting volumes,
artifacts or receipts, reopen the successful proposal:

```sh
E2E_DISPOSABLE_STACK=1 npm run test:browser:phase1-full:persistence
```

The persistence gate reads the exact saved proposal, job, publication and reviewer
metadata. A newer serving selection does not change the historical receipt. It
creates no business records. A successful ready run is required before this mode;
a stale-only run is not evidence of successful optimization or restart persistence.
Safe reports are `phase1-full-lifecycle.json`, `phase1-full-stale.json` and
`phase1-full-persistence.json` under ignored `output/playwright/sanitized/`.

## User-selected candidate gate (port 3100)

`user-selection.e2e.ts` is opt-in and refuses port 3000, which is reserved for the
user's SSH tunnel. It uses the real Auth/BFF/Portfolio/Quant/broker stack, the
existing private accounts file and the additive selection schema. Enable the
server feature gate only after reader/consumer verification and the preservation
backup. No synthetic prices, clock changes, relaxed freshness, HTTP interception
or direct database writes are used.

From `apps/web`, after the parent confirms the stack is ready on port 3100:

```sh
E2E_DISPOSABLE_STACK=1 PLAYWRIGHT_BASE_URL=http://localhost:3100 npm run test:browser:user-selection
```

The gate checks the 32-item catalog even with stale VFF, saves one-asset and
stocks-only drafts with explicit policy blocks, and saves 3-equity+VFF and
8-equity+GOLD+VFF choices. It records the actual per-portfolio readiness. A positive
BL_ML test runs only when selected inputs and model are actually eligible; EW
fallback remains unchecked. The broker result must match the saved revision,
candidate order, proof, model/data pins, group/position limits and zero inactive
weights. If no positive case is eligible, the positive test is **skipped** and
receipts say `BLOCKED`; this is not a successful optimization gate. Add
`USER_SELECTION_REQUIRE_POSITIVE=1` when a positive run is required to pass.

The default negative expectation requires real `VFF_STALE`. Only for a genuinely
fresh eligible date, set `USER_SELECTION_EXPECT_VFF_STALE=0`; this does not change
readiness or data. Optional `USER_SELECTION_MODEL_ID` and
`USER_SELECTION_SNAPSHOT_ID` run real model-review and resource-publication UI
steps first. Without them, the parent prepares those resources through authorized
operations. `USER_SELECTION_LEGACY_RECEIPT` can name another existing Alice-owned
Phase 1 proposal receipt; the default is `.generated/phase1-browser-receipt.json`.

After an actual process restart, preserving volumes, credentials and artifacts:

```sh
E2E_DISPOSABLE_STACK=1 PLAYWRIGHT_BASE_URL=http://localhost:3100 npm run test:browser:user-selection:persistence
```

Private receipts stay under `.generated/user-selection/` with mode 0600. The
persistence run compares the exact old proposal, exact new successful proposals
and candidate revisions. Expired proposals must remain visible and disabled.
If only negative cases exist, it records `BLOCKED_NO_POSITIVE_PROPOSAL` instead of
claiming positive proposal persistence. Static sanitized reports are
`user-selection-lifecycle.json` and `user-selection-persistence.json`; credentials,
raw auth traces, storage state and unmasked automatic screenshots remain excluded.
