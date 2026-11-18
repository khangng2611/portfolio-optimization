# Setup và kiểm thử API phần mềm

Để xem timeline của request qua BFF, RabbitMQ và workers, xem
[hướng dẫn OpenTelemetry + Jaeger](TRACING.md). Có thể bật cùng quá trình setup:
`python3 scripts/setup_software.py up --tracing`.

Đây là điểm vào cho phần ứng dụng trong `apps/`, `services/`, `packages/` và
`infra/`. Các lệnh dưới đây chạy từ repo root. Môi trường `.venv-software` độc
lập với môi trường nghiên cứu Phase 1; không cài `requirements.txt` ở root để
chạy các service.

## 1. Chuẩn bị và chạy bằng một lệnh

Máy cần Python **3.12**, Node.js **>=22.12** (khuyến nghị Node 22 LTS), npm và
Docker Desktop với Compose v2. Mở Docker Desktop, kiểm tra còn đủ dung lượng
trống cho images/build/volumes. Chỉ chạy stack local trên máy phát triển.

```sh
python3 scripts/setup_software.py up
```

Script kiểm tra công cụ, tạo hoặc dùng lại `.venv-software`, cài các package
software theo constraints, dùng `npm ci` khi cần, bootstrap secrets/demo,
kiểm tra Compose, build images và chạy stack. Nó khởi động PostgreSQL,
RabbitMQ và Redis trước, sau đó bổ sung DB/broker grants và chạy Auth
migration, seed cùng các service. Project `portfolio-auth-demo` dùng volume
riêng. Nếu stack `portfolio-software` cũ còn giữ cổng localhost, dừng container
cũ và giữ lại volume của nó.

Các chế độ hỗ trợ:

| Lệnh | Mục đích |
| --- | --- |
| `python3 scripts/setup_software.py --help` | Xem tùy chọn |
| `python3 scripts/setup_software.py check` | Chỉ đọc: công cụ, Docker daemon, môi trường và Compose config |
| `python3 scripts/setup_software.py prepare` | Cài dependency và sinh cấu hình; chưa khởi động container |
| `python3 scripts/setup_software.py up --skip-install --skip-build` | Dùng môi trường/images hiện có đã hợp lệ |
| `python3 scripts/setup_software.py up --refresh-demo` | Làm mới demo bất biến rồi chạy stack; giữ secrets và dữ liệu cũ |
| `python3 scripts/setup_software.py verify` | Python/API/core tests, Ruff, export contracts, web tests/typecheck/build |
| `python3 scripts/setup_software.py verify --live` | Thêm DB/broker/auth boundary và real-JWT asynchronous smoke trên stack healthy |

`--python /đường/dẫn/python3.12` chọn interpreter khi không có lệnh
`python3.12` trong PATH. `--skip-build` chỉ dùng khi images đã phản ánh source
hiện tại. `check` không sửa file hoặc khởi động container; lỗi Docker có nghĩa
chưa kiểm chứng runtime, không đồng nghĩa API tests thất bại.

