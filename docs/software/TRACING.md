# Distributed tracing local

Tracing dùng OpenTelemetry và Jaeger để xem một job mới đi qua BFF, API,
transactional outbox, RabbitMQ và workers. Bật bằng Compose overlay, giữ nguyên
credentials, volumes, quyền truy cập và ngữ nghĩa recommendation/ingestion.
Stack cơ bản vẫn chạy khi không chọn tracing.

## Bật và kiểm tra

Từ repo root, với prerequisites trong [hướng dẫn setup](SETUP_AND_API_TESTING.md):

```sh
python3 scripts/setup_software.py up --enable-test-client --tracing
python3 scripts/setup_software.py check --tracing
```

Setup cài package `portfolio-service-observability==0.1.0` trong môi trường
software riêng, build images, chạy dependencies gồm Jaeger, áp dụng cấu hình
local bổ sung và khởi động các migration/API/workers. Không reset volumes hoặc
thay credentials cũ. Muốn demo input còn mới, thêm `--refresh-demo` vào lệnh `up`;
CSV và numerical bundle cũ vẫn giữ nguyên.

Mở [Jaeger UI](http://localhost:16686). UI và OTLP HTTP port `4318` chỉ bind
`127.0.0.1`; ứng dụng trong Compose export đến `http://jaeger:4318/v1/traces`.
Overlay dùng image `cr.jaegertracing.io/jaegertracing/jaeger:2.22.0`, all-in-one với
storage in-memory và sampling 100%. Jaeger restart sẽ mất traces trong bộ nhớ;
application jobs/recommendations vẫn nằm trong owner database. Đây là cấu hình
local debugging/demo, chưa phải deployment hoặc retention backend production.
[Jaeger 2.22 getting started](https://www.jaegertracing.io/docs/2.22/getting-started/).

`--tracing` không được lưu vào credentials/settings. Truyền lại cờ ở mọi lệnh
cần overlay:

| Lệnh | Hành vi khi thêm `--tracing` |
| --- | --- |
| `prepare` | Cài dependencies và kiểm tra cấu hình base + overlay; chưa chạy container |
| `up` | Build/chạy base + overlay và Jaeger; áp dụng upgrade trước full startup |
| `check` | Kiểm tra môi trường và merged Compose config; không thay dữ liệu |
| `verify` | Chạy tests/lint/contracts/web như bình thường; không yêu cầu collector |
| `verify --live` | Kiểm tra merged config, DB/broker/JWT, business smoke và tracing smoke trên stack đã chạy |

Sau khi stack healthy:

```sh
python3 scripts/setup_software.py verify --live --tracing
```

Trace smoke tạo recommendation MVO và Market ingestion local, truy vấn Jaeger,
kiểm tra trace/job references và in URL trace để mở UI. Muốn kiểm tra một
outbox đã commit tiếp tục cùng trace sau khi dispatcher restart:

```sh
.venv-software/bin/python scripts/smoke_tracing.py --restart-dispatcher
```

Lệnh này thay đổi trạng thái dispatcher local trong lúc probe và tạo các job
local; không xóa application data hoặc consume trực tiếp business messages.
Chỉ chạy trên stack disposable đã bật overlay. Không dùng cho staging/production.

Thêm `--collector-outage` để tạm dừng riêng Jaeger, chạy business smoke MVO và
Market trong lúc collector không hoạt động, rồi bật Jaeger và tạo trace demo mới.
Restart Jaeger xóa traces trong bộ nhớ; các jobs/kết quả trong PostgreSQL vẫn giữ.
Smoke đọc trace bằng stable OTLP JSON query API `/api/v3/traces/{trace_id}`.
[Jaeger query APIs](https://www.jaegertracing.io/docs/2.22/architecture/apis/).

Nếu cần chạy Compose trực tiếp, mọi lệnh tracing cần **cả hai** file, theo thứ tự:

```sh
docker compose --env-file infra/local/.generated/.env -f infra/local/compose.yaml -f infra/local/compose.tracing.yaml config --quiet
docker compose --env-file infra/local/.generated/.env -f infra/local/compose.yaml -f infra/local/compose.tracing.yaml build
docker compose --env-file infra/local/.generated/.env -f infra/local/compose.yaml -f infra/local/compose.tracing.yaml up -d --wait postgres rabbitmq redis keycloak jaeger
.venv-software/bin/python infra/local/upgrade.py
docker compose --env-file infra/local/.generated/.env -f infra/local/compose.yaml -f infra/local/compose.tracing.yaml up -d --wait
```

Chỉ dùng `config --quiet` khi log. `config` thông thường expand secrets trong
connection URLs và environment. API/worker migrations vẫn dùng migrator riêng;
runtime processes vẫn dùng credentials riêng của owner. Tracing không mở quyền
broker hoặc tạo thêm business queues.

## Đọc timeline của job

Tạo recommendation mới từ web sau khi bật tracing. Job UI/API có `job_trace_id`
và `job_trace_url`; mở URL này để xem submission và xử lý bất đồng bộ. Có thể
tìm trực tiếp trace ID trong Jaeger hoặc tìm service/span theo `job_id`.
Các process có resource names riêng:

- `web-bff`
- `portfolio-api`, `portfolio-dispatch`, `portfolio-consume`
- `quant-api`, `quant-dispatch`, `quant-consume`
- `market-api`, `market-dispatch`, `market-consume`

HTTP POST trả `202` và kết thúc trước khi job hoàn tất. Context được lưu cùng
job/outbox transaction, rồi dispatcher gửi AMQP headers W3C. Consumer tiếp tục
trace này, xử lý numerical core, ghi result outbox và đưa kết quả về Portfolio.
Trong timeline, xem các producer/consumer spans, queue/exchange attributes,
`portfolio_core.allocate`, lưu kết quả, status/error và các retry attempt. Thời
lượng span có đơn vị từ Jaeger; khoảng trống giữa spans có thể là thời gian chờ
queue hoặc lịch chạy dispatcher, không phải solver đang chạy liên tục.

`X-Trace-ID` trong response là trace của **HTTP request hiện tại**.
`job_trace_id` là trace submission gốc đã lưu. Poll status và GET result tạo HTTP
trace mới, có span link tới origin cùng `job_id`; vì vậy trace ID của poll có thể
khác job trace ID. Không ghép mọi GET thành POST ban đầu và không diễn giải HTTP
202 là solver đã hoàn thành.

RabbitMQ hop được thể hiện ở application producer/consumer spans. Overlay không
instrument toàn bộ nội bộ RabbitMQ daemon. Core không phụ thuộc SDK; caller trong
Quant instrument lời gọi allocation. Bản ghi có trước tracing không đủ dữ liệu
để tái dựng thời lượng/spans thật; nullable trace fields không tạo link giả cho
job cũ. Jaeger đã restart cũng có thể làm URL của một job đã trace trả không tìm
thấy trace, dù application result vẫn tồn tại.

## Logs, lỗi collector và tắt tracing

Ứng dụng ghi JSON logs ra console/Docker logs, có safe `service`, `trace_id`,
`span_id`, `job_id`, `event_id`, stage/status/duration khi phù hợp. Tra theo trace
hoặc job ID để nối logs với timeline:

```sh
docker compose --env-file infra/local/.generated/.env -f infra/local/compose.yaml -f infra/local/compose.tracing.yaml logs --tail 100 portfolio-api portfolio-dispatch quant-consume quant-dispatch portfolio-consume
```

Jaeger lưu traces và span events. Loki, centralized log storage, production
metrics/alerts chưa thuộc cấu hình này. Không copy generated credentials hoặc
tokens vào logs/screenshots. Instrumentation không capture Authorization/Cookie,
password/client secret/access-refresh token, raw request/event body, query của
auth callback, SQL parameter values hoặc dữ liệu tài chính của người dùng.

Export dùng batch có giới hạn. Collector lỗi hoặc không truy cập được không làm
business request/job commit/broker ack phụ thuộc telemetry; có thể mất spans và
không nên suy diễn không thấy trace nghĩa là job chưa xử lý. Kiểm tra job status,
service logs và collector trước. SDK flags/name/endpoint chỉ nhận từ cấu hình
server local; caller không cung cấp trace-viewer URL tùy ý.

Để tắt instrumentation, chạy lại ứng dụng với base stack:

```sh
python3 scripts/setup_software.py up --skip-build
```

Compose sẽ cập nhật application environment về base. Jaeger có thể còn chạy như
một orphan của lần dùng overlay; nếu muốn dừng collector mà giữ database/queue
volumes:

```sh
docker compose --env-file infra/local/.generated/.env -f infra/local/compose.yaml -f infra/local/compose.tracing.yaml stop jaeger
```

Không dùng `down -v` hoặc xóa `.generated` để tắt tracing.

Workflow GitHub Actions luôn kiểm tra overlay config. Live tracing gate là tùy
chọn qua **Run workflow → tracing**, dùng runner disposable và
`smoke_tracing.py --restart-dispatcher`. Thêm workflow không có nghĩa gate đã
chạy trên GitHub; bằng chứng live/offline của lần hiện thực nằm trong
[implementation status](IMPLEMENTATION_STATUS.md).
