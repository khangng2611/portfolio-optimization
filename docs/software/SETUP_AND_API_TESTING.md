# Setup và kiểm thử API phần mềm

Để xem timeline của request qua BFF, RabbitMQ và workers, xem
[hướng dẫn OpenTelemetry + Jaeger](TRACING.md). Có thể bật cùng quá trình setup:
`python3 scripts/setup_software.py up --enable-test-client --tracing`.

Đây là điểm vào cho phần ứng dụng trong `apps/`, `services/`, `packages/` và
`infra/`. Các lệnh dưới đây chạy từ repo root. Môi trường `.venv-software` độc
lập với môi trường nghiên cứu Phase 1; không cài `requirements.txt` ở root để
chạy các service.

## 1. Chuẩn bị và chạy bằng một lệnh

Máy cần Python **3.12**, Node.js **>=22.12** (khuyến nghị Node 22 LTS), npm và
Docker Desktop với Compose v2. Mở Docker Desktop, kiểm tra còn đủ dung lượng
trống cho images/build/volumes. Chỉ chạy stack local trên máy phát triển.

```sh
python3 scripts/setup_software.py up --enable-test-client
```

Script kiểm tra công cụ, tạo hoặc dùng lại `.venv-software`, cài các package
software theo constraints, dùng `npm ci` khi cần, bootstrap secrets/demo,
kiểm tra Compose, build images và chạy stack. Nó khởi động PostgreSQL,
RabbitMQ, Redis, Keycloak trước; sau đó chạy `infra/local/upgrade.py` để bổ
sung DB/broker/scopes/client cho cấu hình local cũ, rồi bật toàn bộ service
và chờ healthchecks. Không có bước xóa volume hoặc đặt lại realm.

Các chế độ hỗ trợ:

| Lệnh | Mục đích |
| --- | --- |
| `python3 scripts/setup_software.py --help` | Xem tùy chọn |
| `python3 scripts/setup_software.py check` | Chỉ đọc: công cụ, Docker daemon, môi trường và Compose config |
| `python3 scripts/setup_software.py prepare --enable-test-client` | Cài dependency và sinh cấu hình; chưa khởi động container |
| `python3 scripts/setup_software.py up --skip-install --skip-build` | Dùng môi trường/images hiện có đã hợp lệ |
| `python3 scripts/setup_software.py up --enable-test-client --refresh-demo` | Làm mới demo bất biến rồi chạy stack; giữ secrets và dữ liệu cũ |
| `python3 scripts/setup_software.py verify` | Python/API/core tests, Ruff, export contracts, web tests/typecheck/build |
| `python3 scripts/setup_software.py verify --live` | Thêm DB/broker/auth boundary và real-JWT asynchronous smoke trên stack healthy |

`--python /đường/dẫn/python3.12` chọn interpreter khi không có lệnh
`python3.12` trong PATH. `--skip-build` chỉ dùng khi images đã phản ánh source
hiện tại. `check` không sửa file hoặc khởi động container; lỗi Docker có nghĩa
chưa kiểm chứng runtime, không đồng nghĩa API tests thất bại.

