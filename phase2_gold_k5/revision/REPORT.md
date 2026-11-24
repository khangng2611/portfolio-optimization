# Đối soát giá SJC và kiểm định lại view GOLD–K5

Ngày 24/11/2026 · Nghiên cứu Phase 2 · 641 lợi suất ngoài mẫu lịch sử, từ 02/10/2023 đến 29/04/2026.

**Kết luận.** Trên chuỗi đối soát, B2 có Sharpe sau phí 1,247. Thêm view GOLD–K5 trực tiếp đưa Sharpe xuống 1,019, chênh lệch −0,228. Thí nghiệm dừng trước bước shadow mode. View GOLD–K5 suy ra từ dự báo riêng đạt Sharpe 1,904 và là ứng viên cho một phép kiểm định độc lập tiếp theo.

## Dữ liệu nào thay đổi?

Sản phẩm mục tiêu của cả ba phiên bản là vàng miếng SJC loại 1 lượng, 10 lượng, 1 kg tại TP.HCM. Giá mua là giá đơn vị kinh doanh mua vào, dùng khi danh mục bán vàng. Giá bán dùng khi danh mục mua. Số liệu giá trong báo cáo tính theo triệu đồng/lượng.

- **Bản đóng băng Phase 1.** Hai khoảng có cùng cặp giá trong 109 và 340 ngày lịch. Riêng ngày 24/02/2026, việc ghi nhận lại giá làm trung điểm mua – bán tăng 90,33%. [Đối chuẩn trước khi sửa](../README.md)
- **Bản GiaVang.TV tải lại.** Đủ 77 tháng và 2.343 ngày lịch. Có 351 ngày thay đổi cặp giá so với bản đóng băng, gồm 236 phiên thị trường. Trong đoạn 340 ngày, bản mới có 197 cặp giá phân biệt. Giá mua/bán ngày 23 và 24/02/2026 đều là 181,6/184,6, đưa mức thay đổi trung điểm ngày 24/02 về 0%. Đoạn 109 ngày từ 02/12/2024 đến 20/03/2025 vẫn hiện 82,8/85,3. Trong 109 bảng chi tiết từng ngày có 99 bảng thiếu dòng SJC. [So sánh từng ngày](snapshot/day_comparison.csv) · [Bảng chi tiết các khoảng đứng giá](snapshot/residual_flat_period_checks.csv) · [Bảng tháng GiaVang.TV](https://giavang.tv/lich-su/2026/2)
- **Chuỗi đối soát nhiều nguồn.** Từ 31/12/2024 đến 30/04/2026, dùng đủ 486 giá chốt ngày hai chiều đúng sản phẩm và địa bàn của iGold. Trong đó 405 cặp khớp bản GiaVang.TV mới. Ngày 20/03/2025, iGold ghi 97,8/99,8. Sang 21/03, cặp giá là 94,7/97,7, tương ứng trung điểm giảm 2,63%, trong khi bảng tháng ghi tăng 14,46%. Trước thời điểm iGold có dữ liệu, ưu tiên cặp giá cuối cùng trong ngày của Webgia khi có bảng SJC TP.HCM hoặc bản tin chốt phiên của VietnamNet xác nhận. Sau khi phát hiện bảng tháng sai, nếu bảng tiếp tục lặp lại cặp giá đó thì dùng giá xác nhận gần nhất để định giá vị thế và chặn khớp lệnh trong cả hai kịch bản. [Quy tắc chọn nguồn](alternate/source_policy.md) · [Nguồn và tuổi báo giá từng ngày](alternate/provenance.csv) · [Lịch sử iGold](https://igoldvn.com/lich-su-gia-vang)

Chuỗi cuối có 1.789 ngày lấy từ GiaVang.TV, 486 từ iGold, 45 từ hai nguồn Webgia và VietnamNet cùng xác nhận và 23 ngày dùng giá đã quan sát trước đó. Trong 45 ngày đối chiếu báo chí, 37 ngày có nguồn ghi rõ giá chốt phiên, 8 ngày dùng quan sát trong ngày. Đã loại hai cặp giá có bản tin hôm sau ghi giá bán khác. Webgia thiếu nhãn chi nhánh và quy cách trên bảng lịch sử, còn bảng tin SJC TP.HCM có thể thiếu mã quy cách. Những quan sát này có độ chắc chắn thấp hơn chuỗi iGold ghi rõ cả hai. [Bằng chứng từng nguồn](verification/README.md) · [Hai cặp giá mâu thuẫn](verification/manual_conflicts.csv)

Trong đoạn 109 ngày, chuỗi cuối dùng 80 ngày iGold, 15 ngày Webgia và VietnamNet cùng xác nhận, cùng 14 ngày định giá theo quan sát trước. Có 57 cặp giá phân biệt. Trên toàn bộ lịch, 23 ngày định giá theo quan sát trước có tuổi giá tối đa 4 ngày lịch, rơi vào 10 phiên và 2 ngày thực thi theo lịch. Trên 127 dự báo tương đối hồi cứu có thể chấm điểm, 3 nhãn có ít nhất một đầu kỳ hoặc cuối kỳ là giá được giữ lại. [Dữ liệu theo ngày](alternate/provenance.csv)

## Cách so sánh

Giữ lịch chọn năm cổ phiếu K5, mô hình XGBoost, lịch retrain 10 phiên, chân trời dự báo 5 phiên và hai cửa sổ đánh giá đã đăng ký. Với mỗi chuỗi giá, dựng lại dữ liệu thông tin GOLD theo giả định D+1, nhãn, dự báo, confidence, ma trận hiệp phương sai, prior và posterior Black–Litterman, tỷ trọng mục tiêu và NAV. Cùng một chuỗi giá áp cho cả đối chứng lẫn các nhánh thêm view, kể cả giai đoạn hình thành vị thế trước khi chấm điểm. K5 và dự báo gốc từng cổ phiếu lấy từ bản Phase 1. Giá vàng có thể ảnh hưởng confidence của các view cổ phiếu qua biến động thị trường. [Protocol](../protocol.json) · [Phạm vi đợt đối soát](scope.md) · [Mã dựng lại đối chứng](rebuild.py)

B1 dùng Black–Litterman với prior. B2 thêm các view cổ phiếu của Phase 1. View tuyệt đối dự báo lợi suất GOLD. View tương đối **trực tiếp** dùng XGBoost để dự báo lợi suất GOLD trừ lợi suất rổ K5. View tương đối **suy ra** lấy dự báo GOLD trừ trung bình năm dự báo cổ phiếu. Phép so sánh chính đã khóa là B2 thêm view trực tiếp so với B2. Cả hai định giá vàng ở trung điểm, khớp theo đúng chiều bid/ask và tính phí 10 điểm cơ bản mỗi chiều cho tài sản ngoài vàng. Mỗi lần đổi tỷ trọng phải qua điều kiện lợi ích kỳ vọng so với chi phí. [Quy ước thực thi](../execution-policy.md)

Khi chạy lại theo đúng quy ước **gross của Phase 1**, Sharpe B1 lần lượt là 1,175 (bản đóng băng), 1,247 (GiaVang.TV tải lại) và 1,247 (chuỗi đối soát). B2 lần lượt là 1,367, 1,416 và 1,479. Trên chuỗi đối soát, lợi suất năm gross của B2 là 25,75%, so với 26,66% trên bản đóng băng, trong khi độ biến động năm giảm từ 13,71% xuống 12,05%. Các số gross này phục vụ đối chiếu với thí nghiệm cũ. Bảng tiếp theo dùng chung chi phí và quy tắc giao dịch của Phase 2. [Đối chứng B1 và B2 trước và sau đối soát](runs/20261124T090146690849Z/phase1_gross.csv)

Khi cho bộ dựng mới đọc lại giá đóng băng, 620 lần tính tỷ trọng và các bảng posterior B1/B2 khớp bản lưu. Khi thay bằng chuỗi đối soát, mỗi nhánh thay đổi tỷ trọng mục tiêu tại 73/310 ngày quyết định (ngưỡng sai khác 10⁻⁸). Các view cổ phiếu B2 giữ nguyên ma trận P và lợi suất dự báo Q, còn confidence thay đổi tại 7 ngày do dữ liệu biến động đầu vào thay đổi. [Kiểm thử phát lại bản đóng băng](test_rebuild.py) · [Đối chiếu confidence theo ngày](runs/20261124T090146690849Z/b2_regime_confidence.csv)

## Hiệu quả sau phí

| Nhánh Black–Litterman | Sharpe bản đóng băng | Sharpe GiaVang.TV tải lại | Sharpe chuỗi đối soát | Lợi suất năm trên chuỗi đối soát | Drawdown tối đa trên chuỗi đối soát | Số lần khớp mô phỏng |
|---|---:|---:|---:|---:|---:|---:|
| B1 | 1,108 | 1,253 | 1,256 | 22,24% | −11,04% | 19 |
| B2 | 1,050 | 1,239 | 1,247 | 19,73% | −7,28% | 7 |
| B2 + GOLD tuyệt đối | 0,777 | 0,984 | 1,330 | 23,69% | −9,78% | 46 |
| B2 + GOLD–K5 suy ra | 1,020 | 1,572 | 1,904 | 28,63% | −8,19% | 13 |
| B2 + GOLD–K5 trực tiếp | 1,112 | 0,724 | 1,019 | 20,15% | −10,23% | 8 |
| B1 + GOLD–K5 suy ra | 0,858 | 1,253 | 2,106 | 31,81% | −12,70% | 53 |
| B1 + GOLD–K5 trực tiếp | 0,689 | 0,687 | 1,130 | 20,69% | −13,40% | 46 |

Mỗi nhánh có 128 ngày thực thi theo lịch. Với chuỗi đối soát, 99 ngày có báo giá đạt quy ước khớp lệnh chính. B2 thực hiện 7 lần, B2 thêm view trực tiếp thực hiện 8 lần. Lợi suất năm của nhánh trực tiếp cao hơn B2 khoảng 0,42 điểm phần trăm nhưng độ biến động năm tăng từ 10,19% lên 13,15% và drawdown sâu hơn 2,95 điểm phần trăm. Sharpe ròng vì vậy thấp hơn. [Chỉ tiêu đầy đủ và lưới phí](runs/20261124T090146690849Z/metrics.csv) · [Giao dịch mô phỏng](runs/20261124T090146690849Z/trades.csv)

| Chênh lệch Sharpe của B2 + view trực tiếp so với B2 | Bản đóng băng | GiaVang.TV tải lại | Chuỗi đối soát |
|---|---:|---:|---:|
| Cả kỳ | +0,063 | −0,515 | **−0,228** |
| Khoảng tin cậy ghép cặp 95% | [−1,164 đến +1,014] | [−1,410 đến +0,331] | [−1,225 đến +0,671] |
| Đến hết 31/12/2024 | −0,505 | −0,505 | −0,487 |
| Từ 01/01/2025 | +0,512 | −0,270 | +0,240 |

Khoảng tin cậy dùng bootstrap ghép cặp trên 641 lợi suất ngày với 1.000 lần lấy mẫu theo khối 10 phiên. Trên cả hai bản giá mới, nhánh trực tiếp hụt tiêu chí Sharpe ròng dương cả kỳ. Trên chuỗi đối soát, hiệu ứng cũng trái dấu giữa hai cửa sổ đã khóa. Khoảng tin cậy còn rộng nên mẫu lịch sử cho phép cả khả năng có lợi lẫn gây hại. [Bản đóng băng](../runs/20261124T083539735869Z/paired.csv) · [GiaVang.TV tải lại](runs/20261124T085618964318Z/paired.csv) · [Chuỗi đối soát](runs/20261124T090146690849Z/paired.csv)

![Trung điểm giá SJC trên ba chuỗi lịch sử và chênh lệch Sharpe của view trực tiếp](doi-soat-sjc.png)

### Dự báo và kết quả thăm dò

Trên 127 dự báo 5 phiên có nhãn đã đáo hạn, mô hình trực tiếp đạt RMSE 3,86 điểm phần trăm trên chuỗi đối soát. Dự báo chênh lệch bằng 0 đạt 3,70 điểm phần trăm, còn cách suy ra từ dự báo từng tài sản đạt 3,77 điểm phần trăm. Tỷ lệ đúng dấu tương ứng của view trực tiếp và view suy ra là 49,6% và 48,0%. Với GOLD tuyệt đối, RMSE là 2,99 điểm phần trăm so với 2,95 của dự báo lợi suất bằng 0. [Chỉ tiêu dự báo](runs/20261124T090146690849Z/forecast_metrics.csv)

**Hướng đáng nghiên cứu tiếp là view tương đối suy ra từ dự báo từng tài sản.** Với chuỗi đối soát, B2 thêm view này tăng Sharpe 0,656 so với B2, với chênh lệch +0,740 và +0,591 ở hai cửa sổ. Hiệu ứng cả kỳ là +0,333 trên GiaVang.TV tải lại và −0,029 trên bản giá đóng băng. Khoảng tin cậy thăm dò 95% trên chuỗi đối soát là [−0,311 đến +1,526], chưa hiệu chỉnh cho số nhánh đã so sánh. Turnover năm tăng từ 0,56 lên 1,73 và RMSE vẫn cao hơn dự báo 0. Đây là giả thuyết cho thí nghiệm kế tiếp với B2 làm đối chứng và dữ liệu tương lai độc lập. [So sánh thăm dò đã ghép cặp](derived_exploratory.csv)

### Độ nhạy với khớp lệnh và phí

Nếu cho phép khớp cả báo giá theo ngày có giá bán đứng yên nhưng tiếp tục chặn giá do nghiên cứu tự giữ lại, chênh lệch Sharpe của view trực tiếp là −0,237 [−1,251 đến +0,661] trên chuỗi đối soát. Khi thay phí ngoài vàng từ 10 lên 25 hoặc 50 điểm cơ bản, chênh lệch lần lượt thành +0,638 và +0,607. Mức phí cũng tác động đến quyết định có giao dịch của từng danh mục. Các chênh lệch này vì thế bao gồm cả ảnh hưởng của việc thay đổi lịch giao dịch. [Độ nhạy với báo giá](runs/20261124T090146690849Z/dated_quotes/paired.csv) · [Lưới phí](runs/20261124T090146690849Z/metrics.csv)

## Quyết định và giới hạn sử dụng

**Giữ view GOLD–K5 trực tiếp ở phạm vi nghiên cứu.** Chênh lệch Sharpe sau phí âm trên cả hai chuỗi cập nhật, và hai cửa sổ của chuỗi đối soát cho kết quả trái dấu. Theo tiêu chí đã khóa, đợt này dừng trước bước chạy ngầm (*shadow mode*). Ứng dụng tiếp tục dùng luồng đề xuất Phase 1. Trong báo cáo Phase 2, có thể dùng thí nghiệm này để trình bày ảnh hưởng của chất lượng dữ liệu vàng tới kết luận về phân bổ tài sản, cùng kết quả thăm dò của view suy ra.

Cả hai chuỗi được dựng từ nguồn tải hồi cứu. D+1 là thời điểm giả định dữ liệu có thể được sử dụng. Dấu thời gian trên bản tin hoặc sự trùng khớp của hai nguồn chưa xác nhận thời điểm công bố lần đầu, thanh khoản, khối lượng hay giá khớp thực tế. Trước iGold có 1.241 phiên thị trường nằm ngoài phạm vi nguồn này. Với ứng dụng, còn phải xác nhận hiệu quả trên rổ người dùng chọn và cách phối BL–MVO của HYBRID. Protocol xác nhận yêu cầu ít nhất 60 quyết định ghép cặp đã ghi trước giao dịch và đáo hạn, kiểm tra qua 3 khối 20 quyết định. Các quan sát hồi cứu trong báo cáo đóng góp 0 quyết định cho mốc này. [Tiêu chí đã đăng ký](../protocol.json)

## Tái lập

Từ thư mục gốc, có thể dựng lại hai phiên bản giá từ các tệp đã lưu, rồi tái chạy theo từng manifest bên dưới.

```sh
venv/bin/python -B -m phase2_gold_k5.revision.recover
venv/bin/python -B phase2_gold_k5/revision/verification/compare.py
venv/bin/python -B -m phase2_gold_k5.revision.alternate build
venv/bin/python -B -m phase2_gold_k5.revision.study --feed snapshot --repeat phase2_gold_k5/revision/runs/20261124T085618964318Z
venv/bin/python -B -m phase2_gold_k5.revision.study --feed alternate --repeat phase2_gold_k5/revision/runs/20261124T090146690849Z
```

[Manifest GiaVang.TV tải lại](runs/20261124T085618964318Z/manifest.json) · [Lượt lặp GiaVang.TV](runs/20261124T085832420279Z/manifest.json) · [Manifest chuỗi đối soát](runs/20261124T090146690849Z/manifest.json) · [Lượt lặp chuỗi đối soát](runs/20261124T090419955677Z/manifest.json) · [Biên bản kiểm tra kết quả và hash](verification.json)
