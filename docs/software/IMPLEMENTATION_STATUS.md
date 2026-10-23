# Tiến độ software app — 10/10/2026

## OpenTelemetry + Jaeger — kiểm chứng local ngày 10/10/2026

Distributed tracing đã bật bằng `compose.tracing.yaml`, có manual spans cho
BFF/API, outbox dispatch, RabbitMQ publish/consume, numerical allocation và
lưu kết quả. Context nullable được lưu cùng Job/Run/Outbox transaction; không
thay Envelope, input hash hoặc core `0.1.0`. Polling có trace riêng và link tới
trace submission. UI hiện link **Xem trace trong Jaeger** cho job/kết quả mới.

| Kiểm tra | Bằng chứng mới |
| --- | --- |
| Offline Python/API/core | **188 passed**, 1 warning Starlette/AnyIO có sẵn; scoped Ruff đạt. Migrations additive/legacy null, retry/restart, hash/idempotency và privacy được kiểm tra. |
| Web/BFF | **44 passed**, không skip; typecheck và production Docker build đạt. Filter bỏ Next/auth spans trước batch; exporter treo/lỗi không làm hỏng business response. |
| Contracts/config/setup | Export 9 contracts lặp giữ hash; base + tracing overlay hợp lệ; `prepare --tracing --enable-test-client`, `check --tracing` và `up --tracing --skip-install --skip-build` đạt. |
| Real migrations/persistence | Ba owner migrations exit 0; old schema-2 receipt đọc lại đúng recommendation, Market job/snapshot, hash/history/ownership sau cập nhật. DB/broker/identity boundaries đạt. |
| Tracing flow + fault probes | `scripts/smoke_tracing.py --restart-dispatcher --collector-outage` đạt: business MVO + Market/snapshot chạy khi Jaeger dừng; job QUEUED được dispatch sau restart vẫn giữ origin trace; fresh BFF code/PKCE/CSRF flow và Market ingestion xuất đầy đủ spans. |
| Jaeger/UI | Recommendation **17 spans / 7 process names**, Market **7 spans / 3 process names**. Trình duyệt thật đăng nhập alice, mở persisted result và thấy link đúng trace. Jaeger timeline xác nhận `portfolio_core.allocate` và đường kết quả về Portfolio. |
| Logs/privacy/review | Origin recommendation khớp **10 JSON log records / 6 processes**; không có generated credentials trong logs và không có tested private values/unsafe attributes trong trace. Hai lượt review độc lập; findings đã sửa và regression tests đạt. |

