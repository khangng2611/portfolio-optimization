# Portfolio Web / BFF

Vietnamese Next.js application and Node.js BFF. Browser cookies contain only opaque random identifiers; access/refresh tokens remain in AES-256-GCM encrypted Redis records. The current flow includes a three-step risk wizard, backend versioned policy, asynchronous EW/MVO/BL_ML proposals, target acceptance and dashboard. Operators can refresh real stock data, submit snapshot-based training, have a separate reviewer approve a candidate, and publish the approved model ID for Quant inference. Investors can preview and confirm a new immutable risk revision. See [onboarding and targets](../../docs/software/WEEKS_6_7.md) and the [Market–Quant bridge](../../docs/software/MARKET_QUANT_BRIDGE.md).

## Run

Run `python3 scripts/setup_software.py up` from the repository root. Open
`/register` or `/login` on localhost:3000. The BFF runs on the same Compose
network as Auth and Redis. The sample environment uses the private Auth hostname.

## Environment contract

| Variable | Meaning |
| --- | --- |
| `APP_ORIGIN` | Exact public origin, e.g. `http://localhost:3000`; never inferred from request Host headers. HTTPS required except explicit localhost mode. |
| `OIDC_ISSUER` | Exact JWT issuer, locally `http://auth-api:8000`. |
| `AUTH_API_URL` | Private Auth origin, locally `http://auth-api:8000`. |
| `AUTH_WEB_SECRET` | Dedicated BFF credential for registration, login and session operations. |
| `REDIS_URL` | Required dedicated session Redis URL; Docker `redis://redis:6379/0`, production `rediss://...` with credentials. |
| `SESSION_ENCRYPTION_KEY` | Required base64-encoded 32 random bytes (`openssl rand -base64 32`). Rotating invalidates existing sessions. |
| `SESSION_TTL_SECONDS` | Absolute session lifetime, default 28800; 60–86400. Cookie, Redis TTL and server expiry are all bounded. |
| `PORTFOLIO_API_URL` | Fixed backend origin, e.g. `http://portfolio-api:8000`; no path, credentials or query. |
| `MARKET_API_URL` | Fixed Market origin, local `http://market-api:8000`; operator inventory/quality/refresh routes only. |
| `QUANT_API_URL` | Fixed Quant origin, local `http://quant-api:8000`; allowlisted publication operations. |
| `ML_API_URL` | Fixed ML origin, local `http://ml-api:8000`; training/model/review routes. |
| `CHAT_API_URL` | Fixed Chat origin, local `http://chat-api:8000`; conversation/message/job/SSE/explanation routes. |
| `ALLOW_INSECURE_HTTP` | Set exactly `true` only for local HTTP Auth and localhost browser access. Otherwise use secure cookies and HTTPS Auth. |
| `OTEL_TRACES_ENABLED` | Set exactly `true` to enable manual BFF tracing; default disabled. |
| `OTEL_SERVICE_NAME` | Trace process resource name, local `web-bff`. |
| `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` | OTLP HTTP endpoint, local container `http://jaeger:4318/v1/traces`. |
| `TRACE_VIEWER_URL` | Trusted server-configured Jaeger base, local `http://localhost:16686`; never taken from caller input or build-time public env. |

Auth issues RS256 access tokens with per-service audiences and role-derived scopes.
Backends remain authoritative for RBAC and ownership.

## Routes and session behavior

