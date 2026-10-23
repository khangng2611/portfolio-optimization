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
  `roles`; dùng `alice`/`bob` cho kiểm thử owner và `data-operator` cho Market write.
- `infra/local/.generated/.env`: `OIDC_TEST_CLIENT_SECRET` và
  `QUANT_CLIENT_SECRET` cho các request auth bên dưới.

Đọc các file này tại máy, giữ credentials trong kho bí mật hoặc giá trị local
của Postman. Không đưa nội dung vào commit, log, ảnh chụp hoặc environment export.
Giữ `secrets.json`, `.env` và volumes đi cùng nhau. Bootstrap giữ secrets cũ;
thay password trong file không tự đổi password đã cài vào database/identity.

`--enable-test-client` cần được bật **trước lần realm import đầu tiên**. Client
`portfolio-test` cho password grant chỉ phục vụ disposable local realm.
Với stack cũ đã import, chạy lại lệnh `up --enable-test-client`: bước upgrade
bổ sung client thiếu và Market scopes/audience qua admin API mà không reset
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
scope=openid portfolio:read portfolio:write market:read market:write
```

Token của `alice` đọc được Market nhưng không được Market write vì thiếu role
`data-operator`. Lấy token của `data-operator` cho ingestion/snapshot. Token test
client có audiences Portfolio/Market; không dùng để gọi Quant internal API.
Với Quant, dùng `grant_type=client_credentials`, `client_id=portfolio-service`,
`client_secret=<QUANT_CLIENT_SECRET>`, `scope=quant:resolve`.

Tại `/docs`, nhấn **Authorize**, dán giá trị `access_token` vào Bearer security
scheme rồi nhấn **Authorize** và **Close**. Chỉ dán token, không thêm tiền tố
`Bearer ` trong hộp này. Chọn endpoint → **Try it out** → nhập JSON/header/query
→ **Execute**. Swagger gửi `Authorization: Bearer <token>` tự động. Nhận 401
thì lấy access token mới; 403 thì kiểm tra role/scope/audience.

Health endpoints dùng được trước khi authorize. Quant Swagger dành cho contract
service-to-service; web không gọi Quant trực tiếp.

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

Market ingestion/provider registry hiện là nền cho CSV stock/fund/gold.
Chưa xác nhận có crawler live upstream. Market snapshot chưa tự xây prepared
numerical bundle cho Quant; recommendation hiện dùng prepared bundles có
provenance theo catalog riêng.

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
