# GOLD–K5 trong Phase 2 · Kết quả nghiên cứu hồi cứu

Từ 24/11/2026, stack local ghi thêm một bộ tỷ trọng thử nghiệm cho các đề xuất HYBRID đủ điều kiện. Nhánh này đánh giá view GOLD–K5 suy ra từ các dự báo từng tài sản trên rổ của mỗi danh mục. [Cách vận hành và kết quả kiểm tra trên ứng dụng](shadow/README.md)

**Cập nhật đối soát SJC ngày 24/11/2026.** Phần bên dưới lưu kết quả trên phiên bản giá ban đầu. Báo cáo đối soát trình bày kết quả chạy lại B1, B2 và các view GOLD trên hai phiên bản giá mới. [Báo cáo đối soát và quyết định cho Phase 2](revision/REPORT.md)

**Quyết định ngày 24/11/2026.** Giữ GOLD–K5 ở mức thử nghiệm. View trực tiếp cho chênh lệch Sharpe ròng +0,063 so với đối chứng chính. Khoảng tin cậy 95% từ −1,164 đến +1,014, hai cửa sổ đã định cho hiệu ứng trái dấu, và drawdown tăng độ sâu 3,71 điểm phần trăm. Lịch sử giá SJC có hai đoạn bất thường kéo dài. Bằng chứng hiện tại chưa đạt tiêu chí pilot. Nếu trích vào luận văn, kết quả này phù hợp phần thử nghiệm và giới hạn dữ liệu. [Đăng ký protocol](protocol.json) · [Quy ước thực thi](execution-policy.md) · [Chênh lệch và khoảng tin cậy](runs/20261124T083539735869Z/paired.csv)

## Câu hỏi và mẫu đánh giá

Khi đã có các view cổ phiếu, dự báo mức vượt trội của SJC so với năm cổ phiếu đại diện có giúp cải thiện quyết định phân bổ sau phí? Chạy cùng lịch Phase 1, tập khả thi, prior, covariance và bộ giải. Mỗi quyết định cố định K5 đã biết tại thời điểm t. Mục tiêu học là lợi suất SJC trừ lợi suất rổ K5 mua đều vốn trong kỳ từ close(t+1) tới close(t+6). Các mô hình có thể tái huấn luyện sau mỗi 10 phiên khi đủ nhãn đã công bố. Dùng hai seed XGBoost, giới hạn độ sâu 2 và 40 cây mỗi thành viên. Confidence sử dụng sai số dự báo trước đó đã đáo hạn. Năm cổ phiếu mang hệ số −0,2 mỗi mã, GOLD +1 và VFF 0 trong relative view.

Lịch sử nguồn có 1.568 phiên. Kỳ ghi điểm hồi cứu có 641 lợi suất ngày từ 02/10/2023 tới 29/04/2026, tiếp nối vị thế đã hình thành trước kỳ. Bộ mô phỏng giữ số đơn vị giữa hai lần giao dịch, định giá vàng ở trung điểm và khớp phần thay đổi vị thế theo đúng chiều mua/bán. Kịch bản chính thu phí 10 bps trên giá trị giao dịch mỗi phía đối với tài sản ngoài vàng. Gate so lợi ích kỳ vọng trong 5 phiên với chi phí chuyển đổi, đồng thời xét giới hạn và mã rời K5. Đây là kết quả nhánh BL của rổ nghiên cứu cố định theo lịch K5. Ứng dụng sử dụng rổ của nhà đầu tư và còn phối với MVO.

## Kết quả danh mục

| Nhánh | Sharpe ròng với gate | Drawdown tối đa | Turnover năm | Sharpe ròng khi bỏ gate | Sharpe ròng với gate nếu cho khớp mọi báo giá theo ngày |
|---|---:|---:|---:|---:|---:|
| B1 · BL chỉ dùng prior | 1,108 | −10,77% | 0,081 | 1,040 | 1,206 |
| B2 · BL + view cổ phiếu Phase 1 | 1,050 | −8,61% | 0,076 | 1,296 | 0,843 |
| B2 + view GOLD tuyệt đối | 0,777 | −13,63% | 1,435 | 0,701 | 0,721 |
| B2 + GOLD–K5 suy ra từ dự báo từng mã | 1,020 | −8,34% | 0,195 | 1,314 | 0,882 |
| B2 + GOLD–K5 dự báo trực tiếp | 1,112 | −12,32% | 0,371 | 0,702 | 0,902 |

