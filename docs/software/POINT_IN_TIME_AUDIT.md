# Point-in-time audit v5 — 18/11/2026

Phạm vi: model `70716105-ef74-4203-bfa6-9657f756e0b6`, approved manifest
`d511678a0626d8a749b4e4dbd36cc58114702212fa9ba171d180403ecd1cca89`,
recommendation `f1a6761b-01da-42be-8258-2ecdf1eb3242` từ receipt BL_ML đã lưu.
Không train/promote/publish lại, không sửa dữ liệu/model/result/flags. Audit này
kiểm thời gian, revision và evidence đang có; không thay thế một historical
walk-forward hoặc chứng nhận hiệu quả đầu tư.

## Kết quả

| Kiểm tra | Bằng chứng | Trạng thái |
|---|---|---|
| Snapshot → Market ledger | 54.325 observation mỗi snapshot khớp revision ID, giá, timestamp, convention, hash và quality/source pin | PASS |
| Revision được chọn | Không có revision mới hơn trong ledger đã lưu đủ điều kiện trước snapshot mà bị bỏ qua; không có input/quality timestamp sau snapshot hoặc decision thật | PASS |
| Nguồn trên filesystem | 99 normalized CSV, 64 metadata sidecar, 120 raw artifact references kiểm checksum đạt; không có fetch receipt sau quality | PASS cho references đã lưu |
| Train prefix | 1.700 phiên ×30equity =51.000 ô giá; 50.963 source observations và37carry theo missing-session declarations | Đã đối chiếu |
| Availability của train prefix | Mọi dependency đã được hệ thống biết trước epoch16/11 và trước lúc train thật; known range10/11 16:09:12–11/11 16:51:42 UTC | PASS cho system first-seen |
| Timeline thật | Training snapshot/knowledge ≤ trained_at ≤ approved_at ≤ publication ≤ decision18/11 | PASS |
| Model khả dụng ở epoch16/11 | Model thực sự train và approve18/11 | Không khả dụng tại mốc danh nghĩa16/11 |
| Lịch sử publication/revision của provider | published_at trống cho toàn54.325 observation; ledger chỉ có revision1 mỗi observation | NOT_EVIDENCED |
| Certification | Model, schema và report giữ false | Chưa chứng nhận |

Hai snapshot được audit là training v1 `6aa157bf-aa7d-4b71-bd24-d3d0717ccd21`
và serving live v2 `8c2dc496-7d83-4cb2-bc3f-aee78732ee73`. Chúng có cùng
observation hash; khác availability policy và thời điểm tạo. Evidence export
giữ một bản observations theo hash và kiểm độc lập từng snapshot manifest.

Toàn snapshot có96observation first-seen sau nominal epoch16/11. Các dòng này
không thuộc training prefix kết thúc06/11; không thể kết luận chúng đã rò vào
train chỉ từ timestamp global `training_knowledge_cutoff=18/11`. Regression
kiểm đúng đường trainer cắt prefix/features/labels. 37ô carry là giá được dẫn
từ observation cũ tại những phiên thiếu đã khai báo, không phải37bản ghi giá
nguồn mới hoặc bằng chứng giao dịch thực tại các phiên đó.

Timeline thực (UTC+7): train18/11 15:38:32, approve15:42:10, publish15:43:23,
decision15:44:22. Fit epoch16/11 là nhãn theo lịch refit. Receipt thật vẫn hợp
lệ cho lượt chạy18/11; không dùng model train18/11 để tuyên bố đã dự báo16/11.
Hai snapshot này cũng được tạo18/11, dù các giá trong training prefix đã có
system first-seen trước đó. `known_at` trong audit lấy max timestamp ingestion,
availability, publication nếu có và quality check; không đồng nhất quality
check time với thời điểm provider công bố giá.

## Những phần chưa đủ bằng chứng

- System first-seen là10–18/11/2026, muộn hơn observation close cho toàn bộ
  lịch sử đang lưu. Nó chứng minh lúc hệ thống thu thập được giá, không xác nhận
  provider đã công bố đúng phiên bản ấy tại từng ngày lịch sử.
- Chỉ revision1 đang được ghi nhận; chưa có archive đầy đủ các phiên bản sửa
  giá/NAV trước lần hệ thống bắt đầu thu thập. Không suy ra provider chưa sửa
  dữ liệu chỉ vì local ledger chưa ghi revision2.
- 35/99job không có sidecar riêng;32trong số đó còn provenance/raw references
  dạng legacy trong dataset spec và đã kiểm được hashes. Ba job còn lại chỉ có
  normalized CSV/quality evidence, thiếu HTTP fetch receipt. Không tự bịa ngày
  công bố từ observation_date hoặc Fmarket createdAt.
