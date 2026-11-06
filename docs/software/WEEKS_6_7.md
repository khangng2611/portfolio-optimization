# Onboarding, accepted target và approved model serving

**Cập nhật 24/10/2026:** [Market→Quant bridge](MARKET_QUANT_BRIDGE.md) đã bổ sung features từ giá thật, schema 2 với knowledge timestamps và universe discovery. Phần dưới ghi lại adapter ban đầu ngày 23/10.


Hiện thực ngày 23/10/2026 trên kiến trúc hiện có. Nguồn roadmap:
[HK261, tuần 6–7](https://docs.google.com/spreadsheets/d/1Z8h67JC44iQIYguh-iZNZqC0b2zqZSIMlljW0kosMH8/edit?gid=1869718089).

## Luồng G2

1. Đăng nhập tại `http://localhost:3000`, hoàn thành wizard 3 bước.
2. Backend xác định profile và policy v1; dashboard hiển thị vốn kế hoạch,
   hệ số ngại rủi ro và giới hạn mỗi tài sản.
3. Chọn EW/MVO/BL_ML, tạo proposal; theo dõi durable job qua RabbitMQ/Quant.
4. Xem weights, vốn mục tiêu, ngày dữ liệu, policy/model/core và diagnostics.
5. Chấp nhận proposal để lưu target immutable. Dashboard hiển thị target cùng
   thời điểm chấp nhận. Không tạo holdings, transaction hoặc lệnh giao dịch.

Universe trên UI lấy từ catalog qua `/api/v1/universes`; có thể chọn `VN_EQUITY_REAL` hoặc `DEMO` khi còn hiệu lực. MVO/EW dùng prepared inputs server-side. BL_ML
chỉ khả dụng nếu có approved model/views phù hợp; người dùng có thể bật fallback
EW trước request. Không tự chuyển strategy khi sai dữ liệu, hết hạn hoặc solver lỗi.

## Questionnaire/policy v1

`questionnaire_version=risk-v1`. Mỗi yếu tố cho mức 0/1/2; profile lấy mức thấp nhất:

| Yếu tố | 0: thận trọng | 1: cân bằng | 2: tăng trưởng |
| --- | --- | --- | --- |
| Horizon | <12 tháng | 12–59 tháng | ≥60 tháng |
| Nhu cầu thanh khoản | high | medium | low |
| Khả năng chịu lỗ | low | medium | high |
| Kinh nghiệm | — | beginner | experienced |

Policy `risk-policy-v1:{profile}` dùng risk aversion tương ứng **6 / 3 / 1.5**,
max position **50%**, long-only và tổng weights 1. Đây là ánh xạ nghiệp vụ v1 do
ứng dụng chọn, chưa được hiệu chỉnh bằng UAT hoặc chứng minh MDD đơn điệu.
Không dùng mã tài sản phòng thủ cố định khi chưa có asset-class contract từ Market.

Policy/profile được freeze vào command hash và recommendation. API manual cũ
vẫn hoạt động; sửa risk aversion/max position chuyển nhãn về manual policy.
Profile không phải suitability certification hoặc cam kết mức lỗ.

## API bổ sung

Tất cả routes dùng owner từ JWT và scope `portfolio:read/write` hiện có; không
nhận owner/model/features/weights từ public request. BFF giữ CSRF/Origin checks.

| Route | Chức năng |
| --- | --- |
| `POST /api/v1/onboarding/portfolios` | `{name, capital_vnd, universe_id?, answers}`; trả 201 portfolio/policy |
| `GET /api/v1/portfolios/{id}/dashboard` | Portfolio, accepted target, proposal count, target_matches_portfolio, holdings_status |
| `GET /api/v1/portfolios/{id}/targets` | Target history (100 bản mới nhất) |
| `POST /api/v1/recommendations/{id}/accept` | Body `{}`, `If-Match: "<portfolio version>"`; lưu target và tăng version |
| `POST /api/v1/portfolios/{id}/recommendations` | Bổ sung `fallback_strategy: "EW"` tùy chọn cho `strategy: "BL_ML"` |

Accept khóa portfolio để serialize với PATCH/result consumer/các lần accept.
Thiếu If-Match trả 428; sai version trả 412; proposal stale/hết hạn trả 409;
cross-owner (kể cả admin) trả 404. Retry recommendation đã accepted trả đúng target
cũ, kể cả request dùng If-Match ban đầu. Target đã lưu là lịch sử, không bị xóa khi
proposal hết hạn; `target_matches_portfolio` cho biết portfolio đã đổi sau accept.

`decision_context` là optional additive event field. Consumer mới vẫn tính đúng
hash command cũ không có field này. Request cũ cùng Idempotency-Key không bị đổi
body hash chỉ vì thêm `fallback_strategy=null`. Khi rolling upgrade, cập nhật Quant
consumer trước Portfolio producer vì strict consumer cũ chưa biết field mới.

## Training worker và manifest

Worker/CLI riêng: `python -m quant_service.model_worker`; không có training trong
HTTP request hoặc optimizer consumer. Đây là **adapter publication trên filesystem**,
chưa phải ML Platform service với DB, durable training jobs, role-based promotion,
registry aliases, rollback hoặc retrain scheduler.

```sh
.venv-software/bin/python -m quant_service.model_worker --directory /absolute/artifacts train --dataset /absolute/training.json
.venv-software/bin/python -m quant_service.model_worker --directory /absolute/artifacts approve --candidate <candidate-file> --sha256 <candidate-hash> --reviewer <reviewer-id>
```

Training JSON legacy dùng `schema_version=1`, `horizon_sessions=1`,
`return_unit=daily_simple_fraction`, ordered `asset_ids`, `feature_names`,
`feature_schema_version`, `snapshot_id`, `demo`, `training_cutoff`, `features`,
`targets`, `feature_dates`, `label_available_dates`.

Features phải tăng theo thời gian; mọi label available date nằm sau feature date
và không vượt cutoff. Worker chia validation theo thời gian 80/20, bỏ training rows
có label chưa biết trước validation start, fit scaler chỉ trên training subset.
Model CPU XGBoost 3.2.0 dùng 20 rounds, depth 2, seed 0; validation lưu MAE/RMSE,
counts và mốc embargo. Đây là cấu hình tối thiểu để chứng minh pipeline, không
phải model đã được tune hoặc chứng minh hiệu quả tài chính.

Worker ghi native `.ubj` và manifest CANDIDATE với hash dữ liệu/model. Approve tạo
manifest APPROVED mới với reviewer/time; không sửa candidate. Runtime directory
phải thuộc operator tin cậy và mount read-only cho Quant; reviewer string trong CLI
là audit metadata, không thay xác thực người phê duyệt qua service tương lai.

Prepared bundle bổ sung `ml_inference` chứa manifest reference `{file,sha256}`,
feature schema/order, asset order, feature date và rows. `model_bundle_id` là hash
approved manifest. Quant kiểm tra checksum/path containment/shape/scaler/cutoff/
runtime/core/units/approval và demo opt-in trước inference; tạo identity P,
native predicted Q và fixed confidence 0.5, đưa vào shared BL optimizer. Model
cutoff phải trước feature date, feature date phải khớp as_of và không trong tương lai.
Caller chịu trách nhiệm tạo features đúng thời điểm công bố và PIT universe;
bridge schema 2 hiện tự dựng features từ snapshot Market; chưa chứng minh full research timing.

Model format dùng native JSON/UBJ theo [tài liệu XGBoost Model IO](https://xgboost.readthedocs.io/en/stable/tutorials/saving_model.html).
Không deserialize pickle/joblib. Linux dùng wheel `xgboost-cpu` để tránh CUDA/NCCL;
macOS dùng `xgboost`, cùng version 3.2.0. Docker Quant thêm `libgomp1`.

## Kiểm tra local có thể lặp lại

Giữ credentials và volumes cũ. Dùng [setup guide](SETUP_AND_API_TESTING.md) để chạy
stack. Các smoke commands tạo dữ liệu synthetic local và token-free receipts:

```sh
.venv-software/bin/python scripts/smoke_g2.py
.venv-software/bin/python scripts/smoke_ml_serving.py --publish-demo
docker compose --env-file infra/local/.generated/.env -f infra/local/compose.yaml restart portfolio-api portfolio-consume portfolio-dispatch quant-api quant-consume quant-dispatch
.venv-software/bin/python scripts/smoke_g2.py --verify-receipt
.venv-software/bin/python scripts/smoke_ml_serving.py --verify-receipt
```

`--publish-demo` chủ động train/approve model **synthetic**, publish bundle DEMO mới
(7 ngày), giữ bundles/models cũ và secrets. Nó không promote model nghiên cứu hoặc
thay production registry. Chạy `smoke_g2.py` trước khi publish ML demo để thử cả
MODEL_UNAVAILABLE → EW; chạy sau publish để thử BL_ML có model. Script parity dùng
cùng dữ liệu/model/policy/core; không so live API với NAV cả kỳ hoặc legacy lỗi.

CI local-stack đã thêm G2 gate và target receipt verification. Native model/parity
tests nằm trong backend suite; CI hiện chưa có live ML smoke riêng.