Trong 128 ngày thực thi theo lịch của kỳ đánh giá, quy ước chính coi 44 ngày có thể khớp. Gate thực sự khớp **1 lần** cho B2 và **2 lần** cho B2 + view trực tiếp. Danh mục vẫn có vị thế từ trước kỳ đánh giá. Cách xử lý ngày ghi giá đứng yên ảnh hưởng mạnh đến số giao dịch và hiệu suất tuyệt đối. Nếu cho khớp tất cả báo giá theo ngày, số lần khớp tăng tương ứng lên 21 và 25. Chênh lệch Sharpe khi đó là +0,059 [−0,829; +0,793].

Trong hai cửa sổ định trước, chênh lệch Sharpe ròng chính là −0,505 từ đầu kỳ tới hết năm 2024 và +0,512 trong phần còn lại. Khi tăng chi phí ngoài vàng lên 25 hoặc 50 bps mỗi phía, hiệu ứng đổi dấu, lần lượt khoảng −0,062 và −0,068. Gate giảm turnover mạnh, nhưng với B2 đơn thuần Sharpe ròng giảm từ 1,296 xuống 1,050. Bằng chứng chưa đủ để áp dụng riêng gate này vào app. [Toàn bộ 7 nhánh và lưới chi phí](runs/20261124T083539735869Z/metrics.csv) · [Độ nhạy theo giá thực thi](runs/20261124T083539735869Z/dated_quotes/metrics.csv)

## Chất lượng dự báo và dữ liệu

Có 127 quyết định có đủ nhãn và confidence trong kỳ để chấm dự báo. Mô hình trực tiếp đoán đúng dấu chênh lệch 55,9% số lần, nhưng RMSE của chênh lệch 5 phiên là 9,35 điểm phần trăm, so với 9,24 cho dự báo chênh lệch bằng 0. Cách suy ra từ dự báo thành phần đạt RMSE 9,29 và đúng dấu 52,8%. Tương quan sai số giữa hai cách là 0,996 trên mẫu này. Hai cách cùng dự báo một biến đích có ngoại lệ rất lớn, nên hệ số này không đo độc lập thông tin kinh tế của hai tín hiệu. [Chấm điểm dự báo](runs/20261124T083539735869Z/forecast_metrics.csv) · [Sai số theo cặp](runs/20261124T083539735869Z/forecast_error_dependency.csv)

Nguồn SJC HCM lưu trữ có đủ cả giá mua và giá bán. Giá bán gốc khớp bộ định giá Phase 1 ở 1.568/1.568 phiên. Các cặp bid/ask sau giữ nguyên đến độ chính xác được nguồn công bố (giá trong bảng là triệu đồng/lượng).

| Khoảng ngày | Ngày lịch | Bid / ask | Thay đổi midpoint lần cập nhật kế tiếp |
|---|---:|---:|---:|
| 02/12/2024 – 20/03/2025 | 109 | 82,8 / 85,3 | +14,46% |
| 21/03/2025 – 23/02/2026 | 340 | 94,7 / 97,7 | +90,33% |

Thiếu bằng chứng rằng có thể giao dịch tại các giá này xuyên suốt hai khoảng. Quy ước thận trọng bỏ các lệnh đến hạn ở ngày archive gắn cờ giá đứng yên, nhưng giá định danh mục và nhãn huấn luyện vẫn chịu ảnh hưởng. Quy ước cho khớp mọi ngày là kịch bản độ nhạy. Cả hai cùng dựa trên chuỗi SJC này. Nguồn thứ hai trong repo chỉ khớp 114/1.568 giá bán theo ngày và cũng có ngày lặp giá. [Đối soát](runs/20261124T083539735869Z/replay.json) · [Dữ liệu từng ngày](runs/20261124T083539735869Z/reconcile.csv)