- Giá cổ phiếu mang convention provider_adjusted nhưng audit này chưa kiểm
  historical corporate-action factors/vintages, thành viên universe từng kỳ,
  exchange calendar hay tính có thể giao dịch của các phiên thiếu.
- Validation fold hiện dùng cả cho early stopping và MAE/RMSE. Đây là validation
  metric, không phải untouched out-of-sample test. Chưa chạy replay cuốn chiếu,
  kiểm độc lập quá trình chọn hyperparameters hoặc forward/paper performance
  với universe/constraints/costs đồng nhất.
- NAV live v2 căn theo valuation date cho dữ liệu đã biết hiện tại. Đường giá
  này không được coi là lịch publication point-in-time để replay quá khứ.

## Regression và cách chạy

```sh
.venv-software/bin/python scripts/audit_model_point_in_time.py \
  --receipt output/bl-ml-epoch-20261116/chat-flow-receipt.json \
  --output output/point-in-time-v5
.venv-software/bin/python -m pytest tests/software/test_point_in_time_audit.py \
  tests/software/test_temporal_regressions.py -q
.venv-software/bin/python -m pytest tests/software packages/portfolio-core/tests -q
```

CLI dùng original facts hash/bundle/model/snapshot pins, không chọn latest.
Đọc Market DB qua owning container với `SET TRANSACTION READ ONLY`, kiểm nguồn
đã lưu tại local filesystem; không gọi provider hay ghi business records.
Auth dùng local login bình thường, token chỉ ở memory. Raw evidence nén ở
`output/point-in-time-v5/market-evidence.json.gz`; report ở `report.json`, mode600,
ngoài Git. Exit0 chỉ có nghĩa không thấy mâu thuẫn trong checks đã chạy; các
mục NOT_EVIDENCED và `point_in_time_certified=false` vẫn giữ nguyên.

16tests mới gồm: hash/clock không hợp lệ; revision đến muộn; quality/source pin;
model chưa có tại nominal epoch; raw/normalized artifact bị thay; legacy raw
reference; snapshot as-of không đổi khi thêm revision tương lai; trainer không
đọc features/labels sau cutoff; scaler không học từ validation/purged rows;
K5/features/covariance không đổi khi thêm/chỉnh phần panel tương lai. Native
fit/inference được inject tại boundary trong các unit tests liên quan; đây là
offline regression, không được dùng thay bằng chứng real-provider integration.

Lượt audit:16focused tests đạt; full source cuối861Python/core passed,
6opt-in skipped; Ruff/diff đạt. Một lượt full trung gian ghi1failure ở
`test_requested_explanation_uses_method_from_canonical_facts_and_cited_passage`
trong test Chat đang cập nhật đồng thời. Case này chạy riêng rồi full trên
source hiện tại đều đạt; không sửa code/test Chat trong audit này. Log lần lỗi
và các lần chạy lại được giữ ngoài Git. Đọc lại đúng receipt BL_ML,
training/review/publication/model receipts và
preservation receipt; không tạo allocation/approval mới. Không restart mới,
không chạy browser/RAG eval/research backtest/forward test trong đợt này.

Preservation tổng quát **FAIL ở portfolio_db.portfolio**, không đánh dấu xanh
hoặc thay baseline. Log Portfolio ghi nhận accept200 lúc16:03:09 UTC+7 cho
recommendationfafbc9fc-9fef-460c-ac35-d4529a209308, portfolio
c7a7d035-33a8-4ae2-976a-5dba38b19abd (khác portfolio kiểm thử BL_ML của audit);
accepted_target mới592ccf77-3bc8-4678-a063-afe5437a545a xuất hiện sau capture.
Audit chỉ dùng GET/Market read-only và không gọi accept; log này chưa xác định
actor. Không hoàn tác thay đổi đó. Tất cả bảng khác, toàn bộ file hashes đã
capture, volumes và catalog history đều kiểm tra đạt. Model7071 và recommendation
f1a6 cùng receipt mục tiêu vẫn khớp nguyên vẹn. Chi tiết ở
`preservation-diagnostic.json`, không thay kết quả FAIL gốc.

Bước tiếp theo là inventory bằng chứng theo nguồn/ngày, xác định đoạn nào có
vintage/first-seen đáng tin rồi mới replay as-of trên đoạn đó. Phần không có
archive phải giữ unknown; có thể thu thập evidence cho forward test từ hiện
tại. Không sửa flags trên các model/receipt cũ để lấp khoảng trống bằng chứng.
