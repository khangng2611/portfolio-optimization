# Distributed tracing local cho recommendation và ingestion

Trạng thái: người dùng duyệt và yêu cầu hiện thực ngày 10/10/2026.

## Mục tiêu

Xem một recommendation job đi qua Web/BFF, Portfolio API, transactional outbox,
RabbitMQ, Quant worker và numerical core, rồi quay về Portfolio để lưu kết quả.
Giao diện cần cho thấy thứ tự, thời lượng, queue/exchange, lỗi và các lần retry.
Market ingestion dùng cùng tracing primitives. Giữ nguyên identity, ownership,
idempotency, numerical semantics và dữ liệu local hiện có.

Đây là phần triển khai local của mục 13.3 trong
[đặc tả Phase 2](../../TECHNICAL_SPECIFICATION_PHASE_2.md). Hiện source chỉ có
HTTP request IDs và event correlation/job IDs; chưa có OpenTelemetry SDK,
trace-context propagation hoặc trace backend.

## Lựa chọn

| Phương án | Khả năng | Phạm vi |
| --- | --- | --- |
| OpenTelemetry và Jaeger | Trace timeline, span tree, timings và error tags; tìm theo trace/job ID | Chọn cho local debugging/demo |
| Chỉ structured logs và correlation IDs | Tìm các dòng log cùng job; phải tự ghép timeline | Có ích song song, chưa đáp ứng giao diện trace trực quan |
| OpenTelemetry và Grafana stack | Có thể mở rộng traces/logs/metrics nhiều loại | Đợt riêng sau khi tracing tối thiểu được kiểm chứng |