Trace recommendation tại thời điểm kiểm chứng:
[6829e4532520eb66e029b75af708f464](http://localhost:16686/trace/6829e4532520eb66e029b75af708f464).
Market:
[337dd2cb4a49c2c6d6cb23aa2613ae17](http://localhost:16686/trace/337dd2cb4a49c2c6d6cb23aa2613ae17).
Receipt không token: `infra/local/.generated/tracing-receipt.json`.
[Ảnh timeline](assets/tracing-recommendation-2026-10-10.jpg).

Mạng tải pip trong Docker chỉ khoảng 20 kB/s trong lần build đầu; build đó được
dừng, rồi ba backend images được build từ **source hiện tại và Linux wheels tải
từ PyPI trên host**, đúng runtime constraints. Dockerfile tạm chỉ thay cách lấy
dependency bằng `--no-index --find-links`/`--no-build-isolation`; `pip check` trong
images đạt. SDK source SHA-256 trong container khớp source checkout. Cấu hình
Docker credentials tạm được dùng; config toàn cục, generated secrets và volumes
được giữ nguyên. Temporary wheelhouse đã xóa; không prune/reset.

Jaeger dùng RAM; restart collector mất trace history, application data vẫn còn.
Các job trước tracing có null fields, không tái dựng được timings cũ. Đây là
observability local; chưa có centralized log storage/Loki, retention backend,
metrics/alerts hay staging tracing deployment. `npm audit` còn 3 high findings
trên Next/sharp/source-map-js hiện hữu; không thuộc dependencies OTel vừa thêm.
GitHub workflow mới chưa chạy trên GitHub. Xem [hướng dẫn tracing](TRACING.md).

Các mục bên dưới lưu lịch sử của những lần triển khai/kiểm chứng trước.

## Lần chạy lại 10/10/2026 — stack local đã hoạt động

Dung lượng host đã tăng lên khoảng 14 GiB trước chạy, còn khoảng 12 GiB sau
build. Docker server 27.5.1 đã phản hồi. Đã khắc phục các lỗi runtime và chạy
thành công stack hiện hành, giữ nguyên generated credentials và named volumes.

| Kiểm tra mới | Kết quả |
| --- | --- |
| Startup/migrations | **passed**: Keycloak và ba backend migration exit 0; web/APIs/infrastructure healthy. `setup_software.py up --enable-test-client --skip-install --skip-build` exit 0 với images mới đã build. |
| DB/broker/identity boundaries | **passed**: PostgreSQL owner/runtime DML, denied DDL/role escalation/cross-DB; quorum/DLQ và publisher/consumer ACLs; web password grant bị từ chối và test-client Market claims hợp lệ. |
| Real API workflow | **passed**: JWT thật, async MVO qua broker, idempotency, ownership, provenance/history, missing-model rejection; Market ingestion và snapshot thật. |
| Persistence | **passed**: restart cả chín Portfolio/Quant/Market API/worker processes rồi đọc lại receipt cũ, IDs/hash và ownership không đổi. |
| BFF HTTP integration | **passed**: real authorization code + PKCE callback, cookie session, CSRF mutation, async polling/result và logout. HTTPX phải mô phỏng riêng việc gửi Secure cookies trên localhost; không sửa cookie policy của app. Chưa kiểm tra visual UI bằng trình duyệt thật. |
| Offline regressions/review | **passed**: **153 Python tests**, một cảnh báo Starlette/AnyIO có sẵn; software Ruff đạt. Reviewer độc lập kiểm tra các sửa auth/broker, không có important finding. |
| URLs | Web `http://localhost:3000`; Swagger Portfolio/Quant/Market `http://localhost:8001/docs`, `:8002/docs`, `:8003/docs` đều HTTP 200. |

Các lỗi phát hiện và xử lý:

1. Container `identity-migrate` cũ lỗi `java.io.EOFException` khi đọc Quarkus
   serialized application. Image chạy được trong container sạch; tạo lại riêng
   container migration đã giải quyết, database/realm hiện có được giữ nguyên.
2. JWT Keycloak thiếu `sub`, khiến Portfolio HTTP 401. Bootstrap trước đó tự
   khai báo client scopes nhưng thiếu `basic`/Subject mapper. Đã thêm scope mapper
   và attach default cho web/service/test client; upgrade sửa realm cũ theo cách
   additive, không thay users/secrets/grants. Token verifier vẫn bắt buộc `sub`.
   [Keycloak xác nhận Subject mapper thuộc basic scope](https://github.com/keycloak/keycloak/blob/main/docs/documentation/upgrading/topics/changes/changes-25_0_0.adoc).
3. Script boundary gọi sai endpoint permissions (HTTP 404); đã đổi sang
   `/api/vhosts/portfolio/permissions` theo
   [RabbitMQ HTTP API](https://www.rabbitmq.com/docs/http-api-reference).
   Đồng thời sửa `basic_qos` với đủ `prefetch_size`, `prefetch_count`, `a_global`
   theo chữ ký thư viện đang cài. Cả hai có regression RED→GREEN và live check.
4. Build web mặc định mắc ở `docker-credential-desktop`, dù anonymous registry
   probe và pinned Node manifest đạt. Đã build bằng **DOCKER_CONFIG tạm và
   DOCKER_HOST tường minh**, không sửa login config toàn cục. Images hiện đã có;
   dùng `--skip-build` chỉ khi source/image khớp. Hướng dẫn có workaround cho lần
   cần build mới nếu helper còn mắc.

Receipt local schema 2 được tạo lúc `2026-10-10T04:13:42.979100+00:00`, không
chứa token. Quant demo mới:
`demo-20261010T040659196977Z`, SHA-256
`5f3cf99abc4404b6f2c0bc0affd9f3dac7b463074fa53f958bd6a27e13edf220`.
Market artifact mới `demo-stock-20261010T040659200563Z.csv`, SHA-256
`557c1f6b01c7eb435b4048ba432e878a2c688884f5680e1558f28ff501db609d`.
Old bundles, CSVs, users và volumes giữ nguyên. Demo vẫn là dữ liệu tổng hợp,
không chứng minh live provider/trained-model parity hoặc staging deployment.

Các phần dưới lưu lịch sử chẩn đoán trước khi khắc phục; trạng thái blocked
trong chúng đã được cập nhật bằng bằng chứng của lần chạy lại bên trên.

## Chẩn đoán runtime ngày 10/10/2026

- Đã chạy `setup_software.py check` và `up --enable-test-client --skip-install`:
  cả hai dừng tại prerequisite Docker daemon sau timeout 20 giây.
- `docker context show` trả `desktop-linux`; truy vấn Docker server và Compose
  `ps -a` đều timeout 8 giây. Compose `config --quiet` vẫn hợp lệ.
- Filesystem host còn khoảng 493 MiB lúc kiểm tra, báo 100% capacity.
- Docker backend log lúc **10:42:16 ngày 10/10/2026 (Asia/Ho_Chi_Minh)** ghi
  `Failed to write to log file dockerd ... no space left on device`.
  Docker daemon đồng thời báo `input/output error` khi mở
  `/var/lib/docker/buildkit/executor/runc-log.json` và `overlay2/.../lower`.
- Đây là bằng chứng lỗi storage/hạ tầng Docker. Chưa thể kiểm tra lỗi bên trong
  application services bằng stack thật. Cần giải phóng dung lượng host trước,
  khởi động lại Docker bình thường rồi kiểm tra daemon và chạy lại setup.
  Dữ liệu, generated credentials và Docker volumes được giữ nguyên trong đợt
  chẩn đoán này; không thực hiện prune/reset.

Phần dưới là record hiện thực và kiểm chứng offline ngày 09/10/2026.

Đối chiếu theo yêu cầu người dùng và kiến trúc đã chốt. Trước đợt này đã có
Identity/BFF, Portfolio/Quant, outbox/inbox, core package và CI; baseline **84
Python tests đạt**. Đợt này bổ sung Market Data, staging template, fixtures/versioning
và hướng dẫn setup/API. Mã nguồn và cấu hình đạt các kiểm tra offline bên dưới;
**chưa xác nhận toàn bộ stack thật hoặc staging đã triển khai**.

## Các mốc

| Mốc | Đã có trong mã/cấu hình | Giới hạn còn lại |
| --- | --- | --- |
| Service foundation, contracts, CI, dev/staging | Monorepo Next BFF, Portfolio, Quant, Market; package/image/migrations/health riêng. Ba OpenAPI với Swagger Bearer; sáu JSON contracts/DTO schemas. CI Python/web/local stack/persistence và staging config. Local Compose + external-dependency staging template. | GitHub workflow chưa được chạy từ thay đổi này; staging chưa deploy. Các service của use case tương lai được giữ trong kiến trúc, chưa tạo empty scaffolds. |
| Keycloak, BFF session, ownership, schema theo use case | Code/PKCE, state/nonce, encrypted Redis tokens, opaque HttpOnly cookie, CSRF/refresh/logout; issuer/audience/expiry/signature/roles/scopes. Owner-scoped Portfolio/recommendations/jobs, Market creator-scoped ingestion jobs. DB owner/migrator/runtime riêng; migrations cho ba application DB. | Tests BFF/OIDC/Redis đạt; chưa chạy login thật với Keycloak/browser trong đợt này. SQLite không chứng minh runtime grants PostgreSQL. |
| Market ingestion/snapshots, durable jobs, outbox/inbox | `market_service`, CSV registry hash-pinned và normalized observations stock/fund/gold; explicit unit conversion; append-only revisions; atomic job/outbox và inbox/revision/status; durable quorum queue/DLQ; deadlines. Immutable snapshot pins/hashes, cutoff theo ingestion availability, missing/stale/ambiguous-source checks. Local upgrade giữ secrets/volumes/realm. | Provider baseline là CSV/import; chưa có live upstream crawler, exchange calendar/corporate actions. Market snapshots chưa tự xây numerical bundle cho Quant. Live broker/ACL/upgrade/persistence checks chưa chạy được. |
| Tách core, fixtures, version hóa app | Wheel `portfolio-core==0.1.0`, không dựa root globals/paths. Năm synthetic golden cases EW/MVO/BL_ML, 15 tests mới. Changelog và compatibility policy phân biệt refactor/legacy preservation với app behavior changes. | Fixtures chứng minh numerical contract hiện hữu, chưa chứng minh toàn bộ Phase 1 ranking/selection/trained-model parity. Không thay runtime/core version trong đợt này. |

## Bằng chứng kiểm chứng

Các lệnh chạy ngày 09/10/2026, múi giờ Asia/Ho_Chi_Minh:

| Layer | Trạng thái | Bằng chứng |
| --- | --- | --- |
| Python/API/core | **passed** | `.venv-software/bin/python -m pytest tests/software packages/portfolio-core/tests -q`: **150 passed**, 1 cảnh báo deprecated alias của Starlette/AnyIO. |
| Software lint | **passed** | Ruff trên packages/services/tests/software/infra và bốn software scripts. Broad lint `scripts/` phát hiện 56 lỗi có sẵn trong scripts nghiên cứu; không sửa nghiên cứu để làm software CI xanh. |
| HTTP/event contracts | **passed** | Export 9 JSON files; export lặp giữ nguyên SHA-256. Bearer security scheme có ở protected operations, health không cần token. |
| DB migrations | **passed (SQLite)** | Cả Portfolio, Quant và Market upgrade → metadata check → downgrade → upgrade. Chưa thay thế kiểm tra PostgreSQL thật. |
| Web/BFF | **passed (offline/local isolated tests)** | **21 tests**, `npm run typecheck` và `npm run build`. Suite Redis recovery đã chạy, không skip; OIDC transport deterministic ký JWT thật nhưng không phải live Keycloak login. |
| Core wheel | **passed** | Build/install vào venv tạm ngoài repo, import từ site-packages; copied suite **68 passed, 1 expected skip** do không có legacy source trong wheel environment. Deliberate risk-aversion mutation bị golden fixture phát hiện, sau restore suite đạt. |
| Local/staging config | **passed** | Hai Compose `config --quiet`; staging validator với example sentinel values đạt, strict mode từ chối placeholders. Không deploy staging. |
| Setup/Postman | **passed** | `setup_software.py prepare --enable-test-client --skip-install` dùng lại venv/node_modules và giữ credentials. `setup_software.py verify` chạy toàn bộ offline gates thành công. Postman 35 requests, 41 event scripts parse đúng; JSON hợp lệ và secrets/token values để trống. |
| Live Docker infrastructure/API/BFF/persistence | **blocked** | Docker Desktop process có tồn tại nhưng daemon `docker info` timeout trong probe 8 giây và `setup ... check` timeout 20 giây. Không có bằng chứng migration/grants/JWT/RabbitMQ/restart từ stack thật trong đợt này. |
| Independent source/config review | **passed** | Reviewer độc lập không tìm thấy Critical/Important blocker đã kiểm chứng; không thay live verification bằng review. |

## Chạy tiếp trên máy khi Docker đáp ứng

Theo [hướng dẫn setup và API](SETUP_AND_API_TESTING.md), điểm vào là:

```sh
python3 scripts/setup_software.py up --enable-test-client --refresh-demo
python3 scripts/setup_software.py verify --live
```

Lệnh `up` dùng dependency environment đã hợp lệ, build images, bật dependency
services, reconcile DB/broker/realm local cũ rồi chạy toàn bộ stack. Giữ credentials
và volumes; demo refresh tạo artifact identity mới. Smoke tạo dữ liệu demo và
receipt không chứa token cho Portfolio recommendation và Market job/snapshot.
Sau restart workers, `scripts/smoke_software.py --verify-receipt` đọc lại đúng
IDs/hashes cũ; hướng dẫn có lệnh restart đầy đủ.

Không đánh dấu live integration, provider crawling, numerical research parity
hoặc staging deployment hoàn tất chỉ từ các kết quả offline này. Chưa commit,
push hoặc deploy thay đổi; giữ các file/chỉnh sửa đã có của người dùng.
