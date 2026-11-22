# Báo cáo thí nghiệm bổ sung C
C1: đối chứng tỷ trọng cố định khả thi · C2: thẩm định nguồn chỉ số tổng thu nhập

Ngày thực hiện: 04/11/2026. Phiên bản C-v1. Mã chạy chính: extensions-C-20261104T210906; chạy lặp: extensions-C-20261104T211105. Báo cáo độc lập với việc chỉnh sửa bản thảo A+B.

## 1. Kết luận chính và phạm vi

C1 đã hoàn tất trên đúng lịch và danh mục bảy công cụ của B1/B2. Quy tắc đơn giản VFF 30%, mỗi cổ phiếu trong năm mã được chọn và GOLD 11,6667% tạo kết quả OOS gần B1: CAGR 23,66% so với 23,49%; Sharpe 1,172 so với 1,175. B2 có Sharpe gross cao hơn, nhưng lợi thế quan sát được nhạy với chi phí do turnover lớn. Các khoảng tin cậy chênh lệch đều chứa 0; chưa đủ bằng chứng xác định hướng hiệu ứng trong tổng thể.

C2 hoàn tất phần tìm nguồn và đánh giá tính khả thi theo điều kiện dừng của đề bài. Chưa có chuỗi chỉ số tổng thu nhập hằng ngày đáp ứng đồng thời yêu cầu dữ liệu, vintage và quyền sử dụng. Vì vậy không tính thành tích chỉ số và không đưa ra kết luận vượt thị trường. Đây là thí nghiệm chưa chạy số liệu, không phải kết quả chỉ số bằng 0. C3–C6 chỉ có đề cương, chưa triển khai.

C1 trả lời giá trị bổ sung của cách phân bổ, với bộ chọn Proposed K5 được giữ cố định. Nó không kiểm định riêng hiệu quả của bộ chọn cổ phiếu, không phải chiến lược mua và giữ vô điều kiện, và không xác lập alpha. Giai đoạn OOS này đã được xem trong dự án trước đây; C là mở rộng sau thiết kế trên holdout đã quan sát, không phải OOS độc lập mới hay đăng ký trước mang tính triển vọng.

## 2. Dữ liệu kế thừa và giao thức cố định

Giữ nguyên baseline availability-observed-contract-20261012T233110 của Step 1 và core-evidence-20261023T211011 của Step 2. Các snapshot đầu vào được đối chiếu SHA256 trước/sau chạy; B1/B2 được dựng lại từ tỷ trọng đã lưu, không tối ưu lại và không huấn luyện ML. Tất cả chỉ số và bốn kịch bản chi phí B1/B2 khớp hồ sơ đóng băng trong sai số dưới 1e-10.

IS: mốc NAV 18/02/2020, 906 return đến 29/09/2023. OOS: mốc NAV 29/09/2023, 641 return từ 02/10/2023 đến 29/04/2026. Giữ đường nắm giữ liên tục qua ranh giới IS/OOS; chỉ chuẩn hóa NAV từng kỳ khi báo cáo. Tái cân bằng mỗi năm phiên, chọn lại theo lịch Proposed K5 đã lưu; toàn mẫu có 78 trạng thái chọn và 310 sự kiện giao dịch.

Giao thức protocol_frozen.md và mã nguồn được lưu/hash trước khi tính kết quả C1. Quy tắc, cadence, lưới phí và bootstrap seed 20261104 không được điều chỉnh sau khi thấy thành tích. Hai lượt chạy độc lập cho kết quả giống từng byte ở 12 file CSV số liệu. Các bổ sung trình bày và kiểm thử C2 về sau được ghi riêng trong publication_manifest.json, không thay bản snapshot của C1.