Mở [web](http://localhost:3000), tạo tài khoản ở `/register` rồi đăng nhập ở `/login`.
Tài khoản mới có role `investor`. Tài khoản demo `alice`, `bob`, `data-operator` và
`model-reviewer` được seed từ `infra/local/.generated/accounts.json`. Giữ mật khẩu,
signing key và `.env` trong thư mục ignored, cùng volume của demo.

## 2. Địa chỉ và quyền truy cập

| Thành phần | Local URL |
| --- | --- |
| Web/BFF | [localhost:3000](http://localhost:3000) |
| Portfolio Swagger | [localhost:8001/docs](http://localhost:8001/docs) |
| Quant Swagger | [localhost:8002/docs](http://localhost:8002/docs) |
| Market Data Swagger | [localhost:8003/docs](http://localhost:8003/docs) |
| ML Platform Swagger | [localhost:8004/docs](http://localhost:8004/docs) |
| OpenAPI JSON | `/openapi.json` trên mỗi API port |
| Health | `/health/live`, `/health/ready` trên mỗi API port; không cần JWT |

JWT phải có chữ ký hợp lệ, issuer `http://auth-api:8000`, audience đúng service,
`sub` ổn định, thời hạn, role và scope phù hợp. Auth chỉ lắng nghe trong Compose.

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

Smoke test lấy JWT qua helper dùng Compose exec. Để thử Bearer API thủ công
trên macOS, chép JWT ngắn hạn vào clipboard. Đổi `alice` thành `bob` hoặc
`data-operator` để kiểm tra quyền theo role.

```sh
PYTHONPATH=scripts python3 -c 'from local_auth import login; print(login("alice"), end="")' | pbcopy
PYTHONPATH=scripts python3 -c 'from local_auth import service_token; print(service_token("portfolio-service"), end="")' | pbcopy
```

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

Chọn environment **Portfolio software — local**. Điền `access_token` (Alice),
`bob_token`, `market_token` (data-operator) và `quant_token` (tùy chọn) từ mục 3
vào giá trị local. Giữ token khỏi log và environment export.

Thứ tự chạy thủ công:

1. Folder **00 Health** để kiểm tra readiness.
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
6. Folder **05 Quant** là tùy chọn: dùng service token để đọc ready
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
| Token endpoint lỗi | Kiểm tra `auth-api`, `auth-migrate` và account seed trong Compose |
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
python3 scripts/setup_software.py up --skip-install --skip-build
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
hiện hành qua endpoint Auth chỉ đọc trạng thái tài khoản và ownership tại Portfolio.
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

### Chính sách cấu hình dev — 18/11/2026

Checkbox OpenAI và popover dữ liệu đã được bỏ khỏi Chat. Dev bật/tắt qua
CHAT_LLM_ENABLED, embedding truy vấn qua CHAT_QUERY_EMBEDDINGS_ENABLED (mặc định 0).
API preferences trả 403 và các trường consent cũ chỉ giữ để đọc receipt lịch sử.
Xem phần Developer-managed provider policy trong KNOWLEDGE_RAG.md để có lệnh
Compose đúng với demo 127.0.0.1:3100. Các bước consent bên dưới là mô tả lịch sử.

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

## Knowledge/RAG — 07/11/2026

Use the [Knowledge runbook](KNOWLEDGE_RAG.md) for port 8006, separate
PostgreSQL/pgvector roles/migrations, corpus CLI, lexical receipts, consent v2 and
frozen Vietnamese evaluation. Existing Chat OpenAI configuration above does not
authorize new Knowledge ingestion/query/selection spending. New provider budget
is zero until a specific user grant; paid dry-run is offline. Do not enable
Auto Recharge. Release eval and real-provider acceptance remain separate gates.


### Refresh dữ liệu và kiểm tra lỗi hết hạn — 18/11/2026

Chạy operator refresh selected-assets từ repo root, tạo snapshot mới và giữ bản
cũ. Snapshot phải được phát hành qua publication API hoặc publication queue
trước khi dùng cho yêu cầu mới. Không sửa valid_until của artifact cũ.

```sh
docker compose -p portfolio-auth-demo --env-file infra/local/.generated/.env -f infra/local/compose.yaml exec -T market-refresh python -m market_service.selected_refresh --directory /datasets/refresh/full-phase1 --seed /datasets/refresh/full-phase1/seed.json
.venv-software/bin/python scripts/smoke_chat_input_refresh.py --phase fresh --portfolio-id TEST_PORTFOLIO_UUID
.venv-software/bin/python scripts/smoke_chat_input_refresh.py --verify-receipt
```

Fresh phase chỉ chạy khi readiness MVO là READY. Khi nguồn thật chưa đủ mới,
phase stale kiểm nhánh VFF_STALE. Chỉ dùng danh mục kiểm thử do alice sở hữu.
Script tạo hội thoại và đề xuất mới nếu đủ điều kiện, dừng ở kết quả, không accept.
Receipt mặc định output/chat-input-refresh/chat-flow-receipt.json. Verify dùng
đúng receipt sau restart, không gửi luồng mới. Input đã phát hành còn hạn vẫn có
thể bị VFF_STALE vì buffer 5 phiên; refresh không tự bỏ các ràng buộc đó.

### NAV live v2 — 18/11/2026

User đã duyệt tách policy live. Snapshot selected mới mặc định
`user-selection-live-nav-v2`: VFF quality PASS, identity và source hash đã kiểm
tra được dùng sau verification/ingestion thật, không chờ thêm 5 phiên. NAV vẫn
không vượt phiên hoàn tất mới nhất; tuổi tối đa 7 ngày lịch từ ngày định giá.
Schema 2 và selected v1 giữ nguyên buffer và kết quả cũ. Cần snapshot/bundle mới;
không chỉnh manifest/hash/TTL của artifact đã phát hành.

Rebuild `market-migrate portfolio-migrate quant-migrate` để cập nhật ba image.
Rollout Quant/Portfolio readers và workers trước khi phát hành input mới. Khi
recreate local API, giữ override đang bật danh mục tùy chọn:

```sh
docker compose -p portfolio-auth-demo --env-file infra/local/.generated/.env \
  -f infra/local/compose.yaml \
  -f infra/local/.generated/user-selection/compose.web3100.yaml \
  up -d --no-deps --wait --wait-timeout 120 \
  market-api market-refresh market-consume market-dispatch \
  quant-api quant-publication quant-consume quant-dispatch \
  portfolio-api portfolio-consume portfolio-dispatch
```

Với JWT operator, tạo snapshot qua `POST :8003/api/v1/market/selected-snapshots`
body `{}` (xác minh lại nguồn đã lưu, không cần crawl lại nếu nguồn còn mới).
Sau đó `POST :8002/api/v1/market/publications` với Idempotency-Key mới, body
`{"snapshot_id":"<id>","snapshot_hash":"<content_hash>","universe_id":"VN_USER_SELECTION","max_age_days":7}`.
Đợi publication SUCCEEDED và kiểm readiness MVO READY, provenance
`data_policy_id=user-selection-live-nav-v2`, VFF eligible date/age đúng nguồn.
Model là tùy chọn cho EW/MVO; không giả định BL_ML READY nếu chưa ghim model.

```sh
.venv-software/bin/python -m pytest tests/software packages/portfolio-core/tests -q
.venv-software/bin/python scripts/smoke_chat_input_refresh.py --phase fresh \
  --portfolio-id TEST_PORTFOLIO_UUID --receipt output/live-nav-policy/chat-flow-receipt.json
# Sau restart API/workers/Web: dùng chính receipt trên, không gửi luồng mới.
.venv-software/bin/python scripts/smoke_chat_input_refresh.py --verify-receipt \
  --receipt output/live-nav-policy/chat-flow-receipt.json
```

Smoke kiểm confirmation, async result, canonical facts/hash, policy và ràng buộc
tỷ trọng; không accept target. Để không gọi provider, tạm recreate chat-worker
với `CHAT_LLM_ENABLED=0` cùng overlay Chat đang dùng, rồi khôi phục cấu hình dev
ban đầu sau test. Đợt kiểm chứng 18/11 dùng cách này, provider_usage rỗng.
Không cần migration hoặc backfill. Thống kê live v2 dùng đường NAV theo ngày
định giá đã biết tại thời điểm tính; không chứng nhận historical publication,
không dùng làm backtest first-seen ở quá khứ hoặc thay thế baseline v1.

### BL_ML: kiểm tra model trước publication

Đọc đủ trang registry `GET :8004/api/v1/ml/models?status=APPROVED&limit=100`
bằng operator JWT; chỉ model `artifact_ready=true`, schema5 asset ensemble,
demo=false được dùng cho selected portfolio. Xác minh native hashes/runtime,
coverage tất cả equity candidate, fit epoch và từng training-prefix hash qua
production `check_equity_model_inputs`. Không coi APPROVED là đủ điều kiện
cho mọi snapshot. Epoch bắt buộc được tính từ calendar đã pin và lịch refit
10 phiên (`selection_ready.fit_index`), không suy từ ngày publication.

Ngày 18/11: decision session17/11 yêu cầu fit_epoch16/11, training price end06/11.
Registry có đúng3 model APPROVED, chỉ một schema5; model đó fit02/11 với cutoff
23/10. Native150member hợp lệ nhưng bị MODEL_EPOCH_MISMATCH và training-prefix
hiện tại khác hash. Hai model schema3/4 không thể thay thế ensemble schema5.
Không sửa epoch/manifest, lùi decision session hoặc nới gate để dùng lại.

Probe publication thật với approved_model_id hiện có bị worker từ chối
FAILED/PUBLICATION_INVALID, không tạo bundle mới. Receipt riêng tại
output/bl-ml-live/publication-receipt.json chỉ chứng minh nhánh từ chối;
không phải receipt đề xuất BL_ML thành công. Sau restart Quant API/publication,
verify chính job/hash đã lưu, rồi xác nhận bundle live cũ và MVO vẫn READY.

Khi có model schema5 đã duyệt và tương thích, publish qua API với snapshot ID/
hash hiện tại, approved_model_id và Idempotency-Key mới. Đợi SUCCEEDED và
readiness BL_ML READY trước khi gửi Chat intent allocation/strategy BL_ML.
Giữ bước xem đầu vào/xác nhận; không truyền fallback_strategy EW. Test cần
chứng minh strategy/requested_strategy vẫn BL_ML, fallback_reason rỗng, model
manifest và snapshot hash khớp native inference diagnostics, canonical facts/
weight constraints đúng. Lưu receipt mới rồi restart và đọc lại đúng IDs/hash.
Script smoke_chat_input_refresh.py hỗ trợ `--strategy BL_ML`, kiểm đúng native
inference/model/snapshot và từ chối fallback; default MVO giữ tương thích receipt
cũ. Không gọi endpoint training/review hoặc provider trả phí khi chưa được user
cho phép. Lượt kiểm tra đầu ngày18/11 bị chặn vì thiếu model; lượt kế tiếp dưới
đây được user duyệt train/review và đã tạo được đề xuất BL_ML thật.

### Huấn luyện và acceptance v5 epoch16/11 — 18/11/2026

API training nhận `training_cutoff`, không nhận fit_epoch tùy ý. Pipeline suy
epoch từ lịch refit10phiên của snapshot; epoch16/11 tương ứng cutoff06/11 trong
calendar hiện tại. Training dùng snapshot v1
6aa157bf-aa7d-4b71-bd24-d3d0717ccd21/hash
b058ab86a698027154cd6e62386c81354f4f52e9194dbaf542171b9952e16537.
Đã đối chiếu nguyên prefix1700giá/30equity, calendar và validity mask khớp chính
xác snapshot live v2 8c2dc496-7d83-4cb2-bc3f-aee78732ee73. ML worker hiện tại
đọc được v1; phần train chỉ dùng equity, không cần thay policy NAV hay rebuild.
Training snapshot và serving snapshot khác ID/hash được ghi trung thực; model
chỉ được dùng khi mọi training-prefix hash khớp target live.

Operator POST `:8004/api/v1/ml/training-jobs`, Idempotency-Key mới, body:

```json
{"model_family":"phase1-asset-ensemble-v5","snapshot_id":"6aa157bf-aa7d-4b71-bd24-d3d0717ccd21","snapshot_hash":"b058ab86a698027154cd6e62386c81354f4f52e9194dbaf542171b9952e16537","training_cutoff":"2026-11-06","max_age_days":7}
```

Đợi job SUCCEEDED và model CANDIDATE. Kiểm schema5/non-demo, epoch/cutoff,
30equity/150native members, native hashes/load, nguồn code, 5seed/best_iteration,
purged chronological split và metrics finite. So từng training-prefix hash với
panel target; không đổi manifest để làm khớp. Lượt này MAE0.0378128444,
RMSE0.0535328016 cho return5phiên; train label end30/06/2025 trước validation
start01/07/2025. `point_in_time_certified=false` giữ nguyên, không chứng nhận
hiệu quả đầu tư hoặc historical publication.

Dùng JWT **model-reviewer** riêng, GET model lấy ETag, rồi POST
`/api/v1/ml/models/<id>/reviews` body decision APPROVED/reason cụ thể,
If-Match theo ETag và Idempotency-Key. Đợi APPROVED **và** artifact_ready=true;
retry cùng review key phải giữ nguyên review ID/version. Quant service resolver
kiểm lại approved native files và toàn bộ30prefix trước publication.

Model được duyệt: 70716105-ef74-4203-bfa6-9657f756e0b6, approved manifest hash
d511678a0626d8a749b4e4dbd36cc58114702212fa9ba171d180403ecd1cca89.
Publish model này với target snapshot live v2 qua publication API như trên.
Không chấp nhận chỉ artifact_ready hoặc chỉ publication SUCCEEDED làm bằng
chứng allocation; cần cả readiness và kết quả thực.

```sh
.venv-software/bin/python scripts/smoke_chat_input_refresh.py --phase fresh \
  --strategy BL_ML --portfolio-id ISOLATED_TEST_PORTFOLIO_UUID \
  --receipt output/bl-ml-epoch-20261116/chat-flow-receipt.json
# Chỉ sau restart thật, dùng chính receipt trên, không gửi luồng thay thế:
.venv-software/bin/python scripts/smoke_chat_input_refresh.py --verify-receipt \
  --receipt output/bl-ml-epoch-20261116/chat-flow-receipt.json
```

Run đã lưu receipt thì dùng verify, không chạy lại/ghi đè. Test tạo proposal
nhưng không accept target. Provider có thể gọi nếu dev đã bật và có budget
user duyệt; usage của chính hai Chat jobs nằm trong receipt. Native BL_ML là
gate riêng với giải thích OpenAI. Evidence training/review/publication/model
và canonical facts/hash nằm ngoài Git ở output/bl-ml-epoch-20261116.

### Audit point-in-time của receipt v5

Xem [phạm vi và khoảng trống bằng chứng](POINT_IN_TIME_AUDIT.md).
CLI chỉ đọc original receipt/model/bundle/snapshot, Market owner transaction
READ ONLY và cached artifacts; không tạo snapshot/train/approval/proposal mới
hoặc gọi provider. Output audit riêng, không sửa model flag.

```sh
.venv-software/bin/python scripts/audit_model_point_in_time.py \
  --receipt output/bl-ml-epoch-20261116/chat-flow-receipt.json \
  --output output/point-in-time-v5
.venv-software/bin/python -m pytest tests/software/test_point_in_time_audit.py \
  tests/software/test_temporal_regressions.py -q
```

`report.json` tách live integrity và historical evidence; `market-evidence.json.gz`
lưu rows/revisions/quality refs nén, ngoài Git. Exit0 không phải chứng nhận PIT:
xem NOT_EVIDENCED, protocol limitations và cờ false. Không backdate first-seen,
đổi epoch/snapshot/hash để biến kiểm tra thành PASS.
