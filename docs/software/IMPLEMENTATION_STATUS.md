# Tiến độ software app

## Chat LLM phương án B — 05/11/2026

Đã nối OpenAI Responses thật với `gpt-6-luna`, reasoning none, strict schemas,
context ngắn và consent theo conversation (mặc định tắt). LLM chỉ trả intent/
strategy/reference và fact plan; backend giữ quyền tools, canonical facts,
confirmation và explicit accept UI. Không phát prose tài chính chưa kiểm chứng.
Worker có quota ngày UTC, invocation ledger/fencing/dedupe, actual usage và
fallback; provider key chỉ ở worker qua overlay opt-in, không đổi Auto Recharge.

Live browser đã đi qua PKCE → bật consent → thiếu strategy/hỏi lại → MVO follow-up
→ confirmation → Portfolio/RabbitMQ/Quant thật → giải thích → hỏi tiếp đúng cùng
recommendation → tắt consent → explicit accept UI. Tổng **5 OpenAI calls**, actual
usage **1786 input + 196 output tokens**; ước tính bảo thủ **$0.00032125**, không
phải số tiền hóa đơn. Không HTTP interception hay tạo giả SQL results. Market
được refresh KBS đến 04/11/2026, schedule tắt; không dùng dữ liệu hết hạn/DEMO.

Gate đầu dừng ở phép cộng usage sau khi đã accept: message của lượt hỏi tiếp
chỉ mang explanation metadata, thiếu interpretation usage trong phép cộng.
Đã sửa bằng owner-scoped `provider_usage` trên job API và regression RED→GREEN.
Để tiết kiệm, đối chiếu lại chính jobs/requests/ledger đã lưu bằng đọc SQL và
canonical HTTP, không sửa business rows hoặc gọi model lần nữa. Browser receipt
verification sau restart Chat API/worker/Web đạt; replay giữ cùng IDs/hashes/
history và ledger vẫn 5 calls. Gate cap thật ở mức đã dùng 5 trả TEMPLATE với
DAILY_BUDGET_EXHAUSTED, canonical facts giữ nguyên và không thêm invocation.
Fault injection HTTPS proxy loopback từ chối kết nối cũng trả
TEMPLATE trước khi tới OpenAI: ledger hiện 6 reservations, chỉ 5 có paid usage.
Proxy đã được gỡ; worker trở lại quota 20/ngày.