Dữ liệu định giá có 30 cổ phiếu cố định cộng GOLD và VFF. Cổ phiếu dùng giá điều chỉnh của KBS; không tự cộng thêm cổ tức. Chưa có lịch sử revision/corporate actions đủ để xác nhận total return của từng mã. GOLD là giá bán SJC-HCM lưu trữ; VFF là NAV FMarket product 21. Mốc công bố lịch sử thực tế còn thiếu; kế thừa ledger và giả định availability đã chấp nhận, không gán ngày công bố mới. C1 chỉ có ý nghĩa có điều kiện theo hợp đồng proxy này, không chứng nhận dữ liệu point-in-time hoàn chỉnh hay khả năng khớp lệnh.

## 3. C1 được hiện thực như thế nào

Tại quyết định t, lấy trạng thái Proposed K5 gần nhất có selection_date không muộn hơn t và history_end trước t. Đặt VFF = 0,30; mỗi cổ phiếu được chọn và GOLD = 0,70/6; mọi mã còn lại bằng 0. Tổng trọng số bằng 1, không bán khống, không mã nào quá 0,50 và nhóm ngoài VFF bằng 0,70, dung sai 1e-8. Mỗi menu còn được kiểm tra trực tiếp với audit B1 và B2 ở cùng ngày.

Vị thế cũ nhận biến động t→t+1 trước khi thực hiện target tại giá đóng cửa giả định t+1. Vị thế mới chỉ nhận return t+1→t+2. Giữ số đơn vị tài sản và cho trọng số trôi giữa các lần giao dịch; xử lý mua/bán trên hợp 32 mã nên không bỏ sót mã rời danh mục. Tính TO sự kiện bằng nửa tổng trị tuyệt đối chênh lệch target với trọng số trước giao dịch. TO năm = 252 × tổng TO / N, loại lần cấp vốn đầu. Chi phí lần đầu chỉ tính trong IS; không cấp vốn lại ở đầu OOS; giao dịch cuối kỳ vẫn bị tính phí mà không thêm return tương lai.

Quy ước chỉ số: CAGR = NAV cuối^(252/N) − 1; biến động năm dùng độ lệch chuẩn mẫu ddof=1 nhân căn 252; Sharpe dùng rf ngày = 1,06^(1/252) − 1. MDD có dấu âm. TO 0,760 nghĩa là khoảng 0,760 lần giá trị danh mục được thay đổi một chiều trong một năm theo quy ước này, không phải 0,760%.

## 4. Kết quả gross: C1 so với B1/B2

OOS, trước chi phí, cùng 641 return và cùng mốc NAV = 1:

| Nhánh | NAV | CAGR % | Vol % | Sharpe | MDD % | TO/năm |
| --- | --- | --- | --- | --- | --- | --- |
| C1 fixed rule | 1.7164 | 23.66 | 13.97 | 1.172 | -10.18 | 0.760 |
| B1 prior-only | 1.7104 | 23.49 | 13.81 | 1.175 | -10.26 | 0.851 |
| B2 BL + ML | 1.8244 | 26.66 | 13.71 | 1.367 | -9.51 | 7.975 |

C1 hơn B1 khoảng 0,168 điểm phần trăm CAGR nhưng thấp hơn 0,0025 Sharpe. TO C1 thấp hơn B1 khoảng 10,7%. B2 hơn C1 khoảng 3,002 điểm phần trăm CAGR và 0,195 Sharpe gross, đồng thời TO cao khoảng 10,5 lần. Đây là quan sát trên mẫu cụ thể, không chứng minh mức tăng kỳ vọng trong tương lai.

IS, cùng 906 return:

| Nhánh | NAV | CAGR % | Vol % | Sharpe | MDD % | TO/năm |
| --- | --- | --- | --- | --- | --- | --- |
| C1 fixed rule | 1.7751 | 17.31 | 14.15 | 0.787 | -17.66 | 1.434 |
| B1 prior-only | 1.7910 | 17.60 | 14.40 | 0.794 | -17.98 | 1.536 |
| B2 BL + ML | 1.6603 | 15.14 | 15.44 | 0.614 | -18.12 | 7.907 |