Jaeger all-in-one `cr.jaegertracing.io/jaegertracing/jaeger:2.22.0` nhận OTLP và
cung cấp UI. Chạy local với storage in-memory, sampler 100% để demo; traces mất
khi Jaeger restart. Đây không phải retention backend cho production.
[Tài liệu Jaeger](https://www.jaegertracing.io/docs/2.22/getting-started/).

## Giao diện và vận hành local

- UI tại `http://localhost:16686`, OTLP HTTP tại port 4318; chỉ bind host loopback.
- Thêm Compose overlay tracing để bật/tắt độc lập với stack cơ bản. Stack cũ
  vẫn chạy khi tracing tắt.
- BFF và từng API/dispatch/consume process có service name riêng trong UI:
  `web-bff`, `portfolio-api`, `portfolio-dispatch`, `portfolio-consume`,
  `quant-api`, `quant-dispatch`, `quant-consume`, và ba Market processes.
- SDK export bằng batch có giới hạn. Collector lỗi không làm business request,
  job commit hoặc broker ack phụ thuộc vào telemetry.
- Các SDK/exporter dependencies có version pin và lock khi lập implementation
  plan; không đưa dependencies nghiên cứu vào API hoặc worker images.

## Trace context và durable outbox

HTTP dùng W3C `traceparent`/`tracestate`, được validate trước extract. Chỉ context
đúng định dạng được propagate; không nhận arbitrary baggage hoặc header identity.
[OpenTelemetry propagation](https://opentelemetry.io/docs/languages/python/propagation/).

Mỗi owner service bổ sung nullable `trace_context` metadata trong bảng outbox
qua migration riêng. Context được ghi **cùng transaction tạo event/job**.
Dispatcher extract persisted context, mở producer span rồi inject context của
producer vào AMQP headers. Consumer extract headers, mở consumer span và giữ
context trong callback. Result outbox ghi context của Quant consumer trước
commit, để result dispatcher và Portfolio consumer tiếp tục cùng trace.

Không thêm tracing vào canonical OptimizeCommand/input hash hoặc numerical
request. Không thay đổi wire payload để đưa tokens/user identity vào telemetry.
Core package không import SDK; `portfolio_core.allocate` được instrument ở caller
trong Quant worker. Old outbox rows không có context vẫn xử lý được, tạo trace
mới với correlation/job ID thay vì giả tạo lịch sử trace cũ.

## Span timeline dự kiến

```text
web-bff: POST recommendation
  portfolio-api: authorize + create recommendation job
    quant-api: resolve READY inputs
    portfolio-api: job/outbox transaction
  portfolio-dispatch: publish command
    messaging: portfolio.commands / quant.optimize.v1
    quant-consume: process optimize command
      quant: verify/load prepared input
      portfolio_core.allocate: MVO / CLARABEL
      quant: numerical run/result outbox transaction
    quant-dispatch: publish result
      messaging: portfolio.events / portfolio.results.v1
      portfolio-consume: validate + persist recommendation
```

HTTP 202 kết thúc sớm; trace tiếp tục qua các process bất đồng bộ. RabbitMQ hop
được thể hiện bằng producer/consumer spans và queue/exchange attributes, không
khẳng định đã instrument toàn bộ nội bộ RabbitMQ daemon.

## Tìm trace từ UI hoặc Swagger

- Response header `X-Trace-ID` là trace của HTTP request hiện tại; BFF chuyển nó
  về browser. Request ID hiện hữu vẫn giữ để tra log.
- Job lưu nullable origin trace context trong schema owner; API accepted/status
  trả thêm `job_trace_id`, là trace của submission gốc. Trường này khác trace ID
  của lần poll hiện tại. Recommendation đọc trace reference qua owner-scoped job.
- UI hiển thị job trace ID và link đến Jaeger khi local tracing được bật. Base
  URL cố định từ cấu hình server/local, không nhận URL do caller cung cấp.
- Polling và GET result là HTTP requests mới. Gắn job ID và span link đến origin
  context để tìm theo workflow; không giả định mọi GET là cùng HTTP request POST.
- Job/recommendation cũ không có trace context: không hiện link trace bịa đặt.

## Logs và dữ liệu được thu thập

Structured JSON log có `service`, `trace_id`, `span_id`, `job_id`, `event_id`,
`stage`, `queue`, `status`, `duration_ms`, và safe error type/code khi phù hợp.
Span attributes dùng route template, HTTP status, messaging IDs/destination,
strategy/core version, result status và idempotent duplicate outcome.

Không thu Authorization, Cookie, access/refresh tokens, client secrets, password,
raw request/event bodies, portfolio name/capital/weights, user email hoặc SQL
parameter values. Auth callback URLs có code/state cần loại khỏi instrumentation
hoặc bỏ query; không tự bật header/body capture toàn cục. Error events chỉ chứa
safe type/code và stage; không đưa tùy ý exception payload vào collector.

Jaeger phục vụ traces/span events; JSON application logs vẫn đọc ở Docker logs
và tra theo cùng trace/job ID. Loki/full log backend và production metrics/alerts
không thuộc đợt tối thiểu này.

## Retry, duplicate và context lifecycle

- Mỗi publish/consume attempt có span riêng, cùng origin trace nếu context hợp lệ.
- Inbox duplicate được ghi outcome rõ ràng, không chạy solver hoặc tạo result
  lần nữa để phục vụ tracing.
- Restart dispatcher sau outbox commit vẫn giữ chain nhờ persisted context.
- Context manager luôn detach trong finally; concurrent requests/jobs không
  được mang context của nhau. Invalid context tạo root trace mới.
- Tracing tắt hoặc exporter lỗi không đổi business result/status/ownership.

## Các vùng thay đổi

- Shared Python observability primitives; SDK initialization ở service entry
  points, HTTP hooks và structured logging.
- Web Node instrumentation và BFF proxy context/header propagation.
- Portfolio/Quant/Market outbox metadata migrations và job trace references.
- Shared broker producer/consumer helpers và explicit business-stage spans.
- Local Compose overlay, dependency locks/build contexts, setup/tracing guide,
  deterministic tests và live trace smoke script.

Không thay Keycloak realm/credentials, broker ACL/topology của business queues,
numerical core version hoặc ngữ nghĩa idempotency/hash. Không reset volumes.

## Nghiệm thu

1. Offline tests chứng minh HTTP→outbox→AMQP→consumer propagation; cùng trace ID
   qua command và result; context isolation; invalid headers; duplicate/retry.
2. Migration metadata nullable tương thích old rows; atomic persistence test
   gồm outbox commit rồi tạo dispatcher process mới.
3. Fake exporter/collector outage không làm request hoặc job fail; exporter bounded.
4. Real local MVO tạo trace trong Jaeger chứa BFF/API/dispatch/consume/allocate/
   persist spans; tìm được qua trace ID và job ID; timings có đơn vị rõ ràng.
5. Restart một dispatcher với queued outbox và verify cùng origin trace; business
   receipt, owner isolation và idempotency vẫn đạt.
6. Market ingestion có send/process/DB stages và job trace reference.
7. Kiểm tra span/log exports không chứa generated secrets, tokens hoặc payloads.
8. Giữ toàn bộ Python/web gates; Compose base và tracing overlay đều hợp lệ.

Chỉ các request/jobs mới sau khi bật instrumentation có trace timeline. Bản
ghi recommendation trước đó chỉ có correlation/job IDs, không đủ tái dựng spans
và thời lượng thật của lần chạy cũ.
