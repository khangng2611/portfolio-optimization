# Local distributed tracing implementation plan

**Goal:** Một recommendation/ingestion mới có trace xuyên HTTP, durable outbox,
RabbitMQ và workers, xem được trong Jaeger local.
**Spec:** `docs/superpowers/specs/2026-10-10-local-distributed-tracing-design.md`.
**Execution:** Hiện thực trong phiên này theo yêu cầu đã duyệt của người dùng;
chia ba vùng độc lập cho agents và primary thực hiện shared primitives/integration.

## Global constraints

- Giữ dữ liệu, credentials, volumes và mọi thay đổi chưa commit đã có. Không commit/push.
- Core `0.1.0`, canonical input hashes và Envelope wire payload không đổi.
- Trace metadata nullable trong owner DB. Không gửi tokens, bodies, SQL values,
  auth callback query hoặc user financial data vào spans/logs.
- Collector outage không gây business failure. Tracing bật qua Compose overlay.
- SDK dependencies pin/lock. Không sửa môi trường nghiên cứu.

## Shared interfaces

New distribution `portfolio-service-observability==0.1.0`, import `service_observability`.

- `configure(service_name: str) -> None`: bật SDK khi `OTEL_TRACES_ENABLED=true`;
  endpoint `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`; bounded batch export.
- `span(name, *, carrier=None, kind=None, attributes=None)`: context manager;
  `carrier=None` dùng current context; supplied carrier extract từ ROOT, detach finally.
- `capture_context() -> dict | None`: W3C headers của current recording context.
- `trace_id(carrier=None) -> str | None`: current hoặc validated persisted context.
- `trace_fields(carrier) -> dict`: `{job_trace_id, job_trace_url}`; URL từ env
  `TRACE_VIEWER_URL` cố định localhost/HTTPS hợp lệ; legacy context trả null fields.
- `link_job(carrier, job_id)`: gắn job ID và span link đến origin khi poll/get result.
- `log_event(stage: str, **safe_fields)`: structured safe metadata, không raw values/bodies.
- `install_http_tracing(app)`: pure ASGI middleware cho `/api/v1` và `/internal/v1`,
  route template/status, `X-Trace-ID`; không capture auth/health/query/header/body.
- `inject_headers(headers=None) -> dict`: giữ caller headers và thêm W3C context.

Broker `publish/consume` signatures giữ nguyên. Shared publish mở PRODUCER span
và inject AMQP headers; consume extract/open CONSUMER span quanh callback/ack.
Dispatcher cần wrap từng row bằng `span('outbox.dispatch', carrier=row.trace_context)`.

## Task 1 — Shared Python SDK and broker (primary)

- [x] RED tests: validated propagation, isolation, exception cleanup, privacy,
  fail-open exporter and ASGI headers, broker send/receive propagation.
- [x] Implement package, dependency metadata, manual spans/logs and broker hooks.
- [x] GREEN tests and add import path/locking/export support.

## Task 2 — Python owner integration (agent)

- [x] Add nullable JSON `trace_context` to all Outboxes, Portfolio/Market Jobs,
  Quant Run; three additive migrations.
- [x] Configure API/worker processes, HTTP middleware, READY resolver outgoing headers.
- [x] Capture contexts atomically; add business spans incl `portfolio_core.allocate`.
- [x] Accepted/status/recommendation return `job_trace_id/job_trace_url`; link GETs.
- [x] Old rows, duplicate/no-op, hash invariants and transaction tests RED→GREEN.
- [x] Update service deps/Dockerfiles to install shared observability package.

## Task 3 — Node BFF and UI (agent)

- [x] OTel SDK/exporter only for manual `portfolio-bff` scope. Ignore automatic
  Next spans that might contain callback queries; export allowlisted attributes.
- [x] Validate incoming traceparent, propagate to Portfolio request, expose trace header.
- [x] UI Job/recommendation trace link uses fixed server-returned `job_trace_url`.
- [x] RED→GREEN tests for propagation, isolation, secrets omitted, disabled mode.
- [x] Tests/typecheck/build; pinned npm dependencies.

## Task 4 — Local overlay, setup and documentation (agent)

- [x] Jaeger2.22.0 with loopback UI16686/OTLP4318, per-process resource names.
- [x] Setup `--tracing`, explicit overlay compose build/up/verification commands.
- [x] CI installation/copy/lint support and optional live trace smoke gate.
- [x] Document in-memory retention, fresh traces, job trace vs poll trace, and safe logs.
- [x] Base+overlay configuration and setup command tests.

## Integration and review (primary)

- [x] Full153 baseline plus new tests, web tests/typecheck/build, deterministic contracts.
- [x] SQLite migration roundtrips; real owner migrations preserve existing data.
- [x] Build with scoped anonymous Docker config if credential helper stalls.
- [x] Live BFF MVO+Market smoke, Jaeger query asserts same trace across full chain,
  exporter outage and dispatcher restart between enqueue/publish.
- [x] Business boundaries/receipt verification remain passing, no secret values exported.
- [x] Independent focused review; fix proven important findings; update evidence/doc.

## Review focus

Remote headers invalid or adversarial; outbox queued before process restart;
concurrent traces/context leaks; client retry maps original job trace;
auth callback token leakage in framework-generated telemetry; collector downtime.

## Completion evidence

Local verification completed 10/10/2026: 188 Python and 44 web tests; Ruff,
contracts/config/typecheck and current-source images. Real DB migrations, original
receipt persistence/boundaries, BFF/Market traces, dispatcher restart and collector
outage passed. Browser verified result trace link and 17-span/7-process timeline.
See `docs/software/IMPLEMENTATION_STATUS.md` for build workaround and limits.