Trong IS, C1 thấp hơn B1 một ít về CAGR/Sharpe; B2 cũng không đứng đầu. Cả kết quả thuận lợi và bất lợi được giữ nguyên. Không chọn lại trọng số C1 hoặc mô hình B2 để cải thiện xếp hạng.

![Hình 1. NAV gross OOS, chuẩn hóa tại 29/09/2023; C1 và B1 gần nhau.](figures/C1_OOS_wealth.png)

## 5. Độ tập trung và cơ chế phân bổ

| Nhánh | HHI target | HHI daily | Số vị thế hiệu dụng |
| --- | --- | --- | --- |
| C1 fixed rule | 0.171667 | 0.171594 | 5.828 |
| B1 prior-only | 0.171801 | 0.171719 | 5.824 |
| B2 BL + ML | 0.272234 | 0.272604 | 3.892 |

HHI target = tổng bình phương trọng số ở lần thực hiện. Với VFF ít nhất 30% và sáu phần còn lại chia đều, mức HHI nhỏ nhất là 0,30² + 6 × (0,70/6)² = 0,1716667. Quy tắc C1 đạt mức này ở mỗi target. HHI daily tính trên trọng số đã trôi ở đầu ngày return; có thể thấp hơn mốc lý thuyết của target vì VFF tạm trôi xuống dưới 30% giữa các lần tái cân bằng. Số vị thế hiệu dụng là trung bình của 1/HHI theo ngày đã đầu tư, không phải 1 chia HHI trung bình.

Khoảng cách L1 giữa target C1 và B1 trung bình OOS là 0,021493, tối đa 0,038344; nghĩa là tổng độ lệch tuyệt đối khoảng 2,149 điểm phần trăm trọng số, tương đương khoảng 1,075% tái phân bổ một chiều giữa hai target đầy đủ đầu tư. Với B2, L1 trung bình là 0,506589. Hai target B1/C1 gần nhau nhưng không trùng; HHI gần nhau cũng không tự chứng minh cùng danh mục hoặc cùng lợi nhuận.

Kết quả này làm hẹp cách diễn giải B1: kết quả gross tốt không tự chứng minh prior BL đã tạo thêm giá trị kinh tế rõ rệt so với một quy tắc khả thi đơn giản trên cùng menu. Đồng thời, C1 vẫn thừa hưởng chọn mã Proposed K5 và cơ hội GOLD/VFF; không thể dùng nó để kết luận bộ chọn hoặc tài sản ngoài cổ phiếu không cần thiết.

![Hình 2. Tỷ trọng lớp tài sản đã trôi ở đầu return; nét chấm là target VFF tại ngày thực hiện.](figures/C1_class_weights.png)

![Hình 3. Lịch thành viên Proposed K5 cố định theo quyết định; vạch cam là ranh giới OOS.](figures/C1_dated_membership.png)

## 6. Chi phí giả định và khoảng bất định

Chi phí theo mỗi phía mua hoặc bán là 0/10/25/50 bps; 1 bps = 0,01 điểm phần trăm. Mỗi sự kiện áp hệ số (1 − c × tổng absolute traded weights) lên tăng trưởng gross trong ngày thực hiện. Đây là xấp xỉ kế thừa trên giao dịch gross, không phải mô phỏng holdings chính xác sau phí hoặc phí quỹ, spread vàng và lịch nhận lệnh thực tế.

| Nhánh | S 0 bps | S 10 bps | S 25 bps | S 50 bps | NAV 50 bps |
| --- | --- | --- | --- | --- | --- |
| C1 fixed rule | 1.172 | 1.161 | 1.145 | 1.117 | 1.6835 |
| B1 prior-only | 1.175 | 1.162 | 1.144 | 1.112 | 1.6738 |
| B2 BL + ML | 1.367 | 1.251 | 1.075 | 0.782 | 1.4891 |

