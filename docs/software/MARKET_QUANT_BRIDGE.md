# Market snapshot → Quant bằng dữ liệu thật

Cập nhật 24/10/2026, tiếp nối phần còn thiếu của tuần 6. Luồng local đã chạy:
Market ingestion → immutable snapshot → features/numerical bundle → approved
XGBoost → BL_ML qua RabbitMQ → recommendation → accepted target.
Receipt local được tạo lại bằng các smoke commands bên dưới và không lưu trong Git.

## Dữ liệu và kết quả thực tế

- Universe `VN_EQUITY_REAL`: FPT, VCB, HPG; mỗi mã 199 giá đóng cửa từ
  05/01 đến **23/10/2026**, tổng 597 revisions. Nguồn KBS qua vnstock 4.0.4.
- Giá stock giữ đơn vị `thousand_VND/share`, basis `provider_adjusted`.
  [Tài liệu Market chính thức](https://vnstocks.com/docs/vnstock/thi-truong-market)
  mô tả đơn vị và khác biệt điều chỉnh theo provider. Không trộn basis/provider
  trong một chuỗi, không lấy CSV synthetic làm giá thật.
- Serving/core cùng model, inputs và policy đạt max sai số weights < `1e-10`.
  Recommendation và accepted target giữ `demo=false`, hash snapshot, revision
  provenance và immutable bundle/model pins. Cross-owner read trả 404.
- Training economic cutoff 03/10/2026; dữ liệu được biết và model được train/
  duyệt ngày 24/10. Decision dùng ngày dữ liệu 23/10 và thời điểm thực tế sau duyệt.
  Không giả vờ model đã tồn tại tại ngày cutoff.

Đây là pilot ba cổ phiếu để kiểm chứng dữ liệu/serving, chưa phải representative
selection hay universe đa tài sản hoàn chỉnh. Target là kế hoạch phân bổ; holdings
vẫn `NOT_TRACKED`, không phát sinh giao dịch.

## Hợp đồng và kiểm soát

Market thêm `data_origin` và `price_basis` theo revision; dữ liệu cũ mặc định
`unverified`, snapshot cũ không bị sửa. Publisher đọc qua hai endpoint internal
snapshot/observations bằng client `quant-publisher`, scope `market:snapshot:read`,
audience `market-api`. Không đọc chéo database hoặc dùng role người dùng thay scope.
Bootstrap/upgrade reconcile client mới mà giữ secrets và dữ liệu cũ.

Builder kiểm tra snapshot/observations/revision hashes, origin real, thời điểm
available/ingested, cùng ordered observed-session grid và unit/basis. Giá không
hợp lệ, lịch lệch, thiếu lịch sử, dữ liệu tương lai/cũ hoặc hash sai đều bị từ chối;
không forward-fill/intersect để lặng lẽ thay kỳ lợi suất. Tối thiểu 60 returns,
lookback tối đa 252, freshness mặc định 7 ngày, khoảng trống tối đa 14 ngày.
Calendar chỉ là `observed-sessions-only`, chưa có lịch giao dịch chính thức.

`market-close-features-v1`: return 1 phiên, momentum 5/20 phiên và sample
volatility 20 phiên (ddof=1). Numerical inputs dùng daily simple returns,
arithmetic sample mean và covariance ddof=1. BL prior equal-weight, confidence
0.5 được ghi rõ; chưa phải market-cap equilibrium hoặc calibrated uncertainty.

Training schema 2 tách `label_dates` (ngày kinh tế) khỏi `feature_known_at`,
`label_known_at`, `knowledge_cutoff` (thời điểm thực biết). Approved manifest pin
snapshot hash/training knowledge/trained_at; inference yêu cầu features đã biết,
model đã train và **đã được duyệt** trước decision_at. Schema 1 vẫn phục vụ
legacy demo; real publication bắt buộc schema 2 real.

Bundle ghi immutable và checksum-pinned; catalog update atomic, dùng cùng lock
với DEMO refresh. Replay cùng nguồn/model/config trả cùng bundle; `--renew` tạo
phiên mới nếu cần, không ghi đè pins cũ. Mặc định expiry sớm hơn giữa 24 giờ và
freshness của nguồn. Quant mount artifact directory read-only. Historical pins
vẫn được giữ; universe mới nhất hết hạn sẽ unavailable, không tự chọn bản cũ.

## Chạy lại local

Cần stack healthy, migration mới và identity upgrade; xem
[setup guide](SETUP_AND_API_TESTING.md). Fetch dùng môi trường research đã có
vnstock; serving vẫn tách dependencies. Không ghi đè dữ liệu nghiên cứu.

```sh
venv/bin/python scripts/fetch_serving_prices.py --symbols FPT VCB HPG --start 2026-01-01 --end 2026-10-24 --output /tmp/market-quant-real-20261024
.venv-software/bin/python scripts/smoke_market_quant.py --source-directory /tmp/market-quant-real-20261024 --reviewer local-integration-reviewer
.venv-software/bin/python scripts/smoke_market_quant.py --verify-receipt
```

Fetch ghi raw CSV và manifest checksum/provider/unit/basis. Smoke đăng ký pack,
chạy durable ingestion jobs, tạo snapshot, train candidate, approve artifact cho
kiểm chứng local, publish, tạo và accept proposal. Reviewer string là audit
metadata của operator local, chưa thay role-based promotion trong ML Platform.
Receipt riêng giữ tại `infra/local/.generated/market-quant-receipt.json`.
Chạy `--verify-receipt` sau restart để kiểm tra cùng IDs/hash/target và parity.

Publisher có thể chạy độc lập; thiết lập `OIDC_TOKEN_URL`, `MARKET_API_URL`,
`MARKET_READER_CLIENT_SECRET` trong môi trường operator tin cậy, không đưa secret
vào shell history. Dùng một artifact directory có quyền ghi cho operator:

```sh
.venv-software/bin/python -m quant_service.snapshot_publisher --directory /absolute/artifacts --snapshot-id <uuid> --snapshot-hash <hash> train --cutoff 2026-10-03
.venv-software/bin/python -m quant_service.model_worker --directory /absolute/artifacts approve --candidate <candidate-file> --sha256 <candidate-hash> --reviewer <reviewer-id>
.venv-software/bin/python -m quant_service.snapshot_publisher --directory /absolute/artifacts --snapshot-id <uuid> --snapshot-hash <hash> build --universe-id VN_EQUITY_REAL --model-file <approved-file> --model-sha256 <approved-hash>
```

Bỏ model flags để publish EW/MVO. Chỉ publish BL_ML khi approved artifact tương
thích. Publisher là CLI riêng, chưa có cron/durable publisher job trong Compose.
Không tự train trong HTTP hoặc optimizer consumer.

UI lấy `GET /api/v1/universes` qua BFF/Portfolio/Quant, ưu tiên universe được
attest real, cho phép chọn DEMO và phân biệt nguồn chưa xác minh. Wizard, proposal
và accepted target hiển thị đúng loại dữ liệu. Public caller không truyền features,
model file hoặc weights.

## Bằng chứng kiểm chứng ngày 24/10

| Kiểm tra | Kết quả |
| --- | --- |
| Offline software/core | **248 Python tests**, 1 cảnh báo Starlette/AnyIO có sẵn; scoped Ruff đạt |
| Web/BFF | **51 tests**, typecheck và production build đạt |
| Contracts/migrations | Export 9 contracts lặp giữ hash; migration SQLite roundtrip/check cho ba service và Market PostgreSQL migration đạt |
| Live giá thật | 3 ingestion jobs → snapshot → features/training → approved model → BL_ML → accepted target; parity < `1e-10` |
| Persistence/regression | Restart cả 9 API/worker processes; cùng receipt giá thật và các receipts foundation/G2/ML cũ đều đạt khi kiểm tra tuần tự |
| Boundaries/runtime | DB/broker/OIDC probes đạt; source hashes module mới trong backend containers khớp checkout và cả ba `pip check` đạt |
| Browser thật | Đăng nhập alice → wizard mặc định universe real → BL_ML SUCCEEDED → chấp nhận target, nhãn Giá thị trường, ngày 23/10, không bật fallback |
| Review độc lập | Sửa 3 findings: catalog writer lock chung với bootstrap, cách ly retained artifacts không liên quan, approved_at trước decision; mỗi điểm có regression RED→GREEN |

Weights trong phiên kiểm chứng UI: FPT 21,9%, VCB 28,1%, HPG 50,0% (chỉ là đầu
ra kỹ thuật của cấu hình pilot này).

Lệnh kiểm tra tổng hợp: `.venv-software/bin/python scripts/setup_software.py verify`.
Live receipt: `scripts/smoke_market_quant.py --verify-receipt`. Các smoke cùng user
nên chạy tuần tự: chạy password-grant login đồng thời gặp HTTP 400 ở Keycloak trong
lần kiểm tra; chạy lại từng script đạt, không thay credentials hoặc auth policy.

Build Docker mặc định dừng ở metadata registry Node. Backend images đã build từ
source hiện tại trên runtime dependencies local đã có, `--no-deps` và build tools
offline; không đổi dependency locks. Web build lại Linux bằng `npm ci` từ package
lock, development dependencies ở build stage và production runtime trên image Node
local đã có. Workaround chỉ ở Dockerfiles tạm; Dockerfiles chuẩn của repository giữ
nguyên quy trình reproducible. Không reset/prune volumes hoặc generated credentials.

## Giới hạn còn lại

Provider-adjusted history thu thập hôm nay không chứng minh dữ liệu corporate
actions/universe đã biết tại từng ngày quá khứ. Validation chronological 80/20 có
label embargo và scaler fit trên train subset; manifest ghi rõ
`point_in_time_certified=false`. MAE/RMSE chỉ là kiểm tra kỹ thuật model pipeline,
không phải bằng chứng lợi nhuận/backtest/UAT.

Tuần 6 còn representative selection, breadth đa tài sản, quality/quarantine theo
exchange calendar và vận hành publish theo lịch. Tuần 7 còn ML registry/jobs,
role-based promotion, monitoring/retrain/rollback. Ledger/Chat/RAG và nghiên cứu
selection/ablation chưa thuộc phần hoàn tất này. Chưa deploy staging hoặc chạy
GitHub Actions từ thay đổi local.
