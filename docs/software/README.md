# Software foundation — Identity/BFF và Portfolio/Quant

Hướng dẫn hiện hành: [Setup môi trường, Swagger và Postman](SETUP_AND_API_TESTING.md).
Đối chiếu các mốc và bằng chứng ngày 09/10/2026 tại
[trạng thái hiện thực](IMPLEMENTATION_STATUS.md). Phần cập nhật thêm Market Data,
staging template và core fixtures; record 26/09 bên dưới là lịch sử kiểm chứng.

**Cập nhật 10/10/2026:** stack local hiện đã healthy; real JWT/API/Broker workflows,
DB/broker boundaries và persisted receipt sau restart đạt. Có 153 Python tests.
Chi tiết các lỗi runtime đã sửa và giới hạn HTTP BFF/browser tại status file.

Giữ một Git monorepo. Phần nghiên cứu Phase 1 tại root vẫn giữ đường dẫn hiện tại;
phần ứng dụng được thêm độc lập để tránh phá các script, dữ liệu và thí nghiệm cũ.
Không tạo AuthService hoặc AllocationService riêng.

```text
apps/web/                    Next.js UI và BFF; OIDC, cookie/session, proxy
services/portfolio/          Portfolio API, DB/migrations, job/result workers
services/quant-serving/      Ready-input API, DB/migrations, numerical workers
services/market-data/        CSV/normalized ingestion, revisions, immutable snapshots
packages/portfolio-core/    Numerical package cài bằng pip; không phụ thuộc root
packages/contracts/         Wire contracts, OpenAPI và event schemas
packages/service-auth/      Xác thực JWT/JWKS dùng chung; không có business DB
infra/local/                Compose, bootstrap Keycloak/DB/broker, demo artifacts
tests/software/             API, auth, workflows và integration bằng SQLite
scripts/                    Xuất contracts, constraints và smoke test local stack
```

Mỗi service sở hữu database/migration và deployment riêng. Shared packages không
chia sẻ ORM hoặc truy cập chéo database. Khi có nhu cầu release độc lập theo nhóm,
có thể tách service sang repo khác dựa trên các boundary này; hiện chưa cần di
chuyển toàn bộ Phase 1 vào một thư mục mới.

## Đã hiện thực

- Keycloak realm với năm role: `investor`, `researcher`, `data-operator`,
  `model-reviewer`, `system-admin`. BFF dùng authorization code + PKCE, state,
  nonce; token được mã hóa trong Redis, browser giữ cookie HttpOnly. Có CSRF,
  refresh lock, logout và khôi phục kết nối Redis.
- Portfolio xác thực issuer/audience/signature/expiry và scope. Tất cả dữ liệu
  riêng được giới hạn theo owner lấy từ JWT; admin cũng không tự động được đọc
  danh mục của người khác. Các role dành cho quản trị dữ liệu/model đã được khai
  báo, nhưng các API quản trị tương ứng nằm ở milestone sau.
- Tạo, liệt kê, đọc và cập nhật danh mục. PATCH yêu cầu `If-Match` theo `ETag`;
  mỗi cập nhật tăng version.
- `POST /api/v1/portfolios/{id}/recommendations` yêu cầu `Idempotency-Key`, trả
  HTTP 202 và job/status URL. Portfolio chốt input/version/hash, ghi job + outbox
  cùng transaction. Quant xử lý bất đồng bộ qua RabbitMQ; mỗi bên có inbox để
  loại trùng và database riêng. Publisher chờ broker xác nhận.
- Portfolio kiểm tra lại strategy, core version, asset order, tính khả thi và
  thời hạn trước khi lưu recommendation. Có API đọc job, kết quả và lịch sử;
  kết quả giữ provenance và vốn/constraints của yêu cầu đã nhận.
- Core có EW, MVO và BL_ML với đầu vào số được chuẩn bị trước; từ chối input sai,
  thiếu ML views và bài toán bất khả thi. Đóng gói wheel không cần import code
  từ root. Chi tiết khoa học tại [portfolio-core](../../packages/portfolio-core/README.md).
- Market Data có database/roles/migration riêng, data-operator ingestion, durable
  broker jobs/outbox/inbox, hash-pinned CSV, unit conversion và immutable snapshots.
  Chi tiết tại [Market Data](../../services/market-data/README.md).
- Có Swagger Bearer Authorize, Postman collection/environment, setup CLI và đường
  upgrade local cũ không reset volumes/realm. Staging template dùng external TLS
  dependencies và image/secret bắt buộc; chưa deploy staging thật.

