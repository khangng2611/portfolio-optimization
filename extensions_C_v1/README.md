# Additional Experiments C v1

Theo experiment_1.md (26/10/2026); thực hiện ngày 04/11/2026, tách khỏi Step1/Step2 và A+B/paper revision.

- **C1 hoàn tất:** fixed rule VFF30%, mỗi tài sản còn lại70%/6 trên đúng Proposed K5 + GOLD + VFF; cùng lịch 5 phiên, fill t+1, drift và chi phí. Hai run tái lập: extensions-C-20261104T210906 / extensions-C-20261104T211105.
- **C2 NOT RUN:** đã tìm nguồn và nộp feasibility stop; chưa nhận daily total-return levels cùng vintage/vendor dates/quyền nghiên cứu. CSV C2 chỉ có trạng thái/null và header, không phải lợi nhuận bằng 0.
- **C3–C6:** đề cương, chưa chạy.

Đọc trước report_C_v1.md hoặc báo cáo DOCX/PDF trong submission. Xem issues_to_supervisor.md, validations.md, C2_source_feasibility.md và data_dictionary.md. Các bảng dễ xem: C1_results.csv, comparisons.csv, paired_uncertainty.csv, target_L1_distances.csv. File lớn daily/trades/holdings và các snapshot mã gốc có trong gói ZIP minh chứng.

Chạy tại root repository, dùng research interpreter hiện hữu (không cài thêm dependencies):

```sh
venv/bin/python -B -m unittest extensions_C_v1.tests.test_extensions experiments_core.tests.test_core -v
venv/bin/python -B -m extensions_C_v1.C1_fixed_rule
venv/bin/python -B -m extensions_C_v1.C1_fixed_rule --parent-run <run_ID_trước>
venv/bin/python -B -m extensions_C_v1.build_evidence --run <run_ID_chính> --repeat <run_ID_lặp>
venv/bin/python -B -m extensions_C_v1.verify_evidence
```

Lưu ý verify_evidence hiện kiểm định hai run đã nộp theo ID cố định; nếu kiểm định run mới, cập nhật explicit IDs trong script/review, không ghi đè run cũ. C1 script tự tạo run riêng. Inputs phải khớp baseline_manifest.json; thiếu hoặc khác thì dừng, không fallback root datasets hiện tại. Giá và ledger private ở inputs/ không phát hành trong ZIP. C1 phụ thuộc helper thuần experiments_core/src/core.py và constants/hash helper frozen.py; source helper đã nhận diện trong manifests. Gói source dùng lại trong checkout này; không tự cung cấp giấy phép cho raw.

Sau khi có input C2 được thẩm định nguồn/quyền bằng chứng:

```sh
venv/bin/python -B -m extensions_C_v1.C2_market --levels /đường/dẫn/levels.csv --metadata /đường/dẫn/metadata.json --output /đường/dẫn/mới/C2_run
```

levels có index_date,index_level,vendor_record_date. Metadata yêu cầu identifier,name,provider,currency=VND,return_type=total_return,dividend_method,methodology_url,vintage,first_public_availability,retrieved_at,rights_evidence,research_use_permitted=true. Mọi khai báo phải có bằng chứng thật; code không thay thế thẩm định. Chỉ candidate families đã đóng băng; không dùng price index. Raw C2 chỉ giữ private, không tự upload.

C1_trades.csv lặp các tổng EVENT turnover/notional/cost ở 32 dòng tài sản: deduplicate strategy + execution_date trước khi cộng tổng. HHI min là của target, daily weights có drift. CAGR/MDD/Vol trong CSV là fraction; chênh lệch CAGR trong comparisons/CI là điểm phần trăm. Đây là mở rộng trên holdout đã quan sát, không phải prospective preregistration hay alpha/live-performance claim.