- `POST /auth/register` creates an investor account and returns 201. The UI opens /login.
- `POST /auth/login` verifies credentials and returns 204 with an opaque cookie. The workspace opens the risk wizard after a successful empty portfolio read.
- `GET /auth/session`: returns `{authenticated:true,user:{sub,name,roles},csrfToken}` only. Responses disable caching.
- `POST /auth/logout`: requires exact Origin and `X-CSRF-Token`; deletes Redis session before provider revocation. Clears cookies; reports `providerRevoked:false` if Auth cannot confirm revocation.
- `/api/v1/portfolios` GET/POST, `/api/v1/portfolios/{uuid}` GET/PATCH, `/api/v1/portfolios/{uuid}/recommendations` GET/POST, `/api/v1/recommendations/{uuid}` GET, `/api/v1/jobs/portfolio/{uuid}` GET: fixed allowlist to Portfolio. No internal/admin or arbitrary upstream URL routes.
- G2 adds `/api/v1/onboarding/portfolios` POST, `/api/v1/portfolios/{uuid}/dashboard` GET, `/api/v1/portfolios/{uuid}/targets` GET and `/api/v1/recommendations/{uuid}/accept` POST. Accept preserves `If-Match`, checks CSRF and only saves a target.
- Readiness reads are `/api/v1/universes/readiness` and owner-scoped `/api/v1/portfolios/{uuid}/readiness`. These expose data expiry and per-strategy capability without artifact paths. Publication has a separate operator-only allowlist.
- List routes support bounded integer `limit`/`offset`; portfolio lists also accept validated `q`, `risk_profile` and `sort`. JSON bodies remain arrays, with `X-Total-Count`, `X-Limit`, `X-Offset` passed through by BFF. Mutations require JSON, exact Origin, session CSRF token and at most 64 KiB body; recommendation creation additionally requires `Idempotency-Key` (8–128 URL-safe characters). Version preconditions (`If-Match`) and backend version tags (`ETag`) pass through for owner-scoped PATCH. Cookies, caller Authorization, identity headers, upstream redirects and Set-Cookie are never forwarded.
- `GET /health/live` is process liveness, not a claim that dependencies are healthy.

The HTTPS cookie is `__Host-portfolio_session`, with Secure, HttpOnly, SameSite=Lax and Path=/. Local HTTP has explicitly unprefixed, non-Secure cookies. Tokens refresh under Redis NX locks; Lua checks the current lock owner and session existence before storing rotated tokens, preventing expired lock holders or concurrent logout from resurrecting sessions. Redis failures fail closed without queuing requests. Established clients reconnect with a capped delay (at most 2.1 seconds); initial connection setup has a four-second deadline. If Redis restarts without saved sessions, old cookies remain invalid and users must sign in again. Protect Redis with authentication/TLS and no eviction; only trusted BFF instances should access it. Provider revocation failure does not restore a deleted session.

The wizard loads ready universes from `/api/v1/universes`, prefers a verified real-price universe and labels demo data separately. It uses backend policy v1 (risk aversion 6/3/1.5, max position 0.5) and user-entered capital. Each recommendation gets an idempotency UUID, polls the owner-scoped job and displays weights, planned capital and provenance. Target acceptance never changes holdings. The UI ignores superseded portfolio/proposal responses. Same-step serving/core parity does not establish equivalence to the legacy research pipeline.

The workspace supports editing name/planned capital with version conflict recovery,
paginated target/proposal history, and comparison of two proposals. Hash deep links
pin portfolio/proposal IDs and survive reload/back. An expired session remembers
only the navigation destination; signing in never replays an interrupted mutation.
Readiness gates new proposals; expired historical targets remain inspectable.

## Verification

Job/result UI links use persisted `job_trace_id`/`job_trace_url`. `X-Trace-ID`
belongs to the current HTTP request, so polling has its own trace. Only manual
`portfolio-bff` spans with route templates/status are exported; automatic
Next/auth spans are filtered before batching. See [local tracing guide](../../docs/software/TRACING.md).

```sh
npm test
npm run typecheck
npm run build
```

For the real browser gate, run from the repository root with the local stack on
port 3000, disposable test accounts enabled, and a fresh `VN_EQUITY_REAL` bundle
published as described in the Market–Quant guide. It requires Chrome and an
installed Playwright package; set `PORTFOLIO_PLAYWRIGHT_MODULE` to its absolute
module entry when it is not resolvable from the repository.

```sh
node scripts/verify_ui_live.mjs
node scripts/verify_ui_live.mjs --verify-receipt
```

The first command creates a local test portfolio/proposal/target. The second
checks the same saved target, including after a stack restart. Receipts stay in
`infra/local/.generated/`; screenshots and browser logs stay in ignored `output/`.

