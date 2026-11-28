# Local software stack

Developer policy now controls provider access. The Chat UI has no provider
checkbox or data popover. CHAT_LLM_ENABLED=1 enables outbound Chat calls when
provider/key/budget are configured. CHAT_QUERY_EMBEDDINGS_ENABLED defaults to 0.
Historical consent fields remain readable and cannot grant provider access.
See the current developer policy in docs/software/KNOWLEDGE_RAG.md. Earlier
consent notes below describe the historical behavior.

Chat LLM is optional: apply `compose.chat-llm.yaml` with the base stack and the
tracing overlay already in use. Only `chat-worker` reads the ignored
`.generated/chat-openai.env` secret file. Conversations default to no outbound
LLM consent; the UI enables it explicitly. Daily call reservations default to 20
for the whole Chat service, survive restart, and fall back to rules/templates.
See [OpenAI dialogue operations](../../docs/software/SETUP_AND_API_TESTING.md#openai-dialogue--phương-án-b-05112026)
before running the separate paid browser gate. Do not enable Auto Recharge.

This Compose project is **local development only**: it explicitly permits HTTP,
uses disposable generated accounts and retains a synthetic DEMO bundle. Operator
flows also support trusted KBS stock refresh, snapshot-based manual XGBoost
training, reviewer approval and publication. These flows use real upstream I/O
when requested; DEMO remains separately labelled. Production identity and TLS
are not configured.
All published ports bind to `127.0.0.1`.

From the repository root, use the setup entry point for either a new or existing
local stack:

```sh
python3 scripts/setup_software.py up
```

It prepares the isolated software environment, generates local config, builds
images, starts dependency services, applies the additive upgrade, then starts the
full stack. See the [Vietnamese setup and API guide](../../docs/software/SETUP_AND_API_TESTING.md)
for prerequisites and flags. The manual upgrade commands below assume that the
software virtual environment is already installed.

Open [the web application](http://localhost:3000). Disposable `alice` and `bob`
investor credentials, plus accounts for the other four human roles, are in
`infra/local/.generated/accounts.json` under `users`, with fields `username`,
`password` and `roles`. Read that ignored file locally; do not paste its contents
into logs, screenshots or commits. The bootstrap preserves existing secrets.
`secrets.json` is the source of truth for generated credentials; `.env` is derived
from it. Keep both with the corresponding Docker volumes.

The demo runs as Compose project `portfolio-auth-demo`. If the old project
`portfolio-software` still holds the localhost ports, stop its containers and
keep its volumes. Register at `/register` and sign in separately at `/login`.
Auth has no published host port.

| Component | Local address |
| --- | --- |
| Browser BFF | <http://localhost:3000> |
| Portfolio API | <http://localhost:8001> |
| Quant API | <http://localhost:8002> |
| Market Data API / Swagger | <http://localhost:8003> / <http://localhost:8003/docs> |
| ML API / Swagger | <http://localhost:8004> / <http://localhost:8004/docs> |
| Chat API / Swagger | <http://localhost:8005> / <http://localhost:8005/docs> |
| PostgreSQL | `localhost:5433` |
| RabbitMQ AMQP / management | `localhost:5673` / <http://localhost:15673> |
| Redis | `localhost:6380` |
| Jaeger UI (optional tracing overlay) | <http://localhost:16686> |

RabbitMQ and PostgreSQL use the bootstrap admin `local_admin`. Passwords are in
the ignored `.env`. Each DB has a non-login owner, migrator and runtime role.
`auth-migrate` applies Alembic migrations to `auth_db` and seeds demo accounts.
Keep the private `.generated/auth-signing-key.b64` with the demo configuration.

Market owns `market_db`, its revisions, jobs and immutable snapshots. ML Platform
owns `ml_db`, training jobs, candidate registry and immutable review decisions.
`ml-migrate`, `ml-api` and `ml-worker` have separate migration/runtime duties.
Chat owns `chat_db`: `chat-migrate` uses its migrator, while `chat-api` and
`chat-worker` receive only Chat runtime credentials. Its durable leased SQL queue
is independent of the existing Portfolio allocation outbox/RabbitMQ flow.
Chat uses a dedicated credential for Portfolio delegation, Market reads and
Knowledge retrieval. Portfolio uses a separate read-only Auth credential to
check whether the account is still active when a delegated tool runs.

RabbitMQ's `portfolio` vhost has predeclared direct exchanges
`portfolio.commands`, `portfolio.events`, `market.commands` and `portfolio.dead`.
The `quant.optimize.v1`, `portfolio.results.v1` and `market.ingest.v1` queues, and their `.dead` queues,
are durable quorum queues. Each worker has its own publisher or consumer user:
publishers can write only the owner's exchange, consumers can read only their
own queue, and no runtime user can declare topology. A delivery limit of three
and an at-least-once dead-letter policy bound transient delivery attempts.
`market_publisher` writes only `market.commands`; `market_consumer` reads only
`market.ingest.v1`. Neither can declare queues or access another owner's resources.

The `DEMO` universe uses three fictional assets and predetermined means and
covariance, supporting only EW and MVO. It expires after one day. Refresh is an
explicit action that preserves secrets and old bundles, writes a new immutable
bundle ID, then changes the hash-pinned catalog:

```sh
python3 infra/local/bootstrap.py --refresh-demo
```

The same refresh writes a new immutable CSV with yesterday/today synthetic prices
and replaces `.generated/datasets/catalog.json` with its SHA-256-pinned registration
for `DEMO_STOCK` (stock, VND/share, provider `synthetic-local`). Prior CSVs remain
unchanged. Both adapters reread catalogs for each request, so a catalog refresh
needs no process restart. Market jobs record the accepted dataset hash and reject
changed registrations rather than silently ingesting different input.

Auth derives human scopes from the account role and assigns service tokens
only the audiences and scopes configured for each caller. Backends check those
claims and enforce record ownership.

## Optional local tracing

Enable the OpenTelemetry/Jaeger overlay explicitly:

```sh
python3 scripts/setup_software.py up --tracing
python3 scripts/setup_software.py check --tracing
python3 scripts/setup_software.py verify --live --tracing
```

Pass `--tracing` on each command; it is not stored with credentials. The base
stack keeps tracing disabled. The overlay adds Jaeger all-in-one with in-memory
storage and 100% sampling, loopback-only UI `16686` and OTLP HTTP `4318`.
Each BFF/API/dispatch/consume process has a separate service name. Existing
database, broker and identity settings remain in the base Compose file.
Collector restart clears traces while application data stays in owner databases.

For direct Compose operations, append `-f infra/local/compose.tracing.yaml` after
the base file in **every** build/up/config/stop command. Use `config --quiet` to
avoid expanded credentials. Do not reset volumes to enable or disable tracing.
See [the tracing guide](../../docs/software/TRACING.md) for manual startup,
dispatcher-restart smoke, job trace vs HTTP poll trace, JSON console logs and the
limits of local collection. Only new instrumented jobs have a real timeline.

## Refresh or verify the local demo

Bootstrap preserves generated credentials and the Auth signing key.
The upgrade step reconciles DB and broker grants without resetting volumes.

```sh
python3 scripts/setup_software.py up --refresh-demo
.venv-software/bin/python infra/local/verify_boundaries.py
.venv-software/bin/python scripts/smoke_software.py
```

The checks cover DB and broker permissions, user roles, service token boundaries
and the account-status endpoint. Smoke scripts obtain tokens through Compose exec.
Use `docker compose down` without `-v` to stop the demo and retain its volumes.

## Durable operator publication

`quant-publication` runs independently of investor requests, with Quant's runtime
DB credential and the `quant-publisher` client restricted to Market snapshot reads.
It alone mounts the numerical bundle directory read/write; Quant API and numerical
workers retain read-only mounts. Bootstrap derives `LOCAL_BUNDLE_UID` and
`LOCAL_BUNDLE_GID` from the local operator's numeric identity; only this worker
uses that container user to write the host-owned directory and mode-0600 catalog
lock. The bundle directory stays 0755 and `.generated` stays 0700. Existing stacks
must rerun bootstrap to add these derived `.env` values (existing secrets remain
unchanged), then recreate `quant-publication`; no chown or broad write permission
is required. Apply `quant-migrate` after rebuilding the Quant
image to add `publication_job`; keep the existing generated credentials and volumes.
No investor publication endpoint, model training or approval runs in this worker.

An operator must choose a registered real-data universe, an existing Market
snapshot UUID and its exact content SHA-256. Enqueue with an operator-selected
idempotency key (replace the uppercase placeholders):

```sh
docker compose --env-file infra/local/.generated/.env -f infra/local/compose.yaml exec quant-publication python -m quant_service.publication_worker enqueue --key OPERATOR_KEY --snapshot-id SNAPSHOT_UUID --snapshot-hash SNAPSHOT_SHA256 --universe-id REAL_UNIVERSE
docker compose --env-file infra/local/.generated/.env -f infra/local/compose.yaml exec quant-publication python -m quant_service.publication_worker status --job-id JOB_UUID
```

Add `--model-file MODEL_MANIFEST --model-sha256 MODEL_SHA256` only for an already
approved, provenance-complete v2 real-data model in the bundle directory. Omitting
these pins publishes EW/MVO only. Invalid/stale input fails safely; the worker never
guesses a newer snapshot or selects, trains or approves a model. A new explicit key
is a new publication intent, including when refreshing the same snapshot's serving
window; freshness is validated again. Reusing a key with different request pins or
retry bounds fails with a conflict. Successful output is immutable and history is
retained. `status` exposes only job ID, status, attempt count, safe error and output
pin, and never prints credentials.

The persistent job lease is 120 seconds. Claims are atomic and fenced, expired
leases are reclaimable after a worker restart. Every artifact/catalog write and
recovery validates the active unexpired token, renews it, and holds the job's DB
row lock through local publication and its final result commit. Market network
reads run outside that lock. Old or expired lease holders cannot write output or
finalize a replacement claim. Default maximum attempts is five (`--max-attempts` accepts
1–10); retry waits are 30, 60, 120, 240 seconds, capped at one hour. Invalid input
is terminal immediately. A crash after bundle fsync recovers the identical output
before requesting Market again, even when that historical output has expired.
Serving readiness still rejects an expired output. A terminal job requires operator
inspection and a new explicit key; it is never silently reset.

Scheduling is disabled by default (`PUBLICATION_SCHEDULES: "[]"`). A trusted local
Compose override can set this variable to a JSON array with this shape:

```json
[{"id":"real-daily","anchor":"2026-10-25T00:00:00+00:00","interval_seconds":86400,"request":{"snapshot_id":"SNAPSHOT_UUID","snapshot_hash":"SNAPSHOT_SHA256","universe_id":"REAL_UNIVERSE","model":null}}]
```

Intervals must be 60 seconds to one year; anchors require a timezone. Every tick
enqueues the current due slot using a unique deterministic key, so multiple
schedulers/restarts deduplicate. Missed slots during downtime are skipped; there is
no catch-up burst. Each slot keeps its exact configured snapshot/hash/model pins.
Update pins explicitly when new data is available; an old snapshot eventually
fails freshness validation. Changing request pins inside an already enqueued slot
is a conflict: use a new schedule ID (and anchor) for a changed publication policy.
`run --once` performs schedule enqueue and attempts one due job for manual recovery
or an external supervisor. Avoid logging expanded Compose config; use `config --quiet`.

### Market Data Operations (27/10/2026)

Sau build service mới, chạy `market-migrate` tới head `a7b92401fd52`, rồi
`python infra/local/upgrade.py` và recreate web để nhận các URL/scopes mới.
Không cần reset volume, realm hoặc thay secret. Đăng nhập `data-operator` ở
`http://localhost:3000/#market` (credentials local trong `.generated/accounts.json`).

Kho nguồn tin cậy vẫn là `.generated/datasets/catalog.json` + CSV hash-pinned
được mount read-only vào Market. `GET /api/v1/market/dataset-inventory` trả metadata
an toàn; `POST /api/v1/market/datasets` nhận `{dataset_id, expected_sha256}` với
Idempotency-Key để ghim spec vào SQL registry. Không nhận arbitrary URL/path.
Khi đổi bytes/spec, tạo dataset ID mới; không sửa nguồn đã ghim.

Ingestion qua outbox/broker, kiểm tra toàn lô trước khi ghi revision; báo cáo PASS,
QUARANTINED hoặc NOT_CHECKED được lưu trong DB. Metadata missing basis/known-at
có cảnh báo; lịch phiên chỉ được kiểm đủ khi nguồn có `expected_sessions`.
Legacy revision được kiểm tra lại khi tạo snapshot; report cũ không được bịa/backfill.

Snapshot mới ghim revision IDs/hash. Quant `POST /api/v1/market/publications` nhận
snapshot ID/hash, universe ID, `max_age_days` từ 1–30 (mặc định 7), lookback mặc định 252,
min_returns mặc định 60; role data-operator + scope quant:publish. API chỉ enqueue SQL;
worker `quant-publication` là nơi ghi bundle/catalog. List/get chỉ thấy job do chính
operator tạo. Human API nhận thêm `approved_model_id` để resolve model đã duyệt từ ML Platform;
không nhận model file/path tùy ý, không tự train/approve BL+ML.

Kiểm thử thật và restart receipt: xem `apps/web/README.md`. Gate phát hành dùng
nguồn giá thật đã có trên máy; workflow CI DEMO không phụ thuộc upstream bên ngoài.


## P1: refresh, model operations and risk reassessment

Run the normal additive setup after updating source; keep `.generated`, secrets
and matching volumes. It provisions `ml_db` roles and runs all four application
migrations. New processes are `market-refresh`, `ml-api` (loopback port 8004) and
`ml-worker`; `quant-publication` resolves approved model IDs through ML API.

Data operators use `/#market-refresh` or `/api/v1/market/refresh-schedules`
(GET/POST, individual GET/PATCH) and `/api/v1/market/refresh-jobs` (GET/POST and
individual GET). Create/update/manual-run mutations require Idempotency-Key;
schedule PATCH also requires If-Match. Enabled schedules enqueue real timer jobs;
manual runs use the same durable worker. New schedules start due immediately;
subsequent ticks coalesce missed intervals and do not create an unbounded backlog.
Disable a test schedule when finished. Accepted jobs retain their schedule version.

`kbs-direct-v1` uses fixed server-owned KBS endpoints for bounded stock symbols
and the previous completed Asia/Ho_Chi_Minh day. Each run reconciles the full
configured provider-adjusted history, preserving immutable raw/normalized hashes
and inserting only new/changed price revisions. It is not an overlap-only network
fetch: older adjusted prices can change after corporate actions. The source is
provider-adjusted close, not certified total return or historical adjustment
vintages. VNINDEX bars supply an **observed** session calendar
(`calendar_verified=false`); ingestion availability is not historical point-in-time
knowledge. All assets must pass quality before the immutable snapshot is created.
The existing trusted CSV workflow remains available independently.

The refresh worker alone mounts `.generated/datasets/refresh` read/write; Market
API/ingestion readers mount it read-only. ML worker alone writes
`.generated/ml-models`; ML API, Quant API/optimizer and publication worker read
model artifacts read-only. Only `quant-publication` writes the serving bundle
catalog. Runtime database roles cannot migrate schemas or access another owner DB.

At `/#model-training`, an operator explicitly submits snapshot ID/hash, training
cutoff, lookback and freshness policy to `POST /api/v1/ml/training-jobs`. HTTP only
enqueues SQL work. The worker trains a candidate; it never approves it. A separate
`model-reviewer` uses `/#model-review?model=UUID` and
`POST /api/v1/ml/models/{id}/reviews` with reason, If-Match and Idempotency-Key to
approve or reject. Approval artifact materialization is asynchronous; publication
requires `artifact_ready=true`. `POST /api/v1/market/publications` accepts the
approved UUID as `approved_model_id`, resolved server-side to immutable manifest
pins. Legacy trusted CLI manifest pins remain supported. ML currently imports
Quant's existing versioned training/feature helpers as a transitional package
coupling; it owns its database/artifacts and does not change the core algorithm.

Investors use `/#risk-assessment?portfolio=UUID`. Portfolio's owner-scoped
`POST /api/v1/portfolios/{id}/risk-assessments/preview` maps answers without saving.
GET `/risk-assessments` returns paginated immutable revisions; POST confirms with
If-Match and Idempotency-Key, increments portfolio version and returns a durable
revision receipt. Stale confirmations return 412; pending proposals from the old
portfolio version cannot be accepted (409). New proposals pin the risk UUID/policy;
existing queued hashes and accepted allocations remain unchanged. Manual constraint
edits deactivate the active questionnaire profile without rewriting its history.
Legacy portfolios receive no invented assessment backfill.

P1 browser commands and token-free restart receipts are documented in
[the browser gate](../../apps/web/tests/browser/README.md#p1-real-provider-model-and-risk-gate).
On 27 October 2026, the real KBS P1 lifecycle and same-receipt verification
after restarting 14 application processes passed. P0 and Market lifecycle/restart
regressions also passed; see the implementation status for exact scope.

Refresh histories stay fixed at the configured start and are bounded to 3,650
days. If a schedule ages beyond that window, the timer disables it without
moving its start or creating another job; the API/UI marks the history expired.
Manual refresh rejects an expired window before enqueueing. Operators can still
disable it, or update its start/create a new schedule; old snapshots stay intact.

## Knowledge owner cluster

Normal bootstrap/setup now provisions `knowledge-postgres`, `knowledge-migrate`,
`knowledge-api` (:8006) and `knowledge-worker`. This adds only `knowledge-data`;
existing PostgreSQL images/volumes stay intact. The DB port is internal, roles are
separate, and privileged initialization installs pinned pgvector v0.8.1. Run
`infra/local/verify_knowledge.py` in addition to the existing boundary gate.
See [Knowledge setup/lifecycle](../../docs/software/KNOWLEDGE_RAG.md). The optional
`compose.knowledge-paid.yaml` is disabled by default and requires a new explicit
budget; old Chat keys/consent/quota are not permission to apply it.

## Phase 2 · Danh mục mô phỏng

Trong stack có dữ liệu HYBRID forward, thêm `compose.paper-portfolio.yaml` sau các overlay hiện có. Web và Portfolio API cần được build từ cùng checkout. Migration Portfolio tạo hai bảng tài khoản và quyết định mô phỏng. Dịch vụ `paper-market-export` đọc các capture đã kiểm chứng, xuất giá đóng cửa vào `output/paper-market`. API và `paper-portfolio-worker` chỉ đọc thư mục này. Worker cập nhật tài khoản và kỳ xem xét mỗi phút khi có một phiên mới.

Stack cơ bản đọc được bộ giá đã xuất và đối soát khi user mở danh mục. Overlay dưới đây bổ sung việc xuất giá và cập nhật nền. Nó dùng cơ chế thu thập mở rộng sau ngày kết thúc nghiên cứu HYBRID.

Ví dụ cho một stack local đã bootstrap và có capture forward, chạy từ thư mục gốc. Nếu stack có các overlay bổ sung, giữ chúng trong danh sách Compose đang dùng.

```sh
mkdir -p output/paper-market
paper_compose() {
  docker compose --env-file infra/local/.generated/.env \
    -f infra/local/compose.yaml -f infra/local/compose.hybrid-forward.yaml \
    -f infra/local/compose.paper-portfolio.yaml "$@"
}
paper_compose config --quiet
paper_compose build portfolio-migrate web hybrid-forward-study
paper_compose run --rm --no-deps portfolio-migrate
paper_compose up -d --no-deps hybrid-forward-capture paper-market-export paper-portfolio-worker portfolio-api web
```

Trong một danh mục có mục tiêu đã chấp nhận, mở **Tài sản và hiệu suất** để khởi tạo vốn đầu kỳ. Tại **Tái cân bằng**, xem giỏ lệnh dự kiến và xác nhận hoặc bỏ qua. Lệnh chỉ khớp theo phiên đủ điều kiện sau khi xác nhận. Màn hình hiển thị trạng thái dữ liệu nếu giá chưa sẵn sàng. Nhắc xem xét mỗi năm phiên dùng mục tiêu user đã chấp nhận. [Bằng chứng A/B/C và lựa chọn chế độ thủ công](../../phase2_rebalance/REPORT.md)

Kiểm thử trình duyệt có thể chạy riêng qua `npm run test:browser:paper` từ `apps/web` sau khi cài Chromium của Playwright và môi trường `.venv-software`. Bài kiểm dùng giá cố định, Portfolio API thật và SQLite tạm.
