# Phục vụ Phase 1 trên stack local

**Cập nhật 18/11/2026:** selected snapshot mới dùng `user-selection-live-nav-v2`,
NAV đã thu thập/xác minh dùng cho live không chờ thêm 5 phiên, freshness vẫn
7 ngày từ ngày NAV. MVO backend thật và cùng receipt sau restart đã đạt;
xem [status](IMPLEMENTATION_STATUS.md#nav-live-v2--18112026) và
[runbook](SETUP_AND_API_TESTING.md#nav-live-v2--18112026).
Sau đó model v5 epoch16/11 đã được train/review qua pipeline hiện tại;
native BL_ML/K5 trên10candidate và cùng receipt sau restart cũng đạt.
Model, validation/usage, bundle và bằng chứng hiện hành ở đầu
[IMPLEMENTATION_STATUS](IMPLEMENTATION_STATUS.md).
Các mốc buffer/checkpoint bên dưới tiếp tục mô tả baseline và selected v1;
không sửa artifact, publication hay kết quả cũ.

`VN_EQUITY_PHASE1` dùng thứ tự FPT, MWG, VCB. Manifest v3 ghim model offline,
15 booster UBJ, scaler từng mã và kiểm tra validation theo thời gian. Training
job từ snapshot vẫn tạo manifest v2 qua luồng cũ.

## Fit và đăng ký

1. Kiểm tra registry, snapshot và readiness trên project
   `portfolio-auth-demo`. Lấy lịch sử KBS qua adapter `KbsProvider` cho
   `VNINDEX`, `FPT`, `MWG` và `VCB`, từ 01/01/2020 đến
   `completed_cutoff`. Lưu raw JSON dưới tên `<SYMBOL>.json`.
2. Từ root repo, dùng môi trường nghiên cứu đã có để fit một lần.

   ```sh
   venv/bin/python -B scripts/fit_phase1_local.py --kbs-dir /path/to/kbs --output /path/to/new-run
   ```

   Script đối chiếu input và source với hash của lượt baseline, xác minh
   từng phiên giá giao nhau sau đổi đơn vị, rồi fit bằng ensemble đã đóng
   băng. Run directory giữ dữ liệu probe, validation và đối chiếu feature,
   từng booster, confidence, P/Q. Kiểm tra `run.json` có `status=succeeded`.
3. Build và cập nhật các service thay đổi. Chạy migration ML trước khi import.

   ```sh
   dc() { docker compose -p portfolio-auth-demo --env-file infra/local/.generated/.env -f infra/local/compose.yaml "$@"; }
   dc build market-migrate ml-migrate quant-migrate web
   dc run --rm --no-deps ml-migrate
   dc up -d --no-deps --wait market-api market-refresh market-dispatch market-consume \
     ml-api ml-worker quant-api quant-publication quant-consume quant-dispatch web
   ```

4. Đặt thư mục `phase1-<MODEL_ID>` từ kết quả fit vào
   `infra/local/.generated/ml-models/`. Manifest và 15 booster giữ nguyên
   byte. Dùng `manifest_sha256` từ `run.json`.

   ```sh
   dc exec -T ml-worker python -m ml_platform.import_phase1 \
     --manifest "phase1-${MODEL_ID}/manifest.json" --sha256 "${MANIFEST_SHA256}"
   ```

   Import cùng pin trả cùng model ID. Reviewer mở
   `/#model-review?model=<MODEL_ID>` và ghi lý do. Quyết định dùng phiên bản
   registry hiện hành và idempotency key. Chờ `artifact_ready=true`.

## Snapshot, publication và nghiệm thu

- Dùng `data-operator` chạy manual KBS refresh cho FPT, MWG, VCB với ngày
  bắt đầu **14/01/2020** và freshness **7 ngày**. Kiểm tra snapshot `READY`
  và cả ba quality reports `PASS`. Nếu dùng test browser, lưu response
  `GET /api/v1/market/snapshots/{id}` dưới khóa `snapshot` trong
  `infra/local/.generated/phase1-snapshot-receipt.json`.
- Mở `/#market-publications?snapshot=<SNAPSHOT_ID>&model=<MODEL_ID>` và phát
  hành `VN_EQUITY_PHASE1`. Quant kiểm tra đúng lịch sử khởi tạo, giá KBS
  adjusted VND/cổ phiếu và hash phần giao đến cutoff. Feature dùng phiên
  liền trước phiên dữ liệu mới nhất. Option B dùng 20 lợi suất qua phiên
  mới nhất và quy đổi view về lợi nhuận ngày. Snapshot và model phải khả
  dụng tại thời điểm quyết định.
- Đăng nhập investor, tạo danh mục `VN_EQUITY_PHASE1`, chọn BL + ML và
  bỏ chọn EW dự phòng. Browser gate chạy luôn review, publication và proposal
  trên tài khoản local. Candidate cần ở trạng thái `CANDIDATE` lúc bắt đầu.

  ```sh
  cd apps/web
  E2E_DISPOSABLE_STACK=1 PHASE1_MODEL_ID="$MODEL_ID" npx playwright test phase1-offline.e2e.ts
  # Sau khi restart stack và kiểm tra health, mở lại đúng proposal trong receipt.
  E2E_DISPOSABLE_STACK=1 PHASE1_VERIFY_RECEIPT=1 npx playwright test phase1-offline.e2e.ts
  ```

## Build lại riêng Quant từ Dockerfile Compose chuẩn

Chạy từ root repo. Service `quant-migrate` khai báo build context của repo và
Dockerfile `services/quant-serving/Dockerfile`, tạo image
`portfolio-software-quant:local` dùng chung cho bốn service Quant.

```sh
dc() { docker compose -p portfolio-auth-demo --env-file infra/local/.generated/.env -f infra/local/compose.yaml "$@"; }
dc config --quiet
dc build quant-migrate
dc up -d --no-deps --no-build --wait --wait-timeout 120 \
  quant-api quant-publication quant-consume quant-dispatch
docker image inspect portfolio-software-quant:local --format '{{.Id}}'
docker inspect $(dc ps -q quant-api quant-publication quant-consume quant-dispatch) \
  --format '{{.Name}} {{.Image}}'

cd apps/web
E2E_DISPOSABLE_STACK=1 PHASE1_VERIFY_RECEIPT=1 \
  npx playwright test phase1-offline.e2e.ts --grep 'reopens the same proposal'
```

## Kết quả kiểm chứng ngày 11/11/2026

Build Compose chuẩn thành công và cả bốn container Quant chạy image
`sha256:567ff3cde25272d263b004613765dad3eb6bad01232b4fe5ae34a8a55d6366d2`.
Sau khi thay image, cả 23 service đang chạy và các health check đều đạt.
API readiness trả `VN_EQUITY_PHASE1` ở trạng thái `READY`, với
`BL_ML.available=true` và `reason_code=READY`.

| Đối tượng đã đối chiếu | Giá trị |
| --- | --- |
| Model đã duyệt | `47f3981b-268f-44c7-b508-c5458ee90331` |
| Snapshot | `aab80672-8a3a-4861-8033-216591466253` |
| Model manifest SHA-256 | `9150cfa7fb0d67d62c20f215443f28b4c9442ebe35538a14506763dd800685a8` |
| Bundle SHA-256 | `8be863fb0c6c6facd2288db1c08bb2d2eb2608f894d72e32c10b916088adacea` |
| Danh mục | `be72d911-c191-4156-b3a0-18de0bac86a2` |
| Job và đề xuất | `ec78d461-8eef-4242-a7b1-a303e8f43cf6` |

Playwright đăng nhập investor và mở lại đúng đề xuất đã lưu. Job vẫn
`SUCCEEDED`, giao diện hiển thị BL + ML và toàn bộ response của đề xuất
khớp receipt trước khi build lại. Publication vẫn `SUCCEEDED`, model vẫn
`APPROVED` và `artifact_ready=true`. Đã đối chiếu hash snapshot qua Market
API, checksum của 21 tệp tài khoản, receipt và model, cùng danh sách volume
trước và sau khi thay image. Tất cả đều khớp.

Bằng chứng nằm trong [receipt của đề xuất](../../infra/local/.generated/phase1-browser-receipt.json)
và [kết quả Playwright persistence](../../output/playwright/sanitized/phase1-offline-persistence.json).
Bundle của lần kiểm chứng có hạn đến 23:24:03 ngày 11/11/2026, giờ Việt Nam.

Phase 1 dùng giá điều chỉnh theo nhà cung cấp và lịch VNINDEX quan sát.
Timestamps phục vụ dựa trên ingestion. Validation theo lợi nhuận đơn giản
năm phiên và kết quả phục vụ kiểm chứng luồng kỹ thuật.
## Full universe: K5 động + GOLD + VFF

Luồng mới dùng `VN_PHASE1_FULL`, snapshot Market schema 2 và model manifest
schema 4. Schema 1–3 và đề xuất lịch sử giữ nguyên. Thứ tự đầu ra gồm 30 cổ
phiếu từ `assets_1.json`, GOLD và VFF; BL_ML chỉ tối ưu K5 đang chọn cộng
GOLD/VFF, rồi map 25 cổ phiếu còn lại về đúng 0.

K5 reselect mỗi 20 phiên, model refit mỗi 10 phiên và checkpoint mỗi 5 phiên.
Các con trỏ được tính từ lịch VNINDEX đã ghim, rồi lưu epoch, selection hash,
training equity hash và active assets trong manifest/bundle/job. Không cần
bảng schedule mutable riêng. Khi selection đổi trước refit, chỉ phần giao
K5 hiện tại và năm mã có model phát ML views. Manifest có 25 UBJ, seed 42–46,
scaler từng mã, tám feature, best_iteration và nhãn năm phiên kết thúc tại
`fit_index−6`. Thời điểm fit/ingestion thực tế được giữ riêng với thời điểm
khả dụng lịch sử theo policy; không chứng nhận historical first publication.

Freshness full universe cố định **7 ngày lịch**, tính trên observation thực
sự đủ điều kiện ở checkpoint. GOLD dùng từ ngày kế tiếp; VFF dùng sau năm
phiên quan sát, hoặc sau metadata provider nếu muộn hơn. Có NAV nguồn mới
không đồng nghĩa observation đó đã được phép dùng. Publisher và worker dùng
chung gate, tính lại tuổi tại thời điểm sử dụng. `VFF_STALE`/`GOLD_STALE`
chặn cả EW dự phòng, trả ngày observation, tuổi và ngưỡng 7. Publication có
thể lưu bundle chẩn đoán bị chặn; `SUCCEEDED` của publication không đồng
nghĩa BL_ML READY. Bundle này không được đưa vào danh sách onboarding sẵn sàng.

Dữ liệu cổ phiếu thiếu được giữ nguyên ở raw revisions. Chỉ 37 phiên thiếu
lịch sử đã đối chiếu SHA với raw baseline của ACB/DGC/GVR/LPB/SHB/VIB được
carry theo frozen `utils/data_loader.py`; ledger giữ observation/revision gốc
và `carry_basis`. Khoảng thiếu mới bị quarantine, không sinh giá quan sát giả.

Build và thay service bằng Dockerfile Compose chuẩn, giữ nguyên volume:

```sh
docker compose --env-file infra/local/.generated/.env \
  -f infra/local/compose.yaml -p portfolio-auth-demo \
  build market-migrate quant-migrate ml-migrate portfolio-migrate web

docker compose --env-file infra/local/.generated/.env \
  -f infra/local/compose.yaml -p portfolio-auth-demo up -d --no-deps \
  market-api market-consume market-dispatch market-refresh ml-api ml-worker \
  quant-api quant-publication quant-dispatch quant-consume \
  portfolio-api portfolio-dispatch portfolio-consume web
```

Stage `assets_1.json` và `gold_archive_daily.csv` từ baseline vào
`.generated/datasets/refresh/full-phase1`, với `seed.json` chứa hai pin trong
`tasks/plan.md`. Refresh đầy đủ là lệnh operator có pacing, bounded requests,
raw hashes và commit nguyên batch sau quality cho đủ 32 tài sản:

```sh
docker compose --env-file infra/local/.generated/.env \
  -f infra/local/compose.yaml -p portfolio-auth-demo run --rm --no-deps \
  market-refresh python -m market_service.phase1_full \
  --seed /datasets/refresh/full-phase1/seed.json \
  --directory /datasets/refresh/full-phase1
```

Enqueue qua `POST /api/v1/ml/training-jobs` bằng data-operator, với
`snapshot_id`, `snapshot_hash`, `training_cutoff` đúng epoch do MixedPanel
trả về và Idempotency-Key cố định cho cùng ý định fit. Worker vẫn dùng lease,
fenced transaction và durable receipt hiện có. Snapshot stale vẫn có thể
được dùng để fit; việc đó không bỏ kiểm tra freshness của serving.
Reviewer duyệt tại `/#model-review?model=<UUID>` với reason, If-Match và
Idempotency-Key; chờ `artifact_ready=true`. Sau đó data-operator phát hành tại
`/#market-publications` với full snapshot/hash, universe và approved_model_id.

Các gate riêng, chạy từ `apps/web`:

```sh
E2E_DISPOSABLE_STACK=1 PHASE1_FULL_MODEL_ID=<UUID> npm run test:browser:phase1-full
E2E_DISPOSABLE_STACK=1 PHASE1_FULL_MODEL_ID=<UUID> npm run test:browser:phase1-full:stale
E2E_DISPOSABLE_STACK=1 npm run test:browser:phase1-full:persistence
```

Cờ disposable chỉ là bảo vệ gate localhost. Không reset tài khoản, DB hoặc
volume. Gate stale có model ID sẽ duyệt/phát hành qua browser, sau đó xác
nhận VFF_STALE và không tạo optimization job. Gate persistence full chỉ dùng
khi đã có receipt của một đề xuất full thực sự thành công.

Nội dung seed (không chứa credential):

```json
{
  "assets": {"file": "assets_1.json", "sha256": "17f8dcdc12e5bcc85636de55aace06f5ac9a438e35f130ee0718cf813f8f2a42"},
  "gold": {"file": "gold_archive_daily.csv", "sha256": "122a1100daac668883854040dc139c5c6a01131b8fa4a9bab93447a9f3e1dc73"}
}
```

Policy full giữ VFF là defensive, floor 15%, tổng non-defensive gồm GOLD tối
đa 70%, position cap không quá 50% và risk aversion lấy max giữa profile và
baseline regime (1,5 normal/stress; 5 crisis). Với ngân sách 100%, VFF thực tế
cần ít nhất 30%. Requested/effective constraints được pin riêng trong job và
proposal; thay profile hoặc K5 sau đó không sửa đề xuất lịch sử.


Lượt nguồn thật ngày 11/11/2026 tạo snapshot
`19f49fac-c911-41e2-9fae-7c8e1e59bf62`, SHA-256
`be50b30666e6218a396178804592a72ee048016096340aa914351b91a30e4c9d`.
Có 54.197 observation (51.053 equity, 2.538 GOLD, 606 VFF), 32 báo cáo PASS
và 41 raw source hashes đã kiểm tra. Hai lỗi chỉ phát hiện khi nối stack thật
đã được sửa: DATE binding ở PostgreSQL và tên provider Quant/Market chưa
khớp. Các transaction lỗi rollback; job lỗi được giữ trong audit.

Checkpoint của panel là **09/11/2026**, K5 **MBB, PLX, SAB, VHM, VJC**;
selection epoch 09/11, fit epoch 02/11, model selection epoch 12/10 và label
cutoff 23/10. VFF đủ điều kiện ở checkpoint là NAV **29/10**, policy time
05/11 lúc 18:00. Tuổi 13ngày tại 11/11 nên phải VFF_STALE. Nếu chỉ xét phiên
mới nhất 11/11 thì NAV 03/11 đủ điều kiện và cũng stale 8ngày. Nguồn raw có
NAV 10/11; không được đưa NAV đó ngược vào checkpoint 09/11. Ngày khả dụng
thực tế của ingestion là 11/11 và được lưu riêng. Sau00:00 ngày 12/11, tuổi
observation tăng tương ứng, còn checkpoint không tự đổi nếu chưa đến phiên
checkpoint tiếp theo.

Việc refresh không bảo đảm fullREADY hàng ngày khi đồng thời giữ checkpoint
5 phiên, bufferVFF5 phiên và ngưỡng 7 ngày. Positive acceptance chỉ có thể chạy
khi observation đủ điều kiện ở đúng checkpoint còn trong ngưỡng thực tế;
không backdate publication, đổi đồng hồ hay nới freshness để nghiệm thu.

Kiểm chứng offline hiện tại: **682 Python/core/software passed**, **5 opt-in
PostgreSQL tests skipped**; **140 Web passed**, typecheck và canonical Web
production build đạt. Fixtures kiểm tra 25 booster, best_iteration, feature,
confidence, P/Q, selector, regime, covariance, prior/posterior và constraints.
Pure-core có 107 tests, sai khác trọng số với frozen reference không quá 1e-10.


### Kết quả live sau restart ngày 12/11/2026

| Pin | Giá trị |
| --- | --- |
| Full model APPROVED, artifact_ready=true | `81449d2a-2e38-4e01-b695-cdac4a4bbb57` |
| Training job SUCCEEDED | `3bd0f94f-9655-4bb8-870d-d4b1520ba590` |
| Review | `08d0a3e6-60c8-4c36-960e-940e1feafe6f` |
| Snapshot READY/PASS | `19f49fac-c911-41e2-9fae-7c8e1e59bf62` |
| Publication SUCCEEDED | `1378f0b0-58ed-4c1a-8797-1527f827f7f9` |
| Model manifest SHA-256 | `978c63bfb07f257452922a02ef9757ac507b846e42e44018fed43e705cc48276` |
| Bundle SHA-256 | `73ffd3c1cfd389ac9008826fbdc333d9b22c71f0ab30bf45fe59f83c0c25b29e` |
| Full portfolio dùng để kiểm tra stale | `205e7623-f6ef-40d9-9196-38174af7101c` |
| BL_ML readiness full | `UNAVAILABLE / VFF_STALE` |
| Full optimization job / proposal | **Chưa tạo: bị chặn hợp lệ** |

Model được fit thực tế lúc `2026-11-11T17:05:00.525829Z` (00:05 ngày 12/11
GMT+7), giữ label cutoff 23/10. Retry cùng ý định training trả cùng job/model.
Reviewer đã duyệt trên browser với reason, If-Match và Idempotency-Key;
APPROVED không đến từ sửa SQL. Sau đó browser data-operator phát hành bằng
approved_model_id, snapshot và hash. Đã sửa thêm resolver để nhận đúng đường
dẫn artifact v4 `ml-models/<job UUID>/phase1-<model UUID>/<approved>.json`,
vẫn chặn sai UUID, sai model và thư mục lồng thêm.

Browser chạy ở **chế độ stale**: hai bài đạt, một bài persistence đề xuất full
được bỏ qua do chưa có đề xuất full. Nhánh đầu chỉ duyệt/phát hành và xác
nhận stale; tên test có BL_ML không được diễn giải là đã chạy optimizer live.
NAV VFF tại checkpoint 29/10 đã **14 ngày tuổi** khi kiểm chứng ngày 12/11;
UI hiển thị giới hạn7 ngày, submit bị khóa khi EW bỏ chọn và khi bật. Gọi API
trực tiếp cả BL_ML lẫn BL_ML+EW đều trả409 VFF_STALE. Truy vấn Job JOIN
Portfolio trên PostgreSQL xác nhận **0 optimization job full** trước/sau restart.

Đã stop API/worker rồi restart PostgreSQL, RabbitMQ, Redis và Auth bằng
Compose; dùng up --wait để đưa các service liên quan trở lại. Receipt đối
chiếu model, training job, publication, snapshot, selection/epoch và bundle
khớp trước/sau. Browser mở lại đúng full portfolio stale và giữ nguyên gate.
Tài khoản, danh sách volume, model/snapshot cũ và response nguyên vẹn của đề
xuất `ec78d461-8eef-4242-a7b1-a303e8f43cf6` đều khớp. Browser mở lại chính
đề xuất cũ; do TTL cũ đã hết 23:24 ngày 11/11, nút chấp nhận bị khóa và thông
báo hết hiệu lực được giữ đúng. Không gia hạn hoặc tái tính đề xuất đó.

Image Quant cuối, build từ Dockerfile Compose chuẩn:
`sha256:dd1571555076edf1d6514c89f8d805d3abfdeecbea5b4affdfe01151bd9508b6`.
Không dùng lớp vá trong container. Bộ kiểm thử cuối: **682 passed / 5 opt-in
PostgreSQL skipped**; Web **140 passed**, typecheck và production build đạt.

Bằng chứng local:

- [Full snapshot/source audit](../../infra/local/.generated/phase1-full-snapshot-receipt.json)
- [Training](../../infra/local/.generated/phase1-full-training-receipt.json)
- [Browser review/publication](../../infra/local/.generated/phase1-full-stale-publication-browser-receipt.json)
- [Browser stale](../../infra/local/.generated/phase1-full-stale-browser-receipt.json)
- [API stale](../../infra/local/.generated/phase1-full-stale-api-receipt.json)
- [Runtime pins trước restart](../../infra/local/.generated/phase1-full-runtime-receipt.json)
- [Browser full portfolio sau restart](../../infra/local/.generated/phase1-full-stale-persistence-browser-receipt.json)
- [Account/volume/đề xuất cũ](../../infra/local/.generated/phase1-full-preservation-receipt.json)
- [Playwright stale mode](../../output/playwright/sanitized/phase1-full-stale.json)
- [Playwright mở lại đề xuất cũ](../../output/playwright/sanitized/phase1-offline-persistence.json)

Positive nghiệm thu mới (broker BL_ML full, trọng số trên dữ liệu thật và
persistence đề xuất full) còn bị chặn bởi VFF, dù các fixture numerical và
serving v4 đã đạt. Giữ freshness7 ngày như yêu cầu; cần observation đủ điều
kiện tại checkpoint hợp lệ trong ngưỡng, không chỉ NAV raw mới hơn.

Bản tổng hợp machine-readable và log/lệnh đã chạy: [acceptance.json](../../outputs/step1/full-local-acceptance-20261112/acceptance.json).
Các script kiểm tra trong cùng thư mục chạy từ repo root, dùng helper Auth
local và không ghi bearer token ra log.


## User chọn tài sản — nghiệm thu ngày 12/11/2026

Task0–16 đã triển khai trên Compose `portfolio-auth-demo`. Catalog có 30 cổ
phiếu, GOLD SJC và VFF (quỹ trái phiếu), độc lập với publication còn hạn.
Tick nghĩa là cho phép cân nhắc; lưu được 1–32 mã, optimize cần ít nhất hai
mã và ràng buộc khả thi. Không tự thêm VFF/cash. Policy custom mixed vẫn
cần VFF, floor defensive >=15%, cap non-defensive <=70%, cap mỗi mã <=50%.

Candidate revisions được lưu append-only; job ghim revision/profile/policy,
snapshot/bundle/model và hạn selection riêng. EW/MVO dùng toàn candidate;
BL_ML chỉ chạy K5 trong worker khi có hơn năm cổ phiếu, rồi map về candidate
order với inactive bằng đúng 0. Consumer gọi Quant kiểm tra lại proof từ
pinned resource trước khi lưu. Đề xuất lịch sử dùng kết quả đã lưu.

Nhánh mới dùng source snapshot3, model5 và prepared bundle2; các nhánh cũ
snapshot1–2/model1–4/bundle1 giữ nguyên. Model v5 chung cho 30 cổ phiếu,
không fit theo từng user. Runtime chỉ đọc manifest và UBJ native, đúng
best_iteration, scaler, tám feature, seed42–46 và confidence/Option B.

### Lệnh build và rollout đã dùng

Chạy từ repo root. Không chạy bootstrap lại, `down -v` hoặc vá filesystem
container. Trước các batch build/migration đã kiểm tra >=5 GiB trống; đã có
sáu PostgreSQL custom dumps và host-artifact backup private, kiểm tra đọc
được. `.generated/.env`, accounts và secrets không bị viết lại.

```bash
docker compose --env-file infra/local/.generated/.env \
  -f infra/local/compose.yaml -p portfolio-auth-demo config --quiet

docker compose --env-file infra/local/.generated/.env \
  -f infra/local/compose.yaml -p portfolio-auth-demo \
  build market-migrate ml-migrate quant-migrate portfolio-migrate web

# Khi chỉ cần build Quant: dùng chính Dockerfile trong Compose.
docker compose --env-file infra/local/.generated/.env \
  -f infra/local/compose.yaml -p portfolio-auth-demo build quant-migrate

docker compose --env-file infra/local/.generated/.env \
  -f infra/local/compose.yaml -p portfolio-auth-demo \
  run --rm --no-deps portfolio-migrate
```

Migration additive đến `b70211d9e301`, không backfill portfolio cũ. Đã rollout
reader/worker trước producer. Compose mặc định giữ
`USER_SELECTED_ASSETS_ENABLED=false`. Override local đã kiểm thử nằm tại
`infra/local/.generated/user-selection/compose.web3100.yaml`: chỉ đổi Web
sang `127.0.0.1:3100`, `APP_ORIGIN=http://127.0.0.1:3100` và bật gate ở
Portfolio/Quant API. Cổng3000 đang thuộc SSH tunnel hiện có nên được giữ nguyên.

```bash
docker compose --env-file infra/local/.generated/.env \
  -f infra/local/compose.yaml \
  -f infra/local/.generated/user-selection/compose.web3100.yaml \
  -p portfolio-auth-demo up -d --no-deps \
  market-api market-refresh ml-api ml-worker \
  quant-api quant-consume quant-dispatch quant-publication \
  portfolio-api portfolio-consume portfolio-dispatch web

docker compose --env-file infra/local/.generated/.env \
  -f infra/local/compose.yaml -p portfolio-auth-demo exec -T market-refresh \
  python -m market_service.selected_refresh \
  --directory /datasets/refresh/full-phase1 \
  --seed /datasets/refresh/full-phase1/seed.json
```

Fit được enqueue qua ML API bằng data-operator có sẵn quyền `ml:train`,
`model_family=phase1-asset-ensemble-v5`, snapshot/hash dưới đây,
`training_cutoff=2026-10-23`, freshness7. Đây là cutoff của epoch đã nghiệm thu,
không phải giá trị mặc định để dùng cho mọi lần fit sau. Request/job thực tế
nằm trong `.generated/user-selection/training-live.json`.
Reviewer duyệt trên browser bằng model-reviewer, reason, If-Match và
Idempotency-Key; chờ `artifact_ready=true` rồi data-operator phát hành bằng
approved_model_id. Không sửa trạng thái registry qua SQL.

### Pins và kết quả thực tế

| Mục | Giá trị |
| --- | --- |
| Model v5 APPROVED / artifact_ready | `34fc4b8d-debe-4986-ab2a-e18b60e1e5f3` / true |
| Training job SUCCEEDED, một attempt | `ee8d7e13-afb1-492a-9e3e-4450932c9a38` |
| Coverage / native members | 30/30 cổ phiếu, 150/150 UBJ, không omission |
| Fit epoch / label cutoff | 02/11/2026 / 23/10/2026 |
| Fit thực tế | `2026-11-12T15:40:58.243709Z` |
| Snapshot fresh READY / per-asset quality | `9c060194-1172-432a-a6a1-06f1aaaf8779`, 32/32 PASS, 54.229 observations |
| Snapshot SHA-256 | `9e943b5a5b88faa41abbf83d1db08af310769a0b896bff31f283073eb97ef739` |
| Fresh publication SUCCEEDED | `efc2d25c-405e-4bf5-b6ed-bc6d5b30023a` |
| Approved model manifest SHA-256 | `09115d2210636e4b92c2626b0b1d159f82ef7444d4a9a1b679ab107e2942e143` |
| Prepared bundle SHA-256 | `7821d72db25403b81dd5394db85dd8058083d2ea238bac55cd41cf469a8361dc` |
| Job = proposal, FPT/MWG/VCB/VFF | `16471f6c-911d-4a57-98ca-eea54b5ccb53` |
| Job = proposal, 8 cổ phiếu + GOLD/VFF | `b0e6c42b-6cc5-4e44-a6d2-1c920d0dda4a` |

Hai job trên đạt SUCCEEDED qua RabbitMQ, strategy thực thi `BL_ML`, EW dự
phòng bỏ chọn. Tổng trọng số bằng100% trong tolerance1e-7, mọi vị thế <=50%,
VFF gần50%, defensive/non-defensive đúng ràng buộc. Ca10candidate chọn
CTG, DGC, FPT, GAS, GVR cùng GOLD/VFF; ACB, BID, HDB bằng đúng0.
Ca4candidate dùng cả FPT/MWG/VCB/VFF, không chạy K5. Tất cả model/snapshot,
input/selection/constraint hashes được đối chiếu với pin của job.

Freshness giữ đúng7 ngày lịch, phiên hoàn tất mới nhất và VFF buffer5 phiên:
GOLD đủ điều kiện 11/11 (tuổi1); VFF đủ điều kiện 05/11 (tuổi7) tại kiểm tra
12/11. TTL selection/proposal là **00:00 ngày13/11/2026 GMT+7**, sớm hơn TTL24h
của resource. Không gia hạn theo ngày tải hoặc tuổi NAV raw.

Negative gate dùng snapshot thật cut11/11
`9a61bcf9-a3f5-4e97-8b34-3e3b9bde7479`, 54.197 observations: NAV VFF đủ
điều kiện 03/11, tuổi9. Catalog vẫn32 mã, lưu draft được; UI và API trả
VFF_STALE kể cả khi request cho EW dự phòng, không tạo job. Sau đó operator
phát hành lại snapshot12/11 thật; chính các draft đó chạy BL_ML. Không đổi
clock, buffer, freshness hoặc giá để làm positive pass.

GOLD+VFF đạt MVO50/50; EW khả thi, BL_ML báo NO_VALID_ML_VIEWS. Đã kiểm tra
Bob bị404 với portfolio/history/proposal không sở hữu. Candidate edit và
risk reassessment được thực hiện khi job thật còn QUEUED: job cũ giữ revision,
profile/constraints đã ghim; job mới dùng profile mới (risk aversion6), replay
đúng ID và sai phiên bản bị409. Accept đề xuất cũ sau edit bị chặn.

### Kiểm thử, restart và bảo toàn

```bash
PYTHONDONTWRITEBYTECODE=1 .venv-software/bin/python \
  scripts/export_software_contracts.py
PYTHONDONTWRITEBYTECODE=1 .venv-software/bin/python -m pytest \
  tests/software packages/portfolio-core/tests -q
cd apps/web
npm test
npm run typecheck
```

17 schemas/OpenAPI/event files được export. Python/core: **766 passed,
6 opt-in skipped**; DATE binding trên PostgreSQL thật chạy riêng **1 passed**.
Web **145 passed**, typecheck, Ruff/diff và production build bằng Dockerfile
Compose đạt. Hai Redis recovery tests cần quyền bind loopback; lần chạy trong
sandbox bị EPERM, chạy lại có quyền loopback đạt toàn bộ145, không sửa test.

Ba ca lifecycle và một ca risk-revision đã đạt; persistence chạy riêng.
Lệnh browser chạy trong `apps/web`:

```bash
E2E_DISPOSABLE_STACK=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:3100 \
USER_SELECTION_REQUIRE_POSITIVE=1 \
USER_SELECTION_MODEL_ID=34fc4b8d-debe-4986-ab2a-e18b60e1e5f3 \
USER_SELECTION_SNAPSHOT_ID=9a61bcf9-a3f5-4e97-8b34-3e3b9bde7479 \
USER_SELECTION_FRESH_SNAPSHOT_ID=9c060194-1172-432a-a6a1-06f1aaaf8779 \
npm exec -- playwright test user-selection.e2e.ts

E2E_DISPOSABLE_STACK=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:3100 \
USER_SELECTION_REQUIRE_POSITIVE=1 \
npm exec -- playwright test user-selection.e2e.ts --grep 'pending risk revision'

# Chỉ chạy sau khi restart thật; dùng chính receipt đã lưu.
E2E_DISPOSABLE_STACK=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:3100 \
USER_SELECTION_REQUIRE_POSITIVE=1 USER_SELECTION_VERIFY_RECEIPT=1 \
npm exec -- playwright test user-selection.e2e.ts --grep 'reopens identical'
```

Đã restart đủ23 service đang chạy trong đúng project, gồm PostgreSQL,
RabbitMQ, Redis, Auth, các API/worker và Web; không chạy lại init/reset.
Các lượt browser mở lại đúng12 proposal mới đã lưu cùng proposal cũ
`ec78d461-8eef-4242-a7b1-a303e8f43cf6`, đối chiếu nguyên kết quả/pin/history.
16/16 command gốc recompute đúng hash. Receipt SQL/files xác nhận account,
volume, snapshot/model/artifact, accepted target và các row gốc không đổi.
Không dùng proposal mới để thay kiểm tra persistence của proposal cũ.

Lượt live đầu phát hiện consumer thiếu OIDC_TOKEN_URL/QUANT_API_URL/
QUANT_CLIENT_SECRET để gọi verify-selection; đã bổ sung credential scope
quant:resolve hiện có trong Compose và thêm regression. Các job FAILED của
lượt đầu được giữ nguyên, không sửa SQL hoặc purge queue. Snapshot thử cut
lịch sử bị quarantined trước fix cutoff cũng được giữ; fix chọn source job
đã biết tại cutoff và fallback đã kiểm hash, không backdate first-seen.

Đã dọn cache/image trung gian không dùng và cache package/bytecode/HTTP/code
có thể tạo lại để giữ capacity; không xóa cookie/profile trình duyệt, tài khoản
hoặc volume. Image rollback ban đầu vẫn được giữ. Chưa commit/stage workspace.

Image Quant canonical cuối:
`sha256:79c856085cd06d405a7c428e955a1727680870dbd40f7de65780daed17e663e6`.

Báo cáo token-free, IDs/weights/hashes, lệnh và log thực tế:
[acceptance.json](../../outputs/step1/user-selected-local-acceptance-20261112/acceptance.json).
Receipt chi tiết tại `.generated/user-selection/`; reviewer độc lập không còn
Critical/Important findings. Không tái lập hiệu suất backtest; giữ
historical_publication_verified=false. Các mục full legacy còn blocked ở phần
trước không được đổi thành passed bởi đợt custom này.