The reproducible browser CI gate uses the pinned Playwright dependency and
server-registered synthetic DEMO inputs with the real Auth/BFF/DB/broker.
See [browser gate commands and artifact policy](tests/browser/README.md).

Tests cover registration without a session, login throttling, RS256 validation,
encrypted Redis records, CSRF/origin, refresh races, logout and Redis recovery.
The Playwright gate exercises the full local stack.

Market Data Operations runs at `/#market` with the `data-operator` role.
Auth derives Market, Quant and ML scopes from the stored role.

Luồng: đăng ký hash nguồn tin cậy → tạo ingestion → xem chất lượng → tạo snapshot
→ xác nhận phát hành EW/MVO. Báo cáo lỗi lưu trên backend, lô không đạt bị cách ly.
UI có phân trang, deep link báo cáo/job, trạng thái xử lý nền và checksum của nguồn.

Browser gate riêng cần stack disposable đã có ba nguồn CSV giá thật được ghim
SHA-256 (ví dụ nguồn pack `REAL_FPT_*`, `REAL_HPG_*`, `REAL_VCB_*`):

```sh
E2E_DISPOSABLE_STACK=1 npm run test:browser:market
# Sau khi restart các API/worker/web thật:
E2E_DISPOSABLE_STACK=1 npm run test:browser:market:persistence
```

`test:browser` tiếp tục chỉ chạy lifecycle DEMO độc lập với nguồn giá thật.
Fixture Market tạo alias của bytes nguồn hiện có và một nguồn lỗi có nhãn
synthetic; không sửa CSV thật, research data hoặc thông tin đăng nhập.

Gate outage tùy chọn dừng riêng `market-api` local, quan sát worker RETRY rồi
khởi động lại trong `finally`, chờ cùng job thành công và xác minh hash artifact:

```sh
E2E_DISPOSABLE_STACK=1 MARKET_OPS_RETRY_OUTAGE=1 npm run test:browser:market
```

Chạy gate này sau lifecycle Market thành công, trước khi kiểm tra restart receipt.
Các gate giữ token/credentials trong memory, chỉ lưu bằng chứng đã lọc vào `output/`.
Chi tiết phạm vi Figma và giới hạn hiện tại ở [Implementation status](../../docs/software/IMPLEMENTATION_STATUS.md).


## P1 operator and investor flows

- `/#market-refresh`: review/create a trusted KBS stock refresh schedule, toggle it
  with version checks, run manually, and inspect durable jobs/quality/snapshot pins.
  Automatic jobs reconcile the full bounded adjusted-price history; storage adds
  only changed revisions. VNINDEX observed sessions are not a certified exchange
  calendar, and ingestion known-at is not historical point-in-time provenance.
- `/#model-training`, `/#models`, `/#model-review?model=UUID`: explicit training,
  candidate provenance and chronological validation, then a separate model-reviewer
  approval/rejection with a reason. HTTP does not train; approval is never automatic.
  Wait for the approved artifact to become ready before publishing. The serving
  panel reads current universe/model/snapshot/checksum and BL_ML compatibility
  from Quant readiness, showing expiry even while the page stays open.
- Snapshot publication selects `approved_model_id` from the approved registry;
  the server resolves its hash-pinned manifest. No client-supplied artifact URL/path.
- `/#risk-assessment?portfolio=UUID`: server preview before confirmation, reviewed
  If-Match and durable idempotency key, 412 reload recovery, and paginated revision
  history. Confirmation makes old pending proposals stale; accepted target history
  keeps its original weights/profile/policy. Editing answers invalidates preview.
  An uncertain response requires an explicit retry with the same intent.

The BFF routes only allowlisted paths to fixed Portfolio/Market/Quant/ML origins;
backend role/scope/ownership checks remain authoritative. Lists stay arrays with
count/limit/offset headers. ML reads require operator/reviewer access; training
requires `data-operator`, reviews require `model-reviewer`. ML API runs on local
port 8004 and has its own database/worker. Shared Quant training/feature helpers
are a transitional dependency, not a separate algorithm implementation.

