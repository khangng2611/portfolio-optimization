# Chat MVP — implementation and evidence ledger (04/11/2026)

Authority: TECHNICAL_SPECIFICATION_PHASE_2.md §§5.2–5.4, 6.1, 12, 14 and the user's Chat MVP requirements. Work in the requested existing checkout; preserve unrelated files, credentials, volumes and quantitative semantics. No automatic accept/trade/model promotion. No provider secrets or bearer/grant IDs in events or logs.

Architecture: Chat owns its database, additive migrations, HTTP/SSE API and leased SQL worker, following the existing ML/publication local queue pattern. Portfolio retains allocation saga/outbox/RabbitMQ/Quant. Chat persists dependency before the idempotent owner call and reconciles status; polling supports lost broker notifications/restarts without blocking another worker. Portfolio owns short-lived grants, binds subject/actor/conversation/job/resource/tools and checks account/ownership/expiry on each invocation. Explicit structured confirmation pins versions and canonical facts before mutation. Provider output is a bounded schema of fact/template references, never executable tool instructions or unverified prose.

## Tasks and validation

- [x] 1. Owner grants + contracts: tests deny forged actors, cross-user/resources/tools, stale versions, expiry/revocation/disabled users; additive Portfolio migration; real Keycloak identity/scopes and local DB provisioning.
- [x] 2. Chat persistence/API: conversations/messages/jobs/events/tool audit, atomic dedupe and body conflicts, paging/ownership, one active turn per conversation, finite quota/deadlines and durable confirmations.
- [x] 3. Worker: claim/fence/recover, deterministic intent and input collection, explicit confirmation before allocation, canonical tool facts, reconcile allocation, provider schema/time/token budget and template fallback. Unit tests use injected owner/provider/clock; no simulated integration receipts.
- [x] 4. SSE/BFF: durable monotonic sequence, retention reset, reconnect ownership and authentication, bounded streaming relay/session lifetime/header allowlist. Backend and live integration pass before UI work.
- [x] 5. Frontend: read ui-ux-pro-max, Figma reference and Next local guides. Reuse shell/tokens and actual APIs; history/structured cards/canonical results/progress/session-expiry/reconnect. Explicit accept uses existing Portfolio UI.
- [x] 6. Real integration/browser/restart/outage: preserve IDs/hashes and verify canonical resource history. Review diff, run appropriate suites and update existing operations/status docs. Screenshots, raw logs, receipts and design dumps stay ignored/outside Git.

Review focus: duplicate concurrent sends and conflicting bodies; stale risk/portfolio snapshots; grant expiration/revocation/account disable; expired provider/session streams and reconnect gaps; crash after allocation HTTP success before Chat commit.

Execution: direct implementation authorized by user; no additional design approval gate, new worktree, commit, push or deployment. Report only observed test/evidence results.


## Evidence checkpoint — 04/11/2026

- Original checkout reused; unrelated `extensions_C_v1/` preserved. Direct execution
  authorized, no separate approval/worktree/commit/push/deploy required.
- 503 Python/core tests passed with Chat PostgreSQL concurrency enabled; 1 unrelated
  opt-in test skipped. Web/BFF 90 tests and TypeScript passed before frontend wiring.
- Live DB/broker/Identity boundaries passed. Chat PostgreSQL upgrade and Alembic
  metadata check passed; isolated test schemas cleaned after concurrency tests.
- Real KBS Market refresh through 03/11/2026 and publication succeeded; disabled
  schedule. Receipt `.generated/chat-real-input-receipt.json`, no synthetic inputs.
- Real API gate normal + unavailable provider + actual application restarts passed:
  same Chat/messages/jobs/events, canonical recommendation/input/provenance hashes.
  Receipts `.generated/chat-template-api-receipt.json` and `chat-outage-api-receipt.json`.
- Review findings fixed with regressions: submission retry after portfolio edits;
  resume/new-turn race and per-owner quota on PostgreSQL; provider wall-clock/body
  bounds and durable one-call budget; nonblocking SSE and BFF backpressure.
- Disk exhaustion interrupted one rebuild. User explicitly authorized removal of
  unused image/build caches. Docker pruned 13.61 GB build cache +1.758 GB dangling
  images; no containers/volumes/data/credentials removed. Host regained ~12 GiB.
  Corrupted migration container was recreated from clean source image; migrations
  and business receipts verified after restart. No factory reset or volume prune.
- Figma exact file `YKRbiOAJNoVA9DaSZHc7Wc`: F01/F02/F03 official design contexts
  and screenshots read. UI keeps existing tokens/assets/components. ui-ux-pro-max
  accessibility guidance used; generated dark Enterprise pattern rejected because
  it did not match the existing product/reference.
- Frontend Chat and browser acceptance remain in progress at this checkpoint.


## Final acceptance — 04/11/2026

All six tasks complete locally. Final suites: 508 Python/core passed, 1 optional skip;
102 web tests, TypeScript, Ruff, production builds and 11 contracts passed. Real API
normal/outage, 47-probe authorization (actual 5-minute expiry), browser lifecycle,
SSE cursor/offline/queued-worker restart, session re-confirmation, real-response
latency races, provider outage and both post-restart receipts passed. Existing
tracing overlay retained and extended to Chat. Worker outage config removed.
Source/log privacy audit passed. No commits/push/deploy or unrelated cleanup.
After the final rebuild, another 3.325 GB build cache and 699.5 MB dangling images
were removed under the same user authorization. All 11 volume names were unchanged;
host free space was 8.9 GiB. Stack health and both API receipts were rechecked.

Ruling: use a durable Chat SQL queue and owner status reconciliation, as existing
ML/publication workers do — Portfolio/Quant retain RabbitMQ/outbox allocation;
Chat does not require a new broker notification channel to recover lost hints.
Cost: status polling overhead; dedicated continuation events remain future work.
Ruling: provider output is a validated finite fact/template plan — unverifiable
free prose cannot become financial claims. Cost: intentionally limited language
variety until a commercial provider adapter and broader grounding eval are added.
Ruling: preserve normal and outage receipts in separate files and isolate browser
acceptance portfolios from API-gate portfolios — intentional acceptance must not
invalidate independent API history/version evidence. Cost: extra disposable rows.