Ở 10 bps, B2 có Sharpe 1,251, cao hơn mức khoảng 1,16 của C1/B1. Ở 25 và 50 bps, C1/B1 có Sharpe cao hơn B2. Trong bốn kịch bản đã định, C1 chỉ nhỉnh hơn B1 về Sharpe ở 25 và 50 bps; chênh lệch nhỏ và không được biến thành tuyên bố vượt trội chắc chắn. Không suy ra ngưỡng hòa vốn chính xác từ vài điểm lưới; không dùng kết quả để chọn chi phí có lợi.

![Hình 4. Sharpe OOS sau chi phí giả định; B2 nhạy với turnover hơn C1/B1.](figures/C1_cost_sensitivity.png)

Bootstrap ghép cặp gross OOS dùng moving blocks không vòng, độ dài 10 ngày, 1.000 mẫu lặp, seed 20261104. Trong mỗi cặp, cả hai chuỗi lấy cùng chỉ số ngày; chỉ lấy mẫu return đã lưu, không huấn luyện lại. CI là percentile 95%, CAGR chênh lệch tính bằng điểm phần trăm.

| Cặp | Chỉ số | Hiệu ứng | CI 95% |
| --- | --- | --- | --- |
| C1 − B1 | CAGR (điểm %) | +0.168 | [-0.607; +1.277] |
| C1 − B1 | Sharpe | -0.002 | [-0.034; +0.030] |
| C1 − B2 | CAGR (điểm %) | -3.002 | [-11.436; +6.015] |
| C1 − B2 | Sharpe | -0.195 | [-0.701; +0.298] |

Tất cả CI chứa 0. Chưa đủ bằng chứng xác định hướng hiệu ứng; không đồng nghĩa các phương pháp tương đương và không xác nhận alpha. CI có điều kiện theo cửa sổ, universe, selector và nguồn dữ liệu cố định; không bao quát rủi ro chọn thiết kế sau khi thấy holdout, survivorship hoặc vintage nguồn chưa hoàn chỉnh.

## 7. C2: kết quả thẩm định nguồn và điều kiện dừng

Ứng viên đã định trước là VN30TRI chính thức, sau đó mới xét một biến thể VN-Index total return nếu có thể xác minh. Factsheet HOSE tháng 06/2026 xác nhận VN30TRI là chỉ số tổng thu nhập cuối ngày bằng VND. Quy tắc HOSE v1.2 lưu trên SSC, mục 5A, mô tả tái đầu tư cổ tức tiền mặt theo ex-date. Đây là xác minh danh tính/định nghĩa, chưa phải bộ lịch sử hằng ngày có vintage và quyền sử dụng phù hợp.

Trang TradingView cho thấy mã HOSE:VN30TRI nhưng chưa cung cấp gói daily được chấp nhận; trang CEIC đã xem là chuỗi tháng; tài liệu market-breadth của FiinQuant nhận biết nhóm VN30TRI nhưng endpoint này không phải chuỗi close lịch sử. Không nội suy dữ liệu tháng, không khai thác giao thức biểu đồ riêng, và không thay VNINDEX giá thành total return. Chi tiết nguồn, URL và phần còn thiếu được ghi tại C2_source_feasibility.md và C2_source_audit.json.

Trạng thái C2: NOT_RUN_SOURCE_GATE_NOT_MET. Có 0 daily observation được chấp nhận; 641 ngày portfolio chưa thể đánh giá với chỉ số, không phải đã xác minh 641 ngày thị trường mất dữ liệu. Bảng C2 chỉ chứa trạng thái với ô metric trống; file daily chỉ có header. Không có biểu đồ so sánh ba đường hay kết luận vượt thị trường.

Để chạy tiếp cần daily level từ mốc 29/09/2023 đến 29/04/2026, index_date/index_level/vendor_record_date, phương pháp cổ tức/corporate actions, lịch thay đổi/vintage, thời điểm retrieval và xác nhận quyền nghiên cứu. Xin riêng quyền phát hành lại raw. Pipeline đã kiểm thử việc không nối return qua ngày thiếu và tính lại B1/B2 trên cùng mẫu liên tục ngắn hơn nếu cần. Chỉ số cổ phiếu vẫn khác tập khả thi của danh mục có VFF tối thiểu 30%; mọi so sánh sau này mang tính mô tả.