From `apps/web`, with the updated real disposable stack already healthy:

```sh
E2E_DISPOSABLE_STACK=1 npm run test:browser:p1
# After an actual API/worker/web process restart and health checks:
E2E_DISPOSABLE_STACK=1 npm run test:browser:p1:persistence
```

This additional gate fetches current KBS data directly, exercises manual and
actual timer jobs, model review/publication and risk reassessment, then records
`infra/local/.generated/p1-browser-receipt.json` without tokens. It has no HTTP
mocks, source aliases or SQL result fabrication. The safe reporter writes
`output/playwright/sanitized/p1-lifecycle.json` and `p1-persistence.json`;
credentials/auth URLs/raw call logs are excluded. See [the browser guide](tests/browser/README.md#p1-real-provider-model-and-risk-gate)
for restart commands and artifact policy. On 27 October 2026 the real P1
lifecycle and same-receipt restart gate both passed, as did P0/Market regressions.
The offline gate passed 451 Python/core and 84 web tests (one optional PostgreSQL
test skipped; separate live DB/fencing probes passed). Existing Figma comparisons cover the
implemented views and do not establish complete future-screen parity or
production certification.

## Chat MVP

OpenAI conversation assistance is opt-in per conversation. The checkbox defaults
off and describes outbound context; the backend persists consent and checks it
before new model calls. Automatic strategy selection asks again when the user
has not specified a supported strategy. Explicit UI intents skip interpretation
to save credits. See [OpenAI setup](../../docs/software/SETUP_AND_API_TESTING.md#openai-dialogue--phương-án-b-05112026).

`/#chat` lists conversations; `/#chat?conversation=UUID&job=UUID` restores a
specific conversation/job. The view reuses the app shell, tokens and existing
allocation/accept UI, with Figma F01/F02/F03 as references. Conversation and message
lists paginate through the real API. Confirmation cards pin backend facts and
versions before allocation; opening a recommendation and accepting its target
remain explicit actions. Chat cannot accept, trade, promote or edit weights.

Configure `CHAT_API_URL`. Auth grants the `chat-api` audience and
`chat:read`/`chat:write` to human accounts. Provider secrets
belong only to the backend worker. BFF routes conversations/messages/chat jobs,
cancel/resume and recommendation explanations through an explicit allowlist.
The backend checks JWT, role/scope and ownership, including every SSE reconnect.

SSE uses fetch with Last-Event-ID, an owner/job-scoped cursor and canonical
refetch on retention reset. The relay isolates headers, handles backpressure and
closes on session expiry/revocation. Pending intents preserve the same
client_message_id/body across reload or uncertain responses. After session expiry,
login does not replay a mutation: the user must explicitly retry/reconfirm.
Results show canonical Portfolio facts; template explanations remain usable
without a configured provider and during a provider outage.

```sh
E2E_DISPOSABLE_STACK=1 npm --prefix apps/web run test:browser:chat
E2E_DISPOSABLE_STACK=1 npm --prefix apps/web run test:browser:chat:persistence
```

Run from the repository root after the API gate and an actual restart between
these commands. See [Chat real-stack gates](tests/browser/README.md#chat-mvp-real-stack-gates)
for real input preparation, outage/restart commands, receipt isolation and
artifact policy. Current evidence and remaining limits are in
[implementation status](../../docs/software/IMPLEMENTATION_STATUS.md#chat-mvp--kiểm-chứng-local-04112026).

## Knowledge references

Chat adds a **Kiến thức** purpose, versioned source excerpts and a separate
reference section on canonical recommendations. Legacy LLM consent remains
visible; the user must explicitly renew to consent v2 for query embeddings.
Consent-off blocks new outbound requests. Lexical/template references remain
usable at budget zero and are not labelled financially verified. Source links
are escaped HTTPS links with opener isolation. No corpus admin UI or automatic
allocation/acceptance is added. Run the real Knowledge browser and persistence
gates described in [the Knowledge runbook](../../docs/software/KNOWLEDGE_RAG.md).
