# Nền tảng software và tổ chức repository giai đoạn 2

Ngày đối chiếu: **26/09/2026**, múi giờ Asia/Ho_Chi_Minh.  
Trạng thái: **đề xuất để chốt cấu trúc trước khi triển khai**. Các tiêu chí bên dưới là yêu cầu nghiệm thu, chưa phải kết quả đạt được.

## 1. Phạm vi đến hôm nay

Mục tiêu của yêu cầu: bắt đầu hiện thực phần software cho ứng dụng chatbot tư vấn danh mục, tái sử dụng core giai đoạn 1 và lựa chọn cách tổ chức repository. Hướng sản phẩm nhiều người dùng, các service triển khai độc lập đã được ghi trong [đặc tả giai đoạn 2](../../TECHNICAL_SPECIFICATION_PHASE_2.md), mục 3 và 7. Bản này cụ thể hóa repository và thứ tự thực hiện, không thay đổi kiến trúc domain đã có.

Nguồn lịch chính là [Google Sheet, HK261](https://docs.google.com/spreadsheets/d/1Z8h67JC44iQIYguh-iZNZqC0b2zqZSIMlljW0kosMH8/edit?gid=1869718089#gid=1869718089), đọc trực tiếp và xuất XLSX ngày 26/09/2026. Hôm nay thuộc **tuần 3, 21–27/09**.

| Hàng trong Sheet | Mốc | Phần software phải xét đến hôm nay | Hiện trạng đã quan sát |
|---|---|---|---|
| A3:G3 | Tuần 1, 07–13/09 | Chọn stack; init codebase; tham số hóa và đóng gói core | Đã có đặc tả stack/kiến trúc. Chưa có application workspace hoặc Python package có metadata build. |
| A4:G4 | Tuần 2, 14–20/09 | Database, auth/RBAC, worker crawl định kỳ ghi DB | Có crawler xuất CSV. Chưa có service DB/migrations, Identity/BFF hoặc scheduler bền vững trong repo. |
| A5:G5 | Tuần 3, 21–27/09 | Expose allocation API, lưu kết quả; lưu model và lịch retrain | Có numerical functions, backtest và model save/load bằng pickle. Chưa có API, registry hoặc durable train jobs. |

**Phân biệt hai bản lịch:** bản Markdown tại `outputs/phase2-timeline-20260926/timeline-de-xuat.md` gom tuần 1–3 thành rà soát. Sheet hiện tại vẫn giữ nguyên công việc software của ba tuần này; tuần 4 trở đi đã có nội dung điều chỉnh. Vì yêu cầu trỏ tới Sheet, các việc chưa làm tuần 1–3 được ghi nhận là backlog cần triển khai, không tự coi là hoàn thành hoặc tự dời hạn.

**Chuẩn hóa backlog theo kiến trúc:** giữ nhu cầu nghiệp vụ của các hàng cũ, nhưng không triển khai nguyên văn những chi tiết lệch đặc tả. Các điều chỉnh dưới đây chỉ nằm trong bản thiết kế này; chưa sửa Google Sheet.

| Nội dung cũ trong Sheet | Nội dung áp dụng theo đặc tả giai đoạn 2 |
|---|---|
| Tự xây register/login/refresh/logout; JWT trong browser cookie | Keycloak quản lý identity; BFF dùng OIDC và opaque session cookie; access/refresh tokens ở server-side session store |
| RBAC chỉ investor/admin | Ma trận mục 14.2: Investor, Researcher, Data operator, Model reviewer, System admin; mỗi endpoint kiểm tra role/scope và quyền sở hữu resource |
| AllocationService gom API, phép tính và các bảng | Recommendation API thuộc Portfolio; Quant Serving chạy DecisionEngine; ML Platform sở hữu model artifacts/registry |
| Tạo full schema | Migrations thuộc từng owner service và được bổ sung theo use case |

Auth và recommendation API là các khả năng cần có; chúng không tương ứng với hai Python microservice mới tên Auth và Allocation. Tuần 1–3 là nguồn nhu cầu cần đối chiếu, không phải chỉ dẫn thay thế ranh giới service đã chốt.

Chat/SSE ở tuần 8 (26/10–01/11), Knowledge/RAG ở tuần 9 (02–08/11). Đợt đầu xây nền tảng và luồng allocation phục vụ chatbot; chưa bao gồm triển khai trọn chat/RAG. Các mốc tuần 4–6 đã bổ sung contracts, trusted core và Quant Serving là dependency thực tế cho việc hoàn thành backlog tuần 3, không phải bằng chứng backlog đó đã hoàn tất.

## 2. Lựa chọn repository

**Đề xuất: tiếp tục repository Git hiện tại theo monorepo, chuyển dần theo ranh giới trách nhiệm.**

| Phương án | Ưu điểm | Chi phí / vấn đề | Khuyến nghị |
|---|---|---|---|
| Monorepo, trích xuất core từng bước | Thay đổi core, contracts, API và fixtures có thể review cùng nhau; giữ lịch sử nghiên cứu; ít thao tác phối hợp release | Cần kiểm soát dependency, build context và CI theo service | Chọn lúc này |
| Repo ứng dụng mới, repo hiện tại phát hành core package | Quyền truy cập và release nghiên cứu/software tách rõ | Cần registry/package release và consumer compatibility trước mỗi thay đổi liên repo; khó khi API core còn đang hình thành | Hợp lý khi có nhóm/phân quyền/lifecycle độc lập |
| Chuyển toàn bộ repo cũ vào một thư mục `core/` | Cây thư mục nhìn gọn nhanh | Trộn numerical library, CSV, crawler, training CLI, manuscript và logs; làm lệch đường dẫn/import; chưa tạo package độc lập | Không chọn |

Microservices vẫn có image, database owner, lockfile và rollout riêng trong cùng một repo. Không cần repo mới hoặc Git submodule để đạt independent deployment.

Một repo mới nên được cân nhắc lại khi cần tách quyền truy cập source/data, có đội phụ trách độc lập, hoặc core có vòng đời/phạm vi sử dụng khác ứng dụng. Khi đó phát hành wheel có version trước rồi đổi dependency; tránh copy core giữa repo.

## 3. Cấu trúc đích

Đây là cấu trúc đích, **không phải yêu cầu tạo mọi thư mục rỗng ngay**. Service được hiện thực theo từng luồng có thể nghiệm thu.

```text
portfolio-optimization/
├── apps/
│   └── web/                         # Next.js UI + BFF, package.json + lockfile
├── services/
│   ├── portfolio/                   # Profile, policy, portfolios, allocation saga
│   ├── market-data/                 # Ingestion, prices, immutable snapshots
│   ├── quant-serving/               # Inference, selection, numerical runs
│   ├── ml-platform/                 # Training, registry, promotion
│   ├── chat/                        # Hội thoại, scoped tools, SSE; tuần 8
│   ├── knowledge/                   # Corpus, retrieval, citations; tuần 9
│   └── research/                    # API/worker thí nghiệm; khác research/ bên dưới
├── packages/
│   ├── portfolio-core/              # Wheel thuần numerical, import portfolio_core
│   │   ├── pyproject.toml
│   │   ├── src/portfolio_core/
│   │   │   ├── config.py            # Immutable config theo request
│   │   │   ├── decision.py          # One-step DecisionEngine
│   │   │   ├── allocation/          # BL, optimizer, constraints
│   │   │   ├── selection/
│   │   │   ├── features/
│   │   │   ├── views/
│   │   │   └── forecasting/         # Inference và feature contract
│   │   └── tests/
│   └── contracts/
│       ├── openapi/                 # HTTP contract theo service/version
│       ├── events/                  # AsyncAPI + JSON Schema
│       └── generated/               # Clients sinh tự động, không chứa ORM
├── research/
│   ├── phase1/                      # Đích migration về sau: CLI/config/protocol cũ
│   └── experiments/                 # Protocols/runners cho nghiên cứu mới
├── infra/
│   ├── local/                       # Compose, Keycloak realm, DB provisioning
│   ├── helm/                        # Deploy từng service
│   └── terraform/                   # Hạ tầng staging/production khi đến mốc
├── tests/
│   ├── contract/
│   └── e2e/
├── docs/
│   ├── adr/
│   └── thesis-evidence/
├── datasets/                        # Research inputs hiện có; giữ nguyên lúc đầu
├── reports/                         # Kết quả/báo cáo hiện có
├── csonet-paper/                    # Bản thảo hiện có
└── logs/                            # Historical evidence hiện có
```

Trong bước đầu, `backtest/`, `gen_view/`, `utils/`, `crawl/`, `config.py` và `assets_*.json` vẫn ở vị trí hiện tại. Tạo workspace mới theo kiểu bổ sung, sau đó extract từng module có kiểm chứng. `research/phase1/` chỉ được dùng khi có đợt migration riêng đã kiểm tra entry point/path; không đồng thời tạo hai bản source cùng được sửa.

Mỗi Python service dùng namespace riêng, ví dụ:

```text
services/portfolio/
├── pyproject.toml
├── uv.lock
├── Dockerfile
├── .env.example
├── migrations/
├── src/portfolio_service/
│   ├── main.py
│   ├── settings.py
│   ├── api/                         # HTTP DTO/routes/dependencies
│   ├── application/                 # Use cases, transactions, authorization
│   ├── domain/                      # Invariants, entities, policies
│   ├── ports/                       # Repository/provider interfaces
│   ├── adapters/                    # PostgreSQL, broker, HTTP, artifact store
│   └── workers/                     # Consumers, jobs, scheduling của owner
└── tests/
    ├── unit/
    └── integration/
```

Không tạo root `workers/` tập trung nghiệp vụ mọi service. API và workers cùng owner dùng chung package/image nhưng chạy process riêng. Identity dùng Keycloak được cấu hình dưới `infra/`; không viết thêm service quản lý mật khẩu.

## 4. Ranh giới dependency và dữ liệu

- `portfolio_core` không import FastAPI, SQLAlchemy, Celery, SDK LLM hoặc service package. Config và inputs được truyền tường minh; không dựa vào root `config.py`, working directory hoặc CSV trong repo để chạy wheel.
- Quant Serving và Research là consumer trực tiếp của core. Portfolio/Chat gọi service contract, không gọi solver hay import source nội bộ của Quant.
- Một service không import code hoặc ORM của service khác. `packages/contracts/` chia sẻ giao thức và generated clients; không chia sẻ database entities/repositories.
- Dev có thể dùng một PostgreSQL process với các logical database/roles riêng: Identity, Portfolio, Market, Quant, ML. Chat/Knowledge/Research bổ sung theo luồng. Runtime role chỉ truy cập DB owner; migrations dùng role riêng.
- Portfolio sở hữu recommendations/accepted targets; Quant sở hữu numerical runs/selection/forecast artifacts; ML sở hữu model registry; Market sở hữu asset master/prices/snapshot manifests. Không gom tất cả bảng tuần 3 vào một AllocationService có quyền ghi mọi DB.
- Wheel core và từng service pin dependency riêng. Dev có thể editable-install core; CI phải build wheel và test trong môi trường sạch ngoài repo root để phát hiện accidental imports. Release service pin core version/hash; không tự nâng tất cả consumer khi sửa core.
- Root `requirements.txt` tiếp tục là môi trường legacy đến khi parity được xác nhận. Không đưa toàn bộ Gradio/OpenCV/Torch và dependencies nghiên cứu vào mọi service image.
- Docker build context chỉ gồm service, contracts và wheel cần thiết; loại datasets, logs, cache, venv, manuscript. Dataset/model chạy app lưu ngoài source image bằng immutable artifacts có checksum.

`src/` layout hỗ trợ phát hiện khác biệt giữa import từ source tree và package đã cài; cần kiểm tra bằng wheel thật, không chỉ editable install. Nguồn: [PyPA](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/).

## 5. Mapping phần đã có

| Source hiện tại | Đích / trách nhiệm | Cách chuyển |
|---|---|---|
| `backtest/_black_litterman.py`, `_optimizer.py` | `portfolio_core/allocation` | Fixture trước; tham số hóa; giữ semantics legacy riêng với sửa hành vi app |
| `backtest/_ranking_helpers.py`, phần quyết định trong `_loop.py` | `portfolio_core/decision.py` | Tách one-step dùng chung, không lấy toàn bộ backtest làm request handler |
| `gen_view/view_generators.py`, `risk_management.py`, `stock_selection.py`, feature builders | Core views/regime/selection/features | Tách khỏi global paths/config; assets có thứ tự rõ ràng |
| `gen_view/xgboost/xgboost_core.py` | Core inference + ML Platform training/artifact adapters | Giữ feature schema thống nhất; tách I/O serialization và train orchestration |
| `gen_view/xgboost/model_train.py` | ML Platform worker; legacy CLI là adapter | Training được schedule/admin trigger, có job status; không train trong API request |
| `crawl/stock.py`, `fund.py`, `gold.py` | Market Data provider adapters/workers | Fetch theo asset/date range, normalize, persist revisions/snapshot; không import nguyên script để chạy ngầm |
| `utils/data_loader.py` | CSV adapter nghiên cứu/import ban đầu | App nhận snapshot đã version hóa; không đọc root CSV theo request |
| `_loop.py`, CLI, plotting, report/export | Research runner/adapters | Backtest giữ timeline và simulation; numerical decision dùng shared core khi đã parity |
| `datasets/`, `logs/`, `reports/`, manuscript | Research data/evidence/documentation | Không đóng vào wheel core; giữ nguồn và hash khi dùng làm fixtures |

## 6. Các điểm phải xử lý trước serving

Khảo sát source tại commit `5350e2a` trên branch `feat/enhance-performance`; working tree có tài liệu và outputs chưa track từ trước nhiệm vụ này. Không coi số commit đó là snapshot đủ của toàn bộ artifacts.

1. **Prediction khác backtest.** `config.py` chọn `ranking_absolute`. `backtest/_prediction.py` gọi `_views.generate_dynamic_views`, dispatcher chỉ có rule_based/relative/ml/combined. Backtest lại gọi `run_ranking_step` cho ranking modes. Không expose `get_next_period_weights()` rồi tuyên bố đã có parity.
2. **Cấu hình global.** Nhiều module import constants từ root `config.py`; default arguments được bind khi import. Không thay global theo user/request. Chuyển sang config immutable và kiểm tra hai requests khác policy chạy đồng thời không lẫn nhau.
3. **Path gắn source tree.** Data loader, crawlers và model cache dựa vào `Path(__file__).parents[...]`; training CLI thêm `sys.path`. Di chuyển toàn bộ vào `core/` có thể làm sai dataset/cache paths dù import vẫn thành công.
4. **Post-solve validation.** Optimizer normalize/redistribute weights và có fallback EW. Trước READY, service phải kiểm tra constraints trên final weights; không coi solver success là đủ. Các sửa mathematical behavior phải có version riêng, không lẫn vào refactor bảo toàn Phase 1.
5. **Model persistence chưa là registry.** Save/load hiện có dùng pickle và source-local cache. App cần manifest, cutoff, feature order, scaler state, checksums, candidate validation, explicit promotion và bundle READY ở serving.
6. **Crawler còn là batch CSV.** Có batch offsets cố định, ngày cuối lấy ngày chạy và unit conversion đặc thù. Worker mới cần input range, dedupe, retry, source state và publication timestamps. Data mới không tự ghi đè tập dữ liệu dùng tái lập Phase 1.
7. **Chưa thấy app tests/CI.** Script tên `_compare_backtests.py` là runner nghiên cứu, không phải bằng chứng có test suite cho auth, ownership, schema hoặc serving parity.

Phần này là kiểm tra source và smoke checks được ghi riêng trong mục 9; chưa phải numerical audit toàn bộ Phase 1 hoặc trusted-baseline certification.

## 7. Luồng triển khai backlog tuần 1–3

Đây là phân rã deliverables và dependency để review phạm vi. Implementation plan chi tiết được lập sau khi chốt thiết kế; thứ tự dưới đây không tự thay đổi deadline trong Sheet.

### A. Foundation và compatibility evidence

Tạo workspace apps/services/packages/infra theo cấu trúc trên, chỉ khởi tạo service đang cần. Pin Python 3.12, FastAPI/Pydantic và toolchain frontend theo phiên bản kiểm chứng khi triển khai. Mỗi service có health/readiness, settings, package/image boundary và test entry point. Thêm contract HTTP/events, Compose dev và CI theo changed paths. Không ghi nhận staging đã chạy nếu mới có config.

Trước extraction: ghi code/data/config/environment manifest và golden one-step fixtures cho legacy behavior. Không đóng băng dữ liệu bằng cách chỉ gắn Git tag vì cache/output có thể chưa được Git quản lý.

**Nghiệm thu:** service build/start độc lập; core wheel import ngoài repo root; CI kiểm tra consumer khi contracts/core đổi; CLI Phase 1 và fixtures vẫn chạy.

### B. Identity/BFF và Portfolio ownership

Next.js BFF dùng Keycloak OIDC Authorization Code + PKCE; browser giữ opaque session cookie HttpOnly, access/refresh tokens ở server-side session store. Có state/nonce/PKCE validation, cookie/CSRF policy và logout/session invalidation. Domain services validate token signature/JWKS, issuer/audience/expiry/scopes và owner; owner không lấy từ body do client gửi. Roles theo ma trận mục 14.2 của đặc tả: Investor, Researcher, Data operator, Model reviewer, System admin. Một người có thể được gán nhiều role; System admin không mặc nhiên được đọc mọi dữ liệu riêng hay promote model.

“Register/login/refresh/logout” trong Sheet là user-facing capability; thực thi bằng flow Identity/BFF đã chốt, không xây password database/song song JWT issuer mới. Tạo migrations theo use case và DB owner, không tạo toàn bộ schema tương lai trong một database.

**Nghiệm thu:** đăng nhập/logout thật với dev Identity; user A không đọc/ghi portfolio/job của B; Investor không chạy ingestion/promotion; Data operator chạy ingestion, Researcher train theo quota, Model reviewer promote theo scope; System admin không mặc nhiên có quyền dữ liệu riêng; mất session store phải fail closed. Chỉ bật các endpoint khi use case tương ứng được triển khai, nhưng giữ ma trận quyền thống nhất từ đầu. Nguồn endpoint OIDC: [Keycloak](https://www.keycloak.org/securing-apps/oidc-layers).

### C. Market Data ingestion

Tách provider fetch khỏi CSV write; có import adapter đọc dữ liệu hiện tại làm dataset khởi đầu. Ghi prices/revisions, publication/freshness và immutable snapshot manifest. Schedule theo asset/provider, không theo train/test split nghiên cứu. Job/outbox cùng transaction, inbox dedupe trước ack; bounded retry và trạng thái lỗi quan sát được.

**Nghiệm thu:** import/crawl cùng input hai lần không nhân đôi observation; stock/fund/gold units xác định; data thiếu/stale không xuất snapshot READY giả; worker restart không mất job. Kiểm tra provider live riêng, không đánh đồng fixture test với crawl thực tế.

### D. Core, Quant và recommendation API thuộc Portfolio

Trích xuất shared DecisionEngine đủ selection/views/BL/constraints theo contract; Quant/Research cùng dùng core version. Serving chỉ inference với model đã duyệt và input đã pin. Portfolio tạo request, publish command, Quant lưu run/result, Portfolio lưu recommendation; phân quyền ở mỗi owner. API trả `202` với job/status reference, theo dõi kết quả qua status API ở đợt này.

Public façade qua BFF: `POST /api/v1/portfolios/{id}/recommendations` và `GET /api/v1/recommendations/{id}` route tới Portfolio. Không tạo `services/allocation/`. Nếu dùng tên `AllocationService` cho một application class nội bộ thì class đó thuộc Portfolio và chỉ điều phối use case, không trở thành service deploy độc lập hay owner của mọi bảng liên quan.

Luồng tối thiểu: **login → portfolio → immutable snapshot/model → allocation job → Quant result → persisted recommendation**. Accept target/ledger/dashboard hoàn chỉnh theo các mốc sau; không thêm giao dịch khi API chỉ tạo đề xuất.

**Parity:** so một decision trên cùng ordered assets, cutoff, history/window, model state, forecast/selection state, seed, config và solver version. So weights cùng diagnostics/P/Q và constraints theo tolerance định nghĩa trong fixture. Không so một allocation với NAV cả giai đoạn. Refactor legacy parity và validation app-v2 là hai báo cáo riêng; nếu sửa lỗi khiến output đổi thì ghi discrepancy và version thay đổi.

**Nghiệm thu:** retry/idempotency không tạo nhiều canonical recommendation; infeasible/stale/model chưa READY bị từ chối rõ; result có data/model/core/policy version và input hash; parity fixtures cho `ranking_absolute` đạt trước khi đánh dấu backlog tuần 3 hoàn tất.

### E. Model registry và scheduled training

ML Platform sở hữu train jobs, immutable bundle manifests và production alias. Dùng JSON/UBJ cho XGBoost, scaler/feature metadata có schema/checksum; giữ reader legacy riêng khi cần tái lập. Lịch 10 phiên retrain và 20 phiên reselection theo đặc tả là baseline cấu hình, không cron theo số ngày lịch. Candidate validation/promotion tách khỏi việc job train chạy xong; Quant chỉ resolve bundle compatible và READY.

**Nghiệm thu:** train job có status/retry/lease; retrigger cùng kỳ không chạy trùng logical job; reload model giữ prediction trong tolerance; candidate lỗi không đổi alias; run đang xử lý giữ bundle đã pin khi có promotion mới. JSON/UBJ và pickle có mức bảo đảm tương thích khác nhau theo [XGBoost Model IO](https://xgboost.readthedocs.io/en/stable/tutorials/saving_model.html).

Heavy jobs chạy worker riêng, không gắn vào lifetime HTTP process. [FastAPI Background Tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/) nêu công cụ worker như Celery phù hợp hơn với tính toán nặng qua nhiều process/server.

## 8. Quản lý migration và kiểm chứng

1. **Bổ sung trước:** thêm workspace và contracts, giữ entry points/data cũ. Không rename hoặc chuyển toàn bộ repo trong bước init.
2. **Extract từng cụm:** fixtures → config explicit → package → consumer tests. Không maintain hai bản thuật toán được chỉnh độc lập; facade gọi implementation canonical sau parity.
3. **Tách semantics:** `legacy-v1` là behavior phục vụ tái lập; `app-v2` chứa thay đổi đã có acceptance evidence. Những kiểm tra khoa học còn mở theo trusted-baseline timeline được ghi rõ, không tự sửa hết trong PR đổi thư mục.
4. **Chuyển CLI/research sau:** chỉ move sang `research/phase1/` khi đường dẫn đã explicit và có hướng dẫn lệnh thay thế/compatibility. Datasets/manuscript/history không phải điều kiện bắt buộc phải move cùng.
5. **Release theo owner:** contracts có compatibility check; DB migrations thuộc service; consumer chọn core version. Git tag/package version riêng khi tạo release; không gộp release mọi service.

Kiểm thử theo rủi ro: unit numerical/validation, wheel isolation, PostgreSQL migrations, OIDC ownership, worker retry/dedupe, integration allocation và model reload parity. Load/HA/restore/UAT theo mốc hardening; không dùng smoke test để tuyên bố production-ready.

## 9. Kết quả của lần chuẩn bị này

- Đã đọc Sheet hiện tại và phân biệt với bản timeline đề xuất lưu local.
- Đã đối chiếu source paths/imports, numerical dispatch, model serialization và crawler với đặc tả.
- `venv/bin/python -m backtest --help` exit 0, xác nhận CLI import và entry point hoạt động. Có cảnh báo fontconfig cache không ghi được trong sandbox; không làm lệnh thất bại.
- Probe với 90 dòng giá synthetic và mode mặc định `ranking_absolute` xác nhận `generate_dynamic_views()` trả `(None, None, None, [])`, exit 0. Đây là reproduction của nhánh không được dispatch, không phải full backtest/API parity test.
- Đã kiểm tra local Markdown links, code fences và placeholders của tài liệu; `git diff --check` và kiểm tra diff các thư mục numerical/crawler/config không có thay đổi tracked.
- Đã lập đề xuất repository, mapping migration, backlog tuần 1–3 và acceptance criteria trong tài liệu này.
- Chưa tạo application service, di chuyển source, sửa thuật toán, tạo DB, chạy train/crawl, commit/push hoặc triển khai cloud trong lần chuẩn bị này.

Thiết kế cần chốt: **monorepo hiện tại, bổ sung workspace trước, extract core theo fixtures; giữ Phase 1 chạy được trong quá trình migration**. Đây là điểm quyết định trước khi lập implementation plan và sửa application code.
