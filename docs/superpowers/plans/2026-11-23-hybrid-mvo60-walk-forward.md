# Khóa phương án HYBRID MVO 60% và kỳ kiểm định độc lập

Khóa ngày 23/11/2026, giờ Việt Nam, trước khi quan sát kết quả của kỳ mới.
Mã phương án nghiên cứu `hybrid-growth-normal-mvo60-v1`. Trạng thái kiểm định **chờ dữ liệu**.

## Phương án và cổng định lượng

Tỷ phần MVO trong phép phối `α × w_MVO + (1 − α) × w_BL_ML` được cố định như sau.

| Hồ sơ | Bình thường | Căng thẳng | Khủng hoảng |
| --- | ---: | ---: | ---: |
| Thận trọng | 45% | 22,5% | 7,5% |
| Cân bằng | 60% | 30% | 10% |
| Tăng trưởng | 60% | 37,5% | 12,5% |

Ứng viên hạ duy nhất tỷ phần MVO Tăng trưởng ở regime bình thường từ 75% xuống 60%.
Đối chứng chính dùng 60% / 30% / 10% theo regime cho cả ba hồ sơ. Báo thêm BL_ML
và bảng phối v1 trên cùng mẫu để thấy tác động của thay đổi. Mọi nhánh dùng chung
hệ số ngại rủi ro 6 / 3 / 1,5 theo hồ sơ, với sàn 5 trong khủng hoảng, tổng tỷ
trọng 100%, không bán khống, cap 50% mỗi mã, sàn VFF 15% và cap ngoài VFF 70%.

Giữ universe 30 cổ phiếu của baseline cùng GOLD, VFF và lịch phiên VNINDEX.
MVO dùng toàn rổ. BL_ML dùng K5 động và GOLD/VFF. Giữ lịch quyết định mỗi 5
phiên, tái chọn K5 mỗi 20 phiên, refit XGBoost mỗi 10 phiên, mục tiêu dự báo 5
phiên, điều kiện regime và tham số mô hình trong [cấu hình đã đóng băng](../../../outputs/step1/readiness_20261012/runs/availability-observed-contract-20261012T233110/run_config.json).
Dùng lịch 20 phiên cho trung bình và covariance trong [replay HYBRID](../../../scripts/eval_hybrid_policy.py).
Các nhánh dùng cùng panel, views, regime, lịch quyết định và giá định giá.

Mỗi phương án bắt đầu từ tiền mặt, ra quyết định sau đóng cửa và khớp giả định
tại giá đóng cửa phiên kế tiếp. Tỷ trọng mới hưởng lợi suất từ phiên sau ngày
khớp. Giữ số lượng tài sản giữa các lần cân lại. Phí là **10 bps trên một đơn
vị turnover một chiều**, tính cả lần vào từ tiền mặt. Dùng giá điều chỉnh KBS,
giá bán SJC HCM và NAV VFF theo quy ước nguồn đã ghim. Đây là giá đại diện cho
định giá giả lập.

Chấm lợi suất ròng cùng ngày, biến động năm với 252 phiên, drawdown tối đa và
turnover một chiều. Mỗi hồ sơ phải đạt cả ba ngưỡng so với đối chứng chính.

| Chỉ số | Ngưỡng |
| --- | ---: |
| Mức tăng biến động năm | ≤ 2 điểm phần trăm |
| Mức tăng drawdown tối đa | ≤ 3 điểm phần trăm |
| Turnover ứng viên so với đối chứng | ≤ 1,25 lần |

Chấm một lần sau khi đóng kỳ. Công bố số phiên và số lần cân lại theo regime,
các lần bỏ lỡ, chênh lệch tỷ trọng và lợi suất ròng. Kết quả thiếu bằng chứng
timing hoặc thiếu kỳ bình thường có tỷ trọng Tăng trưởng thay đổi so với v1
là chưa đủ để quyết định mở cổng. Nếu một ngưỡng trượt, kỳ này được ghi nhận
đã sử dụng. Một phương án chỉnh sau đó cần kỳ độc lập khác.

## Kỳ walk-forward