## 8. Kiểm chứng, giới hạn và nội dung xin ý kiến

Toàn bộ 310 target C1 thỏa ràng buộc; menu khớp B1/B2. Dựng lại NAV bằng số đơn vị tài sản độc lập cho sai số tối đa 8,66e-14. Identity traded notional = 2 × TO giữ đúng; các tests bao gồm mã vào/ra, execution-day jump, phí cấp vốn ban đầu/cuối kỳ, ví dụ metric tính tay và bootstrap ghép cặp. Kết quả test đầy đủ và hashes nằm trong validations.md và các manifest. Báo cáo không thay thế kiểm tra quyền dữ liệu hoặc chứng nhận giao dịch thực.

| So sánh | Câu hỏi được đánh giá | Giới hạn nhận diện |
| --- | --- | --- |
| C1–B1 | Quy tắc cố định so với phân bổ prior BL, cùng selector/menu | Không tách giá trị của selector; không kiểm định tương đương |
| C1–B2 | Quy tắc cố định so với toàn pipeline BL + ML | Không tách riêng đóng góp ML; cặp matched cho ML là B2–B1 |
| C2 chỉ số TR | Bối cảnh thị trường mô tả khi có nguồn hợp lệ | Khác lớp tài sản và ràng buộc; không suy ra alpha |

Các giới hạn còn nguyên: universe cố định 30 mã có survivorship risk; adjusted close là snapshot hồi cứu; publication vintage GOLD/VFF chưa xác minh hoàn chỉnh; GOLD/VFF là proxy định giá; chi phí chỉ là kịch bản; holdout đã quan sát. Không chỉnh sửa bằng chứng A+B để khắc phục các giới hạn này trong C.

Đề nghị giảng viên xem xét ba quyết định: (1) cập nhật diễn giải vai trò của prior BL trước đối chứng C1 gần B1; (2) quyết định nguồn/kinh phí/quyền truy cập VN30TRI để tiếp tục C2, hoặc chấp nhận feasibility stop; (3) chọn phạm vi C3/C4 nếu cần thêm kiểm định cơ chế. Không tái tối ưu B2 để bảo vệ kết quả cũ. C3–C6 có đề cương riêng trong optional_proposals.md và chưa được chạy.

Gói bằng chứng gồm source, snapshot mã C1, số liệu kết quả, biểu đồ, manifest/hash, tests và hướng dẫn tái chạy. Giá raw và lịch sử vendor giữ riêng ở inputs/ trên máy, không đưa vào Drive/ZIP khi chưa có quyền phân phối. Người tái chạy cần được cấp input pack hợp lệ; bộ kết quả công bố không tự nó cung cấp toàn bộ raw để chạy độc lập.

## 9. Tài liệu nguồn

Nguồn nội bộ: experiment_1.md (26/10/2026); protocol_frozen.md và baseline_manifest.json; bằng chứng Step 1/Step 2 theo hai run ID ở mục 2; toàn bộ kết quả C1 theo run ID đầu báo cáo. Tất cả bản dùng tính toán được nhận diện bằng SHA256.

Nguồn ngoài cho quyết định C2 (truy cập 04/11/2026): [1] HOSE, Factsheet market-cap indices 06/2026, staticfile.hsx.vn/Uploads/UploadDocuments/2468981/Form_Factsheet_MCIndices_VN_T06.2026.pdf. [2] HOSE index rules v1.2, SSC, dDocName APPSSCGOVVN162095654, mục 5A. [3] TradingView, HOSE-VN30TRI. [4] CEIC, Ho Chi Minh Stock Exchange Index: Total Return: VN30, monthly dataset. [5] FiinQuant, tài liệu hàm thống kê độ rộng thị trường. URL đầy đủ được giữ trong C2_source_feasibility.md để kiểm tra trực tiếp.