Offline: 539 Python/core + 1 skip ngoài phạm vi, 104 web tests, TypeScript,
Ruff, 11 contracts và production builds đạt tại mốc kiểm tra. Đã bổ sung thêm
PostgreSQL storage probe cho quota LLM đồng thời (callbacks injected, không gọi
provider); ba Chat PostgreSQL concurrency probes đạt. Read-only review tìm lỗi
cách viết “BL + ML”; đã sửa với regression test. Explanation planner nhận câu hỏi đã redaction để chọn
sections đúng trọng tâm. Bổ sung owner grant/account
preflight trước interpretation, nên revoke/disable chặn cả lượt gửi context ra LLM.
Xem
[setup/giới hạn credits](SETUP_AND_API_TESTING.md#openai-dialogue--phương-án-b-05112026).

Giới hạn: chưa đánh giá rộng chất lượng hội thoại tiếng Việt/full RAG; explanation
vẫn là finite fact plan do backend render; model alias chưa có dated snapshot;
redaction không bảo đảm loại mọi PII tự do; số tiền chỉ ước tính. Full paid lifecycle
không chạy lại sau sửa phép cộng usage; kiểm chứng lại trên chính receipt cũ để
không tốn thêm credits. Không tuyên bố production/HA hoặc GitHub CI đã chạy.

## Chat MVP — kiểm chứng local 04/11/2026

Đã hiện thực vertical slice Chat trên API thật, kiểm thử backend trước frontend:

- `chat_db`, migration/API riêng (Swagger port 8005), leased SQL worker, conversations,
  messages, jobs, event sequence và tool audit. HTTP 202 trả resource references;
  client_message_id/key/body conflict, quota theo owner, retry/deadline, fencing
  và dependency checkpoint chống duplicate khi restart.
- Portfolio cấp/kiểm tra delegation 5 phút, binding user/service/conversation/job/
  resource/tool, expiry/revoke và account/role hiện hành qua Identity. Chỉ lượt
  structured-confirmed được cấp request_allocation; không có accept/trade/promote
  trong tools. Market cung cấp observations/source/timestamps từ database owner.
- Canonical recommendation/facts/versions được refetch; provider schema chỉ chọn
  fact-template sections. Deadline tổng 5 giây, body budgets, durable one-call/job;
  unconfigured/outage/unverified output dùng template, giữ nguyên quantitative
  result. Template v2 dùng câu tiếng Việt, hashes trong phần đối chiếu.
- BFF relay SSE có Last-Event-ID/header isolation, session expiry, backpressure;
  events bền vững 7 ngày và reset khi quá retention. Browser có list/history paging,
  review cards, job progress, canonical cards, explicit retry/reauthorize, deep
  links/reload và mở proposal để accept rõ ràng bằng UI hiện có.

Bằng chứng cuối: **508 Python/core tests passed, 1 skipped** (opt-in có sẵn ngoài
Chat); hai storage concurrency tests Chat chạy trên PostgreSQL thật. **102 web
tests**, TypeScript, Ruff, production Docker build và 11 contracts đạt. DB/broker/
Identity boundaries và PostgreSQL migration/metadata check đạt. Read-only review
phát hiện các race/recovery/budget/SSE defects; đã sửa và có regression tests.

Real API gate normal/outage/restart đạt trên Keycloak, PostgreSQL, RabbitMQ,
Portfolio/Quant thực; snapshot KBS FPT/MWG/VCB đến 03/11/2026, không HTTP interception
hoặc tạo giả SQL results. Gate authorization riêng **47 probes / 305.34s** đạt,
bao gồm hết hạn thực sau 5 phút, revoke, account disable/restore, sai binding/tool,
stale portfolio/risk và rejected expired real inputs. Bob đã được khôi phục;
không tự accept từ API harness.

Browser thật đạt 4 cases thường (PKCE→conversation→confirmation→allocation→verified
facts/template→accept UI; expiry/explicit retry; hai races), 1 case provider outage,
và 2 receipt cases sau restart. Có nhận accepted SSE event trong browser khi worker
đang dừng, lưu cursor, offline và tiếp tục cùng job sau restart. Race tests chỉ
làm chậm network response thật qua Chromium, không thay response. Desktop/390px
đã kiểm tra và xem screenshot; Figma F01/F02/F03 trong đúng project 24.10.2026 và
ui-ux-pro-max; giữ shell/tokens/assets/AllocationView hiện có.

Receipts không token ở `infra/local/.generated/chat-*-receipt.json`; báo cáo/ảnh
ở `output/playwright/sanitized/chat-*.json/png`, không vào Git. Sau restart 9 tiến
trình Chat/Web/Portfolio/Quant, IDs, input/facts/target hashes và lịch sử khớp.
Đã scan logs: không có configured secrets, bearer strings hoặc grant references;
installed Chat/Portfolio source hashes khớp workspace. Worker outage đã trở lại
cấu hình bình thường. Xem [API/worker](SETUP_AND_API_TESTING.md#chat-mvp-api-và-worker)
và [browser gate](../../apps/web/tests/browser/README.md#chat-mvp-real-stack-gates).

Trong triển khai, disk-full làm Docker treo. Theo yêu cầu người dùng, đã dọn
**13.61GB build cache +1.758GB dangling images**; giữ containers/volumes/secrets/
data, phục hồi Docker và kiểm chứng lại. Lịch KBS thử nghiệm đang tắt. Giữ nguyên
`extensions_C_v1/`, nghiên cứu/core và dữ liệu cũ. Chưa commit/push.
Sau build cuối, dọn thêm 3.325 GB build cache + 699.5 MB dangling images;
11 volumes giữ nguyên, ổ đĩa còn 8.9 GiB. Health và cả hai API receipts vẫn đạt.

Giới hạn: intent/tool allowlist deterministic; hosted provider dùng protocol
`fact-plan-v1`, chưa cấu hình provider thương mại/SDK riêng. Chưa có full RAG/
Knowledge, Chat AMQP continuation consumer (worker reconcile bằng owner API),
production HA/load/SLO certification; GitHub CI chưa chạy bản này. Market calendar
vẫn là observed VNINDEX sessions, không coi ingestion availability là historical
point-in-time proof. Đây là local MVP, không chứng nhận nghiên cứu/production.

## P1 — kiểm chứng local 27/10/2026

Đã bổ sung ba luồng và UI nối API thật:

- Data Refresh: schedule/job bền vững, chạy tay hoặc timer, KBS stock adapter cố
  định và raw/normalized SHA-256, kiểm tra toàn lô trước snapshot. Mỗi lần fetch
  đối chiếu toàn bộ khoảng lịch sử adjusted đã cấu hình; chỉ revision mới/thay
  đổi được thêm vào storage. Không ghép các adjustment vintage bằng fetch riêng
  cửa sổ overlap. Calendar là phiên VNINDEX quan sát được, chưa được xác nhận độc
  lập; ingestion availability không chứng minh historical point-in-time data.
- ML Operations MVP: `ml_db`, migrator/API/worker riêng (Swagger port 8004),
  snapshot/hash-pinned training được kích hoạt thủ công, candidate và review
  APPROVED/REJECTED có reason/If-Match/idempotency. HTTP chỉ enqueue; worker không
  tự duyệt. Publication nhận `approved_model_id`, resolve manifest tin cậy ở server
  và chờ artifact đã materialize. ML tạm dùng lại Quant training/feature helpers;
  chưa hoàn tất việc tách thư viện dùng chung, không thay core/risk mapping.
- Risk reassessment: preview thuần đọc, confirmation có If-Match/key, revision UUID
  bất biến và lịch sử phân trang. Profile mới tăng version danh mục; proposal cũ
  không được accept. Target đã chấp nhận giữ allocation/policy cũ; queued input/hash
  legacy không bị sửa và lịch sử chưa biết không bị bịa/backfill.

BFF giữ session/CSRF và allowlist upstream theo Portfolio/Market/Quant/ML;
operator/reviewer/investor có role gates riêng. Chỉ refresh/ML/publication workers
được ghi artifact thuộc owner; các API và optimizer đọc read-only. Local upgrade
bổ sung DB/scopes/clients/migrations, giữ secrets và volumes hiện có.

Đã thêm gate P1 nguồn thật và receipt sau restart, gồm manual refresh + actual
scheduler tick, training/reviewer/publication và risk → BL_ML → accepted target.
**Kiểm chứng mới: 451 Python/core tests, 84 web tests**, Ruff, TypeScript,
production build và 10 contracts ổn định. Một PostgreSQL concurrency test opt-in
skip trong gate mặc định; probe fencing trên PostgreSQL thật và DB/broker/Identity
boundaries chạy riêng đạt. Sáu browser gates đạt: P1, P0 và Market lifecycle cùng
đối chiếu chính receipt sau restart. P1 dùng KBS FPT/MWG/VCB đến 26/10/2026;
không mock HTTP hoặc tạo giả kết quả SQL. Đã restart 14 tiến trình ứng dụng, giữ
nguyên model/snapshot/input hash, quyết định review, risk UUID và cả allocation
cũ/mới. Lịch tự động thử nghiệm đã tắt, replay không bật lại hoặc tạo thêm job.

Model UI hiển thị model được chọn theo từng universe từ Quant readiness, checksum
và tương thích BL_ML; trạng thái hết hạn tự cập nhật trên trang đang mở. UI dùng
ui-ux-pro-max và các khung Figma I01/I02/I07–I10/I34/I35; hồ sơ rủi ro tái sử dụng
wizard/review hiện có. Kiểm tra desktop và 390px đạt; không coi các trạng thái
prototype VALIDATED/PRODUCTION là lifecycle đã hiện thực trong MVP. GitHub CI
chưa chạy trên bản thay đổi này. Báo cáo đã lọc ở
`output/playwright/sanitized/p1-lifecycle.json` và `p1-persistence.json`, receipt
không token ở `infra/local/.generated/p1-browser-receipt.json`.
Xem [cách chạy](../../apps/web/tests/browser/README.md#p1-real-provider-model-and-risk-gate)
và [setup/API](SETUP_AND_API_TESTING.md). Chưa tuyên bố CI GitHub, production
certification hoặc đầy đủ mọi lifecycle/screen tương lai trong Figma.

Các mục bên dưới giữ nguyên bằng chứng và giới hạn tại từng mốc lịch sử.

## Market Data Operations — cập nhật 27/10/2026

Đã bổ sung registry SQL bất biến từ trusted CSV inventory, đăng ký có
Idempotency-Key, lịch sử ingestion phân trang và báo cáo chất lượng
PASS/QUARANTINED/NOT_CHECKED. Lô dữ liệu được kiểm tra trước khi ghi giá;
snapshot ghim revision/hash và kiểm tra chất lượng các revision được chọn.

Data operator có thể enqueue/list/get publication của mình với snapshot ID/hash
và universe cố định. API chỉ ghi SQL queue; worker riêng phát hành bundle và retry
lỗi tạm thời. Frontend `/#market` nối đầy đủ nguồn → ingestion → chất lượng →
snapshot → phát hành, với role gate, CSRF, phân trang và deep links.

Kiểm chứng: **385 Python/core tests / 64 web tests**, Ruff, TypeScript,
production build, 9 contracts và DB/broker/Identity boundaries. Một PostgreSQL
concurrency test opt-in được chạy riêng và đạt; gate mặc định skip test này.
Năm browser gates trên backend thật đạt: Market lifecycle, outage/retry,
Market restart persistence, P0 lifecycle và P0 restart persistence. Luồng giá thật
FPT/HPG/VCB đi đến accepted target; retry giữ đúng job/hash và lịch sử giữ nguyên
sau restart. CI GitHub chưa chạy.

Giới hạn: trusted CSV/import; lịch phiên chỉ kiểm đủ khi nguồn có
`expected_sessions`. Metadata thiếu basis/known-at có cảnh báo, chưa được coi là
đã xác minh. UI bám Figma I01; I02–I06 chưa đối chiếu chi tiết do hạn mức đọc MCP.
Xem [hướng dẫn UI](../../apps/web/README.md) và [vận hành local](../../infra/local/README.md).

## P0 — cập nhật 25/10/2026

Đã bổ sung readiness dữ liệu/model có mã nguyên nhân và thời hạn; publication
jobs bền vững với lease fencing, retry/idempotency, recovery và lịch cấu hình.
Worker dùng Quant DB và Market snapshot-reader; Quant API/optimizer giữ artifact
mount read-only. Lịch mặc định tắt; không tự crawl, train hoặc duyệt model.

UI theo design hiện có hỗ trợ sửa tên/vốn có If-Match/conflict recovery, tìm/lọc/
sắp xếp/phân trang từ server, lịch sử target, so sánh proposal và deep link/reload.
Phiên hết hạn chỉ lưu đích điều hướng, không tự gửi lại mutation.

Kiểm chứng: **336 Python/core tests / 60 web tests**, Ruff, typecheck, build và
contracts đạt. Browser thật đã qua PKCE → onboarding → EW/target → history → sửa
đồng thời/412 → MVO/compare → expiry → 401/đăng nhập lại; sau restart giữ cùng
target/proposal/allocation hash. Job publish từ snapshot Market giá thật và model
được duyệt đã SUCCEEDED, retry cùng key và đọc lại sau restart giữ cùng kết quả.
Workflow đã nối browser lifecycle/persistence với Playwright pin và artifacts
đã lọc; chưa chạy workflow này trên GitHub. Xem [browser gate](../../apps/web/tests/browser/README.md)
và [publication worker](../../infra/local/README.md#durable-operator-publication).

## UI — cập nhật 25/10/2026

UI trên cổng 3000 hỗ trợ onboarding có review, universe thật/minh họa, danh sách
danh mục, biểu đồ/bảng phân bổ, accepted target và dashboard. Luồng browser thật
đã kiểm chứng OIDC/PKCE → tạo danh mục → MVO → lưu target → reload/restart.
Kiểm tra offline: **248 Python tests / 52 web tests**, lint, typecheck và build.
Giữ các smoke scripts để chạy lại; ảnh chụp và receipts local không lưu trong Git.

## Market → Quant — cập nhật 24/10/2026

Đã nối snapshot giá thật FPT/VCB/HPG đến features, numerical bundle, approved
XGBoost, BL_ML và accepted target trên stack local. Dữ liệu đến **23/10/2026**;
serving/core cùng bước sai số weights < `1e-10`. UI chọn universe từ catalog và
phân biệt real/demo. **248 Python / 51 web tests** cùng lint/typecheck/build,
contracts/migrations, live boundary probes, restart receipts và browser thật đạt.
[Chi tiết, cách chạy và giới hạn](MARKET_QUANT_BRIDGE.md).

Các cập nhật 23/10 bên dưới là lịch sử trước khi nối bridge.


## Tuần 6–7 — cập nhật 23/10/2026

G2 local đã kiểm chứng qua browser thật: OIDC → wizard → portfolio/policy →
MVO proposal → accept target → dashboard. Native XGBoost approved manifest → BL_ML
qua RabbitMQ đã đạt same-step parity, max |Δweight| = 0 trên synthetic inputs.
MVO/Market/target/ML receipts giữ nguyên sau restart. **219 Python tests / 49 web
tests**, typecheck/build/lint/contracts/migrations và live boundary probes đạt.

Hợp đồng và cách dùng: [WEEKS_6_7.md](WEEKS_6_7.md).
Chưa hoàn tất full ML Platform, Market→features, representative selection, ledger,
Chat/RAG hoặc nghiên cứu selection/ablation. Các mốc bên dưới là lịch sử.

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


### Chat merge verification — 07/11/2026

- Fresh local verification: 540 Python/core tests passed with all three real
  PostgreSQL concurrency probes enabled; one unrelated opt-in test skipped.
  Web: 134 tests, TypeScript and production build passed. Ruff, 11 contract
  exports, Compose configuration and real DB/broker/Identity boundaries passed.
- Real Chat API lifecycle and four browser journeys passed: PKCE/confirmation/
  MVO/result/explicit accept/reconnect, session reauthorization, late refresh and
  late conversation creation. After restarting Chat/Portfolio/Quant processes,
  API and browser replay verified the same history, facts, input hashes and target.
- Initial browser attempts correctly failed on expired prepared real inputs.
  Renewed the existing immutable real snapshot through the standard publisher
  with freshness validation, then regenerated the API receipt before browser use.
  No source prices or stored expiration fields were edited.
- Fixed CSV metadata validation mixing host-local dates with the UTC observation
  contract; a regression reproduces local midnight before UTC midnight.
  Refresh rejection tests now use the Vietnamese business cutoff.
- CI exposed a setup test relying on the developer's existing venv executable;
  its fixture now selects the current runner's Python explicitly.
- Paid LLM, provider-outage and five-minute live grant-expiry gates were not
  repeated in this merge run. Prior dated evidence above remains historical.
  Knowledge RAG and untracked research extensions are outside this PR.