Phân tích bổ sung sau khi phát hiện chuỗi đứng giá cho thấy, trên 293 phiên trước tháng 12/2024, chênh lệch Sharpe của view trực tiếp là −0,542. Trong 303 phiên gồm hai đoạn đứng giá và lần cập nhật ngày 24/02/2026, chênh lệch là +0,546. Trong 45 phiên còn lại, chênh lệch là −0,070. Nếu chỉ bỏ lợi suất ngày 24/02/2026 khỏi chuỗi đã mô phỏng, chênh lệch cả kỳ tăng lên +0,253. Chính ngày nhảy giá có lợi cho B2. Các phép cắt này giữ lịch sử huấn luyện và vị thế ban đầu của mỗi đoạn, nên chỉ dùng để xem hiệu ứng nằm ở đâu. [Chi tiết chẩn đoán](diagnostics/20261124T083539735869Z/carry_diagnostic.csv)

![Báo giá SJC và hai danh mục ngoài mẫu](diagnostics/20261124T083539735869Z/gold_k5_evidence.png)

## Kiểm chứng và khả năng áp dụng

Đã dựng lại hai nhánh Phase 1 qua 620 lần giải, kiểm tra prior/posterior, target, turnover, lịch thực thi và NAV ngày. Sai số NAV tuyệt đối lớn nhất so với bản lưu là 4,45 × 10⁻¹⁶. Tệp nguồn, cấu hình và đầu vào Phase 1 được đọc từ vị trí gốc. Đầu ra Phase 2 nằm riêng theo lượt chạy. [Danh mục đầu vào, nguồn và hash](runs/20261124T083539735869Z/input_manifest.json) · [Bằng chứng từng lần tính](runs/20261124T083539735869Z/allocations.csv)

Chưa có quyết định nào được phát hành trước giao dịch theo protocol GOLD–K5 mới trong một kỳ xác nhận độc lập. File dự báo mang nhãn hồi cứu, có ngày phát hành giả định, thời điểm nhãn khả dụng, fit epoch, thành phần rổ và dấu thời gian chạy thực trong manifest. Trước khi dùng để xác nhận, cần đối soát nguồn bid/ask độc lập cho đoạn thiếu cập nhật, khóa phiên bản dữ liệu, huấn luyện lại rồi ghi dự báo theo thời gian thực trước từng lần giao dịch. Điều kiện tối thiểu đã đăng ký là 60 quyết định ghép cặp đã đáo hạn, kiểm tra độ ổn định qua ba khối và khoảng tin cậy dương. Độ khả thi của rổ do user chọn và phép phối HYBRID là kiểm tra riêng ở bước pilot. [Dự báo và thời điểm khả dụng](runs/20261124T083539735869Z/forecasts.csv)

## Tái lập

Từ thư mục gốc repository, dùng môi trường nghiên cứu đã cài và các snapshot có hash trong manifest. Hai lệnh chạy tạo thư mục kết quả mới. Bộ chấm điểm dùng Sharpe thường niên từ lợi suất vượt lãi suất phi rủi ro 6%/năm và bootstrap ghép cặp 1.000 lần với block 10 phiên.

```sh
venv/bin/python -B -m unittest discover -s phase2_gold_k5 -v
venv/bin/python -B -m phase2_gold_k5.run
venv/bin/python -B -m phase2_gold_k5.run --repeat phase2_gold_k5/runs/20261124T083539735869Z
```

Hai lượt độc lập khớp từng byte trên cả 24 CSV kết quả. 15 kiểm thử đã đạt; các hash đầu vào Phase 1 khớp sau khi chạy. [Biên bản xác minh](diagnostics/20261124T083539735869Z/verification.json) · [Manifest lượt chính](runs/20261124T083539735869Z/manifest.json) · [Manifest lượt lặp](runs/20261124T083813883338Z/manifest.json)