Luồng chính: Browser → Next BFF → Portfolio API → command outbox → RabbitMQ →
Quant worker → numerical core → result outbox → RabbitMQ → Portfolio result
consumer → recommendation lưu bền vững. Browser poll job rồi đọc kết quả.

## Chạy local

Yêu cầu Docker Desktop có đủ dung lượng trống và đang chạy. Từ repo root:

```sh
python3 scripts/setup_software.py up --enable-test-client
```

Mở <http://localhost:3000>. Tài khoản local nằm trong file ignored
`infra/local/.generated/accounts.json`; bootstrap không in password ra log và
giữ nguyên secret khi chạy lại. `--enable-test-client` phục vụ smoke test; setup
bật trước khi import realm mới hoặc bổ sung qua upgrade cho realm local cũ.
Client dùng cho browser không bật password
grant. Xem [hướng dẫn stack](../../infra/local/README.md) và
[cấu hình BFF](../../apps/web/README.md).

Demo chỉ có EW/MVO trên ba tài sản giả định, hết hạn sau một ngày. Muốn cập nhật
demo, chạy `python3 infra/local/bootstrap.py --refresh-demo`. Bundle mới có ID và
hash mới; các bundle cũ giữ nguyên. BL_ML chỉ chạy khi có bundle hợp lệ chứa
model được phê duyệt và P/Q/confidences phù hợp, không tự fallback sang EW.

## Kiểm chứng

Dùng môi trường riêng, không thay dependency của Phase 1:

```sh
python3.12 -m venv .venv-software
.venv-software/bin/python -m pip install -c services/quant-serving/requirements.lock -e packages/contracts -e packages/service-auth -e packages/service-observability -e packages/portfolio-core -e services/portfolio -e services/quant-serving -e services/market-data pytest==8.4.2 ruff==0.13.2 httpx==0.28.1
.venv-software/bin/python -m pytest tests/software packages/portfolio-core/tests -q
.venv-software/bin/python -m ruff check packages services tests/software infra scripts/export_software_contracts.py scripts/lock_software_dependencies.py scripts/smoke_software.py scripts/setup_software.py
.venv-software/bin/python scripts/export_software_contracts.py
npm --prefix apps/web ci
npm --prefix apps/web test
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
```

Khi stack đã healthy:

```sh
.venv-software/bin/python infra/local/verify_boundaries.py
python3 scripts/smoke_software.py
docker compose --env-file infra/local/.generated/.env -f infra/local/compose.yaml restart portfolio-api portfolio-consume portfolio-dispatch quant-api quant-consume quant-dispatch market-api market-consume market-dispatch
docker compose --env-file infra/local/.generated/.env -f infra/local/compose.yaml up -d --wait
python3 scripts/smoke_software.py --verify-receipt
```

Smoke test dùng JWT thật từ Keycloak, tạo một danh mục local, chạy MVO qua broker,
kiểm tra idempotency/ownership/provenance và lưu receipt không chứa token để
kiểm tra sau restart. Script boundary kiểm tra quyền DB/broker và web password
grant bị tắt. Workflow GitHub Actions chứa cả unit/build và local-stack gate;
workflow chưa được chạy trên GitHub trong lần thực hiện này.

**Trạng thái kiểm chứng 2026-09-26:** Python/API/core đạt 84 tests. Các migration
đã chạy với SQLite; wheel core đã được cài và gọi ngoài repo. Web đã qua 21 tests,
typecheck và production build; có thử Redis thật bị dừng/khởi động lại. Compose
config hợp lệ; PostgreSQL/RabbitMQ/Redis từng healthy, nhưng Docker sau đó lỗi
`overlay2`/BuildKit I/O do ổ dữ liệu host đầy (còn khoảng 220 MiB lúc lỗi). Do đó **chưa
xác nhận toàn bộ luồng Keycloak → BFF → PostgreSQL/RabbitMQ bằng stack thật**,
chưa xác nhận migration/quyền runtime của tất cả service bằng PostgreSQL thật.
Cần giải phóng dung lượng, khởi động lại Docker bình thường và chạy các lệnh
integration trên; không cần factory reset hoặc xóa volumes.

## Phạm vi tiếp theo

Chưa có crawler/live Market Data, training/promotion Model Registry, Chat/RAG,
onboarding risk profile đầy đủ, acceptance/ledger hoặc giao dịch. Adapter input
hiện đọc artifact được chuẩn bị phía server; chưa nối các service dữ liệu/model
đó. Core BL_ML hiện tính từ views đã cung cấp; không khẳng định parity với toàn
bộ pipeline `ranking_absolute` của Phase 1. Đây là phần nền tảng auth và
recommendation đã thống nhất, không phải hoàn tất toàn bộ Phase 2.