Mở [web](http://localhost:3000), đăng nhập với tài khoản local. Credentials nằm
trong hai file ignored:

- `infra/local/.generated/accounts.json`: `users[]` có `username`, `password`,
  `roles`; dùng `alice`/`bob` cho kiểm thử owner, `data-operator` cho Market/ML
  training và `model-reviewer` cho duyệt/từ chối model.
- `infra/local/.generated/.env`: `OIDC_TEST_CLIENT_SECRET` và
  `QUANT_CLIENT_SECRET` cho các request auth bên dưới.

Đọc các file này tại máy, giữ credentials trong kho bí mật hoặc giá trị local
của Postman. Không đưa nội dung vào commit, log, ảnh chụp hoặc environment export.
Giữ `secrets.json`, `.env` và volumes đi cùng nhau. Bootstrap giữ secrets cũ;
thay password trong file không tự đổi password đã cài vào database/identity.

`--enable-test-client` cần được bật **trước lần realm import đầu tiên**. Client
`portfolio-test` cho password grant chỉ phục vụ disposable local realm.
Với stack cũ đã import, chạy lại lệnh `up --enable-test-client`: bước upgrade
bổ sung client thiếu và Portfolio/Market/Quant/ML scopes/audience qua admin API mà không reset
realm. `portfolio-web` của trình duyệt luôn dùng authorization code + S256
PKCE; password grant và implicit grant bị tắt.

## 2. Địa chỉ và quyền truy cập

| Thành phần | Local URL |
| --- | --- |
| Web/BFF | [localhost:3000](http://localhost:3000) |
| Keycloak | [localhost:8080](http://localhost:8080) |
| Portfolio Swagger | [localhost:8001/docs](http://localhost:8001/docs) |
| Quant Swagger | [localhost:8002/docs](http://localhost:8002/docs) |
| Market Data Swagger | [localhost:8003/docs](http://localhost:8003/docs) |
| ML Platform Swagger | [localhost:8004/docs](http://localhost:8004/docs) |
| OpenAPI JSON | `/openapi.json` trên mỗi API port |
| Health | `/health/live`, `/health/ready` trên mỗi API port; không cần JWT |

JWT phải có chữ ký hợp lệ, issuer `http://localhost:8080/realms/portfolio`,
audience đúng service, chưa hết hạn, role và scope phù hợp. Không dùng ID token
hoặc cookie BFF để gọi Bearer API trực tiếp.

Access token phải có `sub` để owner-scoping hoạt động. Bootstrap/upgrade gắn
default scope `basic` với Subject mapper cho web, service và test client.
Realm local cũ cần chạy bước upgrade để bổ sung; lấy token mới sau upgrade.

| API | Token/quyền |
| --- | --- |
| Portfolio GET | Human role hợp lệ + `portfolio:read`, audience `portfolio-api` |
| Portfolio POST/PATCH | Human role hợp lệ + `portfolio:write` |
| Market đọc | Human role hợp lệ + `market:read`, audience `market-api` |
| Market ingestion/snapshot | Role `data-operator` + `market:write` |
| Quant ready-input | Service token có `quant:resolve`, audience `quant-api` |
| Quant publication | `data-operator` + `quant:publish`, audience `quant-api` |
| ML đọc models/jobs | `data-operator` hoặc `model-reviewer` + `ml:read`, audience `ml-api`; training jobs giới hạn người tạo |
| ML training | `data-operator` + `ml:train` |
| ML review | `model-reviewer` + `ml:review` |

Portfolio và Market ingestion job dùng issuer/subject từ JWT để giới hạn owner.
Đổi token sang `bob` khi đọc portfolio/job/recommendation của `alice` phải nhận
**404**. Role admin cũng không tự mở quyền đọc danh mục riêng của người khác.
Market assets/prices/snapshots là dữ liệu dùng chung cho người có quyền đọc;
Market ingestion job chỉ người tạo được đọc.

## 3. Nhận JWT và dùng Swagger

Import Postman ở mục 4 là cách thuận tiện để nhận token mà không viết password
vào lệnh shell. Request token của human user là:

```text
POST http://localhost:8080/realms/portfolio/protocol/openid-connect/token
Content-Type: application/x-www-form-urlencoded

grant_type=password
client_id=portfolio-test
client_secret=<OIDC_TEST_CLIENT_SECRET từ file ignored .env>
username=<alice hoặc data-operator>
password=<password tương ứng từ accounts.json>
scope=openid portfolio:read portfolio:write market:read market:write quant:publish ml:read ml:train ml:review
```

Token của `alice` đọc được Market nhưng không được Market write vì thiếu role
`data-operator`. Lấy token của `data-operator` cho ingestion/snapshot. Token test
client được upgrade các audiences Portfolio/Market/Quant/ML; quyền human không
mở các endpoint internal service-to-service.
Với Quant, dùng `grant_type=client_credentials`, `client_id=portfolio-service`,
`client_secret=<QUANT_CLIENT_SECRET>`, `scope=quant:resolve`.

Tại `/docs`, nhấn **Authorize**, dán giá trị `access_token` vào Bearer security
scheme rồi nhấn **Authorize** và **Close**. Chỉ dán token, không thêm tiền tố
`Bearer ` trong hộp này. Chọn endpoint → **Try it out** → nhập JSON/header/query
→ **Execute**. Swagger gửi `Authorization: Bearer <token>` tự động. Nhận 401
thì lấy access token mới; 403 thì kiểm tra role/scope/audience.

Health endpoints dùng được trước khi authorize. Quant Swagger có cả contract
service-to-service và operator publication; trình duyệt gọi allowlist qua BFF,
không giữ Bearer token hay gọi trực tiếp service origin.

## 4. Postman: import và chạy theo thứ tự

Import hai file:

- [Collection](postman/portfolio-software.postman_collection.json)
- [Environment](postman/local.postman_environment.json)

Chọn environment **Portfolio software — local**. Điền các giá trị secret tại
máy: `test_client_secret`, `alice_password`, `bob_password`,
`operator_password`; `quant_client_secret` nếu muốn thử Quant. Các giá trị
secret/token trong file đã lưu đều để trống. Không đồng bộ hoặc export environment
sau khi điền nếu chưa xóa credentials và tokens.

Thứ tự chạy thủ công:

1. Folder **01 Auth**: lấy token Alice, Bob, data-operator. Scripts lưu token vào
   environment để những request sau dùng lại; không in token ra console.
2. Folder **02 Portfolio**: tạo danh mục → GET để lấy `ETag` → PATCH với
   `If-Match` → gửi MVO → retry cùng key → đổi nội dung cùng key (409).
   Request đầu tiên lưu `portfolio_id`, `job_id`, `status_url`; key được giữ lại
   để thử idempotency. Muốn tạo yêu cầu mới, xóa `recommendation_key` ở environment.
3. Gửi **Poll recommendation job** lại đến khi `status=SUCCEEDED`, rồi đọc kết
   quả/lịch sử. `QUEUED` chưa có kết quả; `FAILED` cần đọc `error`, không đọc
   recommendation ID rỗng. Collection Runner không tự poll lặp hoặc chờ worker.
4. Folder **03 Ownership**: đọc các ID của Alice bằng token Bob, kỳ vọng 404.
5. Folder **04 Market**: ingest registered demo CSV → poll ingestion đến
   `SUCCEEDED` → đọc assets/prices → tạo snapshot → đọc manifest/observations.
   Script điền ngày UTC hiện tại nếu `market_start_date`, `market_end_date`,
   `market_as_of_date` còn trống; sửa các ngày theo dữ liệu thật trong
   demo/provider khi cần. `market_asset_id` mặc định là `DEMO_STOCK`, tách biệt
   với tài sản `AAA` của numerical demo bundle.
6. Folder **05 Quant** là tùy chọn: lấy service token rồi đọc ready
   inputs của `DEMO`/`MVO`. Human token không thay service token.

Các request có kiểm tra HTTP status, tự lưu ID/ETag và kiểm tra result weights/
provenance. Không chạy cả collection một lượt để suy ra async job đã hoàn tất;
poll trước khi chạy request cần `recommendation_id` hoặc snapshot đã tạo.

## 5. Portfolio: request mẫu và điều kiện kỳ vọng

Tạo danh mục `POST /api/v1/portfolios` (201):

```json
{
  "name": "Danh mục API demo",
  "capital_vnd": "1000000",
  "universe_id": "DEMO",
  "risk_aversion": 1.5,
  "max_position_weight": 0.5
}
```

`GET /api/v1/portfolios/{id}` trả header `ETag`, ví dụ `"1"`. PATCH với
`If-Match: "1"` và `{"name":"Danh mục đã cập nhật"}` tăng version; thiếu
`If-Match` trả 428, version cũ trả 412. Lấy lại ETag trước khi sửa tiếp.

Gửi `POST /api/v1/portfolios/{id}/recommendations` với header
`Idempotency-Key: <một UUID mới>` và `{"strategy":"MVO"}`. HTTP 202 trả
`job_id`, `status_url`. Retry cùng owner/portfolio/key/body trả cùng job; cùng key
với `{"strategy":"EW"}` trả 409. Poll `GET {status_url}` trên Portfolio API
cho tới `SUCCEEDED`, sau đó gọi `GET /api/v1/recommendations/{recommendation_id}`.
Kết quả có weights, strategy, core version, input/bundle hashes, data snapshot
ID và provenance; lịch sử nằm ở `GET /api/v1/portfolios/{id}/recommendations`.

Demo numerical bundle là dữ liệu tổng hợp, hỗ trợ EW/MVO và hết hạn sau một ngày.
BL_ML cần model bundle đã phê duyệt và ML views hợp lệ; demo không có model này,
nên request BL_ML trả 503. Làm mới bằng `up --refresh-demo`, không sửa bundle cũ.

## 6. Market Data: ingestion và immutable snapshot

Gửi token `data-operator`, `Idempotency-Key` và JSON tới
`POST /api/v1/market/ingestions` (202):

```json
{"dataset_id": "DEMO_STOCK"}
```

Dataset ID phải đã đăng ký trong server provider registry. Endpoint không nhận
đường dẫn hoặc URL bất kỳ do client đưa vào. Chờ
`GET /api/v1/jobs/market/{job_id}` thành `SUCCEEDED`; đọc `error` nếu `FAILED`.
Gửi lại key/body cũ trả cùng job; cùng key với body khác trả 409.
`--refresh-demo` chỉ cập nhật CSV/catalog demo, chưa tự ingest giá mới. Xóa
`ingestion_key` trong Postman trước lần import mới sau refresh; nếu giữ key cũ,
API trả lại job cũ đúng theo idempotency.

Cũng có thể gửi normalized observations thay `dataset_id`; hai nguồn không
được xuất hiện cùng một request. Ví dụ cho ngày đã có dữ liệu:

```json
{
  "observations": [{
    "asset_id": "AAA",
    "kind": "stock",
    "observation_date": "2026-10-09",
    "price": "25000",
    "source_unit": "VND/share",
    "provider": "postman-local",
    "price_type": "close"
  }]
}
```

`published_at` tùy chọn phải có timezone và không ở tương lai. Stock/fund/gold
cho phép đúng đơn vị chuẩn hoặc prefix `thousand_` để chuyển đổi rõ ràng;
`price_type` có thể là `close`, `nav`, `bid`, `ask`, `midpoint`. Job response có
`status`, `inserted_count`, `error`. Dùng key mới khi gửi nội dung revision mới.

CSV demo chứa asset `DEMO_STOCK`, provider `synthetic-local`, cho hôm qua và
hôm nay theo UTC lúc bootstrap/refresh. Ngày chính xác nằm trong CSV/catalog
ignored `infra/local/.generated/datasets/`. Với normalized request tùy chọn
trong Postman, giữ cùng provider/price convention để tạo revision cho asset
demo; trộn nhiều provider/convention cho cùng asset sẽ khiến snapshot bị từ chối.

`GET /api/v1/market/assets` trả asset master;
`GET /api/v1/market/prices?asset_id=DEMO_STOCK&start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`
trả revisions giá theo thời gian. Giá normalized lưu stock `VND/share`, fund
`VND/unit`, gold `VND/tael`. Nguồn CSV phải khai báo unit; không suy đoán đơn vị.

Sau khi dữ liệu đã có, gửi `POST /api/v1/market/snapshots` (201) với ngày phù hợp
thực tế; đây là ví dụ cấu trúc, không bảo đảm demo hiện tại có các ngày dưới đây:

```json
{
  "asset_ids": ["DEMO_STOCK"],
  "start_date": "2026-10-09",
  "end_date": "2026-10-09",
  "as_of_date": "2026-10-09",
  "max_age_days": 7
}
```

Snapshot chốt thứ tự assets, revision IDs, date range, publication/availability
times, source metadata và `content_hash`. Thiếu dữ liệu hoặc dữ liệu quá cũ thì
trả 409 và không tạo snapshot READY. Đọc
`GET /api/v1/market/snapshots/{id}` và `/api/v1/market/snapshots/{id}/observations`
bằng token `market:read`. Ingest revision mới không sửa snapshot đã lưu; cùng
nội dung snapshot tạo cùng content hash.

CSV stock/fund/gold tiếp tục là một nguồn nhập tin cậy. P1 bổ sung adapter KBS
stock trực tiếp, refresh jobs/snapshots và publication worker xây numerical
bundle từ snapshot; investor recommendation dùng bundle đã publish với pins.
Không nhận arbitrary provider URL/path từ client.

## 6b. P1: refresh, training/review và đánh giá lại rủi ro

Chạy lại setup `up` sau cập nhật source để bổ sung `ml_db`, các role DB riêng,
`ml-migrate`, `ml-api`, `ml-worker`, `market-refresh` và scopes/clients còn thiếu.
Giữ generated credentials và volumes; đăng nhập lại để nhận claims mới. API/worker
runtime dùng credential của owner; migrator mới có quyền schema. Refresh worker
chỉ ghi thư mục refresh, ML worker chỉ ghi model artifacts; API/readers và Quant
optimizer giữ mount read-only. `quant-publication` riêng ghi bundle/catalog. ML
đang dùng lại Quant training/feature helpers theo cách chuyển tiếp, không đổi
thuật toán portfolio-core hay risk-policy mapping.

Data operator mở `/#market-refresh`, xem lại rồi tạo schedule với
`name`, `asset_ids`, `initial_start_date`, `interval_minutes`, `overlap_days`,
`max_age_days`, `enabled`. API:

- `GET/POST /api/v1/market/refresh-schedules`; `GET/PATCH /{id}`.
- `GET/POST /api/v1/market/refresh-jobs`; `GET /{id}`. POST body chỉ có
  `{"schedule_id":"SCHEDULE_UUID"}`.

Mutations cần Idempotency-Key; PATCH cần If-Match lấy từ ETag hiện tại. Schedule
mới enabled được đặt due ngay; bật lại schedule hiện có đặt lần sau theo interval.
Manual run và timer dùng chung durable worker, lease/retry và schedule-version pin.
Tắt schedule thử nghiệm khi hoàn tất. Không sửa DB hoặc đồng hồ để ép lịch chạy.

Nguồn `kbs-direct-v1` fetch bounded stock symbols từ endpoint cố định, cutoff là
ngày đã hoàn tất trước ngày hiện tại ở Asia/Ho_Chi_Minh. Mỗi run đối chiếu **toàn
bộ lịch sử adjusted trong khoảng cấu hình**, vì corporate actions có thể sửa giá
cũ; chỉ lưu thêm revision mới/thay đổi. `overlap_days` không biến network fetch
thành incremental-only. Raw JSON, normalized CSV và manifest được ghim hash;
quality phải PASS cho toàn bộ tài sản mới tạo snapshot. Giá là provider-adjusted
close, chưa phải certified total return hay historical adjustment vintages.
VNINDEX cung cấp calendar quan sát (`calendar_verified=false`), không phải lịch
sàn đã chứng nhận; known-at theo ingestion không chứng minh historical PIT.

Ở `/#model-training`, chọn snapshot UUID/hash và cutoff **trước ngày quan sát
serving mới nhất**, rồi xem lại và gửi. `POST /api/v1/ml/training-jobs` nhận
`snapshot_id`, `snapshot_hash`, `training_cutoff`, `lookback`, `min_returns`,
`max_age_days` và Idempotency-Key; HTTP chỉ enqueue, không train trong handler.
GET list/detail jobs trả trạng thái và model UUID khi thành công. Model bắt đầu
CANDIDATE. Reviewer độc lập mở `/#model-review?model=UUID`:

```text
POST /api/v1/ml/models/{id}/reviews
If-Match: "CURRENT_MODEL_VERSION"
Idempotency-Key: REVIEW_INTENT_UUID

{"decision":"APPROVED","reason":"Đã xem provenance và validation"}
```

`REJECTED` cũng cần reason; review không tự động và không được ghi đè quyết định
đã lưu. Chờ `artifact_ready=true` sau APPROVED. Data operator chọn model UUID khi
`POST /api/v1/market/publications` cùng snapshot/hash/universe và policy freshness;
field `approved_model_id` được server resolve thành manifest hash pin, không dùng
file/path/URL client cung cấp. API publish chỉ enqueue worker; bỏ model UUID thì
publish EW/MVO. Model không tương thích/hết hạn hoặc nguồn không hợp lệ phải được
xử lý theo status/error, không tăng ngưỡng chỉ để che lỗi.

Investor mở `/#risk-assessment?portfolio=UUID`. POST
`/api/v1/portfolios/{id}/risk-assessments/preview` với body
`{"answers":{"questionnaire_version":"risk-v1","horizon_months":120,"liquidity_need":"low","loss_tolerance":"high","experience":"experienced"}}`
trả before/after profile/constraints và portfolio version, không lưu assessment.
POST cùng body tới `/risk-assessments`, thêm quoted If-Match từ version đã xem
lại và Idempotency-Key, mới xác nhận revision UUID bất biến. Retry cùng key/body
trả receipt cũ; khác body trả 409; phiên bản stale trả 412. GET `/risk-assessments`
là array phân trang với count/limit/offset headers và `is_active`.

Confirmation tăng version danh mục; accept pending proposal cũ trả 409 khi dùng
version hiện tại. Tạo proposal mới để pin profile UUID/policy mới. Accepted target
cũ và queued input hashes giữ nguyên; sửa manual constraints làm profile cũ hết
active, không sửa lịch sử. Portfolio legacy không được bịa lịch sử assessment.

Gate browser thật chạy từ `apps/web`:

```sh
E2E_DISPOSABLE_STACK=1 npm run test:browser:p1
# Sau actual API/worker/web restart và health checks:
E2E_DISPOSABLE_STACK=1 npm run test:browser:p1:persistence
```

Gate nguồn KBS này độc lập DEMO và không dùng HTTP mocks/SQL fake. Nó bao gồm
manual + actual timer refresh, train/reviewer/publish, risk conflicts và BL_ML
accepted target. Receipt không token: `.generated/p1-browser-receipt.json` bên
trong `infra/local`; safe reporter ghi `output/playwright/sanitized/p1-lifecycle.json`
và `p1-persistence.json`, không lưu credentials/auth URLs/raw call logs.
Xem [restart commands](../../apps/web/tests/browser/README.md#p1-real-provider-model-and-risk-gate).
Ngày 27/10/2026, lifecycle P1 nguồn thật và đối chiếu chính receipt sau restart
đều đạt; P0/Market lifecycle và persistence cũng đạt. Xem bằng chứng/phạm vi
ở [Implementation status](IMPLEMENTATION_STATUS.md).

## 7. Kiểm chứng persistence và chẩn đoán

Khi stack healthy và test client đã bật:

```sh
python3 scripts/setup_software.py verify --live
docker compose --env-file infra/local/.generated/.env -f infra/local/compose.yaml restart portfolio-api portfolio-consume portfolio-dispatch quant-api quant-consume quant-dispatch market-api market-consume market-dispatch
docker compose --env-file infra/local/.generated/.env -f infra/local/compose.yaml up -d --wait
.venv-software/bin/python scripts/smoke_software.py --verify-receipt
```

Smoke tạo dữ liệu local và lưu receipt không chứa token trong `.generated`.
Lệnh `--verify-receipt` đọc lại kết quả đã lưu sau restart; nó cần smoke chạy
thành công trước đó. Có thể giữ các ID đã lưu trong Postman rồi đọc lại portfolio,
job, recommendation và snapshot sau restart để kiểm tra thủ công.

| Hiện tượng | Bước kiểm tra |
| --- | --- |
| Docker không đáp ứng / build I/O error | Mở Docker Desktop; kiểm tra dung lượng rồi chạy `check` lại |
| Token endpoint lỗi | Kiểm tra secrets/account local và test client; chạy lại `up --enable-test-client` để upgrade realm cũ |
| 401 | Dùng access token mới, issuer/audience đúng service |
| 403 Market write | Dùng `data-operator` với scope `market:write` |
| 404 dữ liệu riêng | Kiểm tra đúng owner và ID; cross-owner 404 là hành vi mong đợi |
| 412/428 PATCH | GET lại danh mục và copy nguyên ETag vào `If-Match` |
| 409 idempotency | Dùng lại đúng body để retry, hoặc key mới cho yêu cầu mới |
| Job QUEUED/FAILED | Đọc status/error; kiểm tra health của broker, dispatcher, consumer |
| JWT thiếu `sub`, API 401 dù login được | Chạy setup/upgrade để gắn basic/Subject mapper, rồi đăng nhập/lấy token mới |
| Identity migration `java.io.EOFException` sau sự cố đầy đĩa | Image sạch đã được kiểm tra; tạo lại riêng `identity-migrate` container, giữ volumes, rồi chạy setup tiếp |
| Build đứng ở metadata Node/credential helper | Dùng workaround cấu hình Docker tạm dưới đây; không đổi global Docker login config |
| MVO 503 / bundle hết hạn | Chạy `up --refresh-demo`; không dùng demo để suy ra chất lượng mô hình |
| Snapshot thiếu/quá cũ | Ingest dữ liệu và chọn date range/as-of phù hợp, không tăng ngưỡng để che lỗi dữ liệu |

Xem trạng thái container bằng `docker compose --env-file
infra/local/.generated/.env -f infra/local/compose.yaml ps`. Dùng `config --quiet`
để xác thực cấu hình; `config` không có `--quiet` mở rộng secrets. Nếu chia sẻ
log chẩn đoán, bỏ credentials/tokens. Dừng mà giữ dữ liệu:

```sh
docker compose --env-file infra/local/.generated/.env -f infra/local/compose.yaml down
```

Không thêm `--volumes` khi muốn giữ persistence. Staging nằm trong
`infra/staging/` là deployment template với external dependencies/HTTPS/secrets;
chưa được triển khai bởi hướng dẫn này và không dùng tài khoản/demo local.

Nếu Docker credential helper mắc khi build các **public base images của repo**,
workaround đã kiểm chứng chạy từ repo root là:

```sh
python3 - <<'PY'
import json, os, subprocess, tempfile
from pathlib import Path
endpoint = subprocess.check_output(
    ['docker', 'context', 'inspect', 'desktop-linux', '--format', '{{.Endpoints.docker.Host}}'],
    text=True,
).strip()
with tempfile.TemporaryDirectory(prefix='portfolio-public-build-') as directory:
    Path(directory, 'config.json').write_text(json.dumps({
        'auths': {},
        'cliPluginsExtraDirs': ['/Applications/Docker.app/Contents/Resources/cli-plugins'],
    }))
    environment = os.environ.copy()
    environment['DOCKER_CONFIG'] = directory
    environment['DOCKER_HOST'] = endpoint
    subprocess.run([
        'docker', 'compose', '--env-file', 'infra/local/.generated/.env',
        '-f', 'infra/local/compose.yaml', 'build',
    ], env=environment, check=True)
PY
python3 scripts/setup_software.py up --enable-test-client --skip-install --skip-build
```

Workaround này dành cho Docker Desktop macOS/context `desktop-linux` đang dùng;
nó không đọc/copy credentials registry và không thay cấu hình Docker toàn cục.
Với private base images, dùng cơ chế đăng nhập registry của môi trường tương ứng.
`--skip-build` chỉ dùng sau khi images hiện hành đã build thành công.

Kiến trúc và trạng thái hiện thực: [software README](README.md),
[local infrastructure](../../infra/local/README.md),
[implementation status](IMPLEMENTATION_STATUS.md).


## Chat MVP API và worker

Chat sở hữu `chat_db` và có `chat-migrate`, `chat-api` (Swagger port 8005),
`chat-worker`. Queue SQL có lease/fencing giống ML/publication; allocation vẫn do
Portfolio outbox → RabbitMQ → Quant xử lý. Chat lưu dependency intent trước HTTP
và reconcile bằng stable key, không phụ thuộc browser connection hoặc broker hint.

- `POST/GET /api/v1/conversations`; `GET /api/v1/conversations/{id}`.
- `GET/POST /api/v1/conversations/{id}/messages`: GET có limit/offset và pagination
  headers. POST cần Idempotency-Key bằng client_message_id; trả 202 message/job,
  status_url/events_url. Cùng key/nội dung trả cùng receipt; body khác trả 409.
- `GET /api/v1/jobs/chat/{id}`, `GET .../{id}/events` nhận Last-Event-ID;
  `POST .../{id}/cancel`; `POST .../{id}/resume` cần confirmed=true và UUID
  authorization_id mới từ thao tác người dùng, giữ nguyên job/dependency.
- `GET /api/v1/recommendations/{id}/explanation` kiểm tra lại quyền qua Portfolio.

Confirmation tham chiếu message_id/facts_hash của card server lưu, ghim portfolio,
risk/policy, constraints và strategy. Text “đồng ý” không thay structured
confirmation. Portfolio kiểm tra lại pins dưới lock; retry đã commit trả receipt
cũ trước khi đánh giá version hiện tại. Accept/trade/promote không có trong tools.

Portfolio cấp grant qua `POST /internal/v1/delegation-grants` nhận user bearer
và X-Service-Authorization của chat-service. Delayed call tới
`/internal/v1/chat-tools/{tool}` nhận service bearer và các headers
X-Delegation-Grant/X-Chat-Job/X-Chat-Conversation. Grant mặc định 5 phút, binding
subject/actor/conversation/job/portfolio/tools; mỗi call kiểm tra account/role
hiện hành qua read-only Keycloak identity và ownership tại Portfolio.
Grant chỉ cấp request_allocation cho lượt đã xác nhận. Grant replay không gia hạn;
resume phải được người dùng cấp lại quyền. `/api/v1/chat/delegations/revoke` thu
hồi grants của user; BFF gọi khi logout. Grant/token không vào bus, SSE hoặc logs.

Quotas: 5 jobs pending và 100 turns/user/giờ, serialize theo owner trên PostgreSQL;
job deadline 180 giây, tối đa 5 retry lỗi, lease 30 giây. Mỗi worker step tối đa
6 tools. SSE events giữ 7 ngày; reset_required yêu cầu refetch message/job/resource.
SSE heartbeat 15 giây, stream tối đa 85 giây; BFF tối đa 80 giây và đóng khi session
bị thu hồi/hết hạn. Poll SQL/JWKS chạy ngoài event loop và có wait cap 5 giây.

Provider mặc định chưa cấu hình: template deterministic từ canonical facts.
Có thể cấu hình riêng worker bằng CHAT_PROVIDER_URL/CHAT_PROVIDER_KEY/
CHAT_PROVIDER_MODEL qua secret environment; không đưa vào browser/BFF public env.
Adapter protocol `fact-plan-v1` nhận facts tối thiểu, trả sections/facts_hash và
usage theo schema; không nhận prose hoặc tool instructions tùy ý. Giới hạn
usage schema tối đa 1600 input + 448 output tokens, request 6400 bytes, response
8192 bytes, total deadline 5 giây. Một lượt gọi provider/job được reserve bền vững trước I/O; crash sau đó
fallback template, không tiêu thêm budget tự động. Đây là adapter protocol, chưa
phải adapter SDK riêng cho một provider thương mại. Lỗi provider không đổi weights,
constraints hoặc strategy. RAG/Knowledge đầy đủ còn ngoài phạm vi MVP.

Offline và live gates (môi trường local disposable đã chuẩn bị):

```sh
CHAT_POSTGRES_TEST=1 .venv-software/bin/python -m pytest tests/software packages/portfolio-core/tests -q
npm --prefix apps/web test
npm --prefix apps/web run typecheck
.venv-software/bin/python scripts/export_software_contracts.py
.venv-software/bin/python infra/local/verify_boundaries.py
.venv-software/bin/python scripts/smoke_chat.py
# Sau restart Chat/Portfolio/Quant thực, đọc cùng receipt:
.venv-software/bin/python scripts/smoke_chat.py --verify-receipt
# Gate quyền riêng: quan sát expiry thực 5 phút, disable/restore Bob trong finally:
E2E_DISPOSABLE_STACK=1 .venv-software/bin/python scripts/smoke_chat_authorization.py
```

`smoke_chat.py` yêu cầu universe real-price MVO READY, kiểm tra trực tiếp Market
snapshot/observations hashes và canonical Portfolio facts; không mock HTTP hoặc
tạo giả SQL result. `--provider-outage` chỉ kiểm chứng khi worker thực được cấu
hình trỏ đến provider đang unavailable. Không đổi dữ liệu thành DEMO để vượt
freshness. Receipt không token ở `infra/local/.generated/chat-api-receipt.json`.
Các test PostgreSQL concurrency dùng schema tạm riêng và injected tools: đây là
storage unit tests, được báo riêng với gate integration thật. API gate không
accept target; chấp nhận phải đi qua UI rõ ràng trong browser gate.

## OpenAI dialogue — phương án B (05/11/2026)

LLM hỗ trợ nhận diện intent, hiểu câu trả lời trong ngữ cảnh ngắn và chọn các
phần giải thích. Backend tiếp tục lấy canonical facts, hỏi thông tin thiếu,
tạo confirmation card và cấp quyền tools. Text đồng ý không thay structured
confirmation; không có accept/trade/promote hoặc sửa weights qua LLM.

Adapter gọi trực tiếp OpenAI Responses bằng httpx đã pin, không thêm agent
framework. Model ban đầu `gpt-6-luna`, reasoning `none`, Structured Outputs strict,
`store=false`, không hosted tools/previous_response_id. Model hiện chỉ công bố
alias này; lưu model trả về và prompt/schema versions, chưa có dated snapshot để
pin. Tham chiếu [model](https://developers.openai.com/api/docs/models/gpt-6-luna)
và [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).

Mỗi conversation có `llm_consent=false` mặc định. Investor chủ động bật checkbox
“Cho phép OpenAI hỗ trợ hội thoại này”; thay đổi qua
`POST /api/v1/conversations/{id}/preferences` với `{ "llm_consent": true/false }`,
BFF kiểm tra session/CSRF và backend kiểm tra scope/owner. Thu hồi consent ngăn
các lời gọi mới, không thu hồi dữ liệu đã gửi trong một request đang chạy.
Chỉ gửi nội dung hiện tại, tối đa 4 messages trước (mỗi nội dung 400 ký tự),
trạng thái card tối thiểu và facts cần thiết; loại UUID/email/bearer/API keys/
chuỗi số định danh phổ biến. Đây không phải cam kết loại mọi PII từ văn bản tự do.
Không gửi owner/grant/service tokens hoặc provider key trong context/logs/SSE.
`store=false` không đồng nghĩa Zero Data Retention của provider.

### Bật local

Tạo project API key trong API organization đã nhận subscription credits. Lưu
riêng trong `infra/local/.generated/chat-openai.env` (Git ignored), ví dụ từ
`infra/local/chat-openai.env.example`, với `OPENAI_API_KEY=...`, rồi `chmod 600`
file đó. Không đưa giá trị vào chat, command arguments, Git hoặc screenshot.
Không cần bật Auto Recharge. Overlay chỉ đưa key vào `chat-worker`, không API/BFF.

```sh
docker compose --env-file infra/local/.generated/.env -f infra/local/compose.yaml -f infra/local/compose.tracing.yaml build chat-migrate web
docker compose --env-file infra/local/.generated/.env -f infra/local/compose.yaml -f infra/local/compose.tracing.yaml run --rm --no-deps chat-migrate
docker compose --env-file infra/local/.generated/.env -f infra/local/compose.yaml -f infra/local/compose.tracing.yaml -f infra/local/compose.chat-llm.yaml up -d --no-deps chat-api chat-worker web
```

Giữ overlay tracing khi stack đang dùng tracing. Lệnh `setup_software.py up` chưa
tự thêm overlay LLM; nếu dùng lệnh đó để tạo lại worker, áp dụng lại lệnh cuối.
Để tắt provider và quay về xử lý deterministic, chạy cùng lệnh cuối nhưng bỏ
`-f infra/local/compose.chat-llm.yaml`. Dữ liệu/consent/history vẫn được giữ nguyên.

### Credits và kiểm thử

Mặc định 20 invocation/ngày UTC cho toàn Chat, tối đa 100 qua cấu hình deployment
`CHAT_LLM_DAILY_CALL_LIMIT`; 0 tắt các lượt gọi. Một job tối đa 1 interpretation
và 1 explanation. Intent/strategy được chọn rõ ở UI và structured confirmation
bỏ qua interpretation. Model không được tự chọn strategy thiếu bằng chứng từ
người dùng; backend hỏi lại. Explicit UI strategy ưu tiên hơn model.

`provider_invocation` reserve bền vững trước I/O, serialize quota bằng PostgreSQL
advisory lock; crash/timeout không gọi trả phí lần hai. Validated plan được lưu
để reuse trên cùng job. Reservation chưa có kết quả vẫn chiếm quota. Mỗi request
tối đa 12000 bytes envelope, 384 output tokens, wall timeout 8 giây, không retry
HTTP trả phí tự động. Khi lỗi/schema không hợp lệ/đạt quota, dùng rule/template.
Giới hạn lời gọi là rào chi phí; `estimated_cost_usd` chỉ là ước tính theo bảng
giá lúc triển khai, không thay hóa đơn OpenAI. `GET /api/v1/jobs/chat/{id}` có
`provider_usage` theo từng purpose từ ledger, bao gồm lượt hiểu intent của job
giải thích tiếp; không cộng usage chỉ từ message vì có thể thiếu lượt đó.

```sh
# Offline (không load key file, không gọi provider thật):
CHAT_POSTGRES_TEST=1 .venv-software/bin/python -m pytest tests/software packages/portfolio-core/tests -q
npm --prefix apps/web test
npm --prefix apps/web run typecheck
# Opt-in: 5 provider calls cho một lifecycle mới, không tự retry:
E2E_DISPOSABLE_STACK=1 npm --prefix apps/web run test:browser:chat:llm
# Sau restart API/worker/web thật: replay/refetch, không thêm provider calls:
E2E_DISPOSABLE_STACK=1 npm --prefix apps/web run test:browser:chat:llm:persistence
```

Live gate cần real-price MVO universe READY và receipt
`infra/local/.generated/chat-real-input-receipt.json` từ Market refresh/publication
thật. Receipt Chat LLM riêng là `.generated/chat-llm-browser-receipt.json`; báo
cáo/ảnh nằm trong `output/playwright/sanitized/chat-llm-*`, ngoài Git. Xem
[browser guide](../../apps/web/tests/browser/README.md#chat-llm-paid-gate).