Chọn kỳ theo dõi tiến về trước **24/11/2026–23/11/2027** theo giờ Việt Nam. Mốc
12 tháng được đặt trước để bao phủ một chu kỳ lịch đầy đủ. Quyết định đầu tiên
theo lịch nói trên rơi vào phiên VNINDEX đầu tiên từ ngày 24/11. Chấm lợi suất
đến phiên cuối cùng trong kỳ. Dữ liệu trước ngày bắt đầu chỉ dùng làm lịch sử
đầu vào. Model được huấn luyện cuốn chiếu đúng tại mỗi cutoff, với feature,
nhãn, validation và artifact model có thể đối chiếu với thời điểm ra quyết định.

Mỗi cutoff cần lưu timestamp thu thập thật, revision, hash nguồn và snapshot,
dữ liệu khả dụng, model artifact, views, K5, regime và thời điểm quyết định.
Dùng timestamp first-seen của hệ thống khi nguồn thiếu lịch sử công bố, giữ
nguyên điều đó trong provenance. Giá được quan sát muộn chỉ đi vào quyết định
sau khi khả dụng. Nếu thiếu đầu vào ở cutoff, cả hai phương án giữ vị thế
đang có ở lần quyết định đó và ghi lý do. Mọi khoảng thiếu giá định giá phải
được đối soát trước khi chấm. Không truy hồi bằng model hiện hành hay gán lại
giờ công bố từ ngày ghi trên giá/NAV.

| Kỳ đã rà | Bằng chứng và quyết định |
| --- | --- |
| Trước 01/10/2023 | 780 phiên đã dùng để chọn 60%. [Kết quả phát triển](../../../output/hybrid-20261123/research/development.json) |
| 01/10/2023–29/04/2026 | Holdout 641 phiên đã dùng để đánh giá v1. Hai lượt replay mới theo cùng một ledger. [Kết quả v1](../../../output/hybrid-20261122/quantitative.json) |
| Phần mở rộng tới 01/07/2026 | Đã có trong replay tháng 7 và báo cáo cũ. Ledger ghi các lần vào vị thế đến 26/06. VFF theo ngày định giá và GOLD có carry với thời điểm gốc chưa xác minh. [Audit dữ liệu](../../../outputs/step1/data_static/final_run_review.md) |
| Phần còn lại trước ngày khóa | Stack có snapshot thu thập từ tháng 11. Audit ghi nhận thiếu lịch sử revision/publication của provider và chỉ chứng minh các quyết định thực có receipt. Chưa tìm thấy ledger cuốn chiếu độc lập cho phần này. [Audit point-in-time](../../software/POINT_IN_TIME_AUDIT.md) |

Phiên cấu hình phát triển ghim trong [manifest](../../../output/hybrid-20261123/research/manifest.json).
Commit nền `ca0043b4a95c8d1fae0a5ec0f373377d307e00fb`. SHA-256 runner gốc
`cc2f98cf0c76a3c23ada257f4505757f5003158708b002235b1cbfd3e5fd49d0` và
kết quả phát triển `c117e0733f1392095693594f44e8dcee2ca2dc3b9316fece67981b8f01903807`.
Trước khi tính chỉ số cho kỳ mới, đóng băng input, code và môi trường chạy
trong manifest riêng. Runner Phase 1 cần bộ artifact có đúng dữ liệu và lịch
cho kỳ mới. Bản khóa này đăng ký phương án kiểm định, chưa khởi chạy thu thập.

## Điều kiện kiểm chứng trên ứng dụng

Cổng phát hành cần cả kết quả độc lập đạt ngưỡng và Quant trả READY cho MVO
cùng BL_ML trên snapshot đã công bố, với model đã duyệt khớp fit epoch và
training prefixes. Sau đó kiểm bằng hai danh mục test trên desktop 1440 px và
mobile 390 px. Mở đề xuất hết hạn, xem lại yêu cầu, xác nhận tính mới, đợi job
HYBRID thành công rồi chủ động chấp nhận. Đối chiếu tỷ trọng/vốn/ngày dữ liệu
của mục tiêu sau reload và trong lịch sử, truy lại snapshot/model từ receipt.
