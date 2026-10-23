# Step 1 — Báo cáo tóm tắt kết quả và hiện trạng

Cập nhật: **04/10/2026**. 

## 1. Kết quả chạy lại

Kỳ yêu cầu: **01/2020–04/2026**, chia IS/OOS tại **01/10/2023**, kết thúc đến hết **30/04/2026**. Phiên cuối có dữ liệu là **29/04/2026**.

- **IS:** NAV từ 11/02/2020–29/09/2023, gồm 911 return sau giai đoạn khởi tạo.
- **OOS:** return từ 02/10/2023–29/04/2026, gồm 641 return; NAV chuẩn hóa tại 29/09/2023 để giữ lợi nhuận phiên đầu OOS.

| Kỳ | Chiến lược | NAV cuối | LN/năm | Biến động/năm | Sharpe | MDD | Turnover/năm |
|---|---|---:|---:|---:|---:|---:|---:|
| IS | EW | 1.9308 | 19.96% | 23.31% | 0.648 | -37.47% | 0.737 |
| IS | MVO | 4.3186 | 49.88% | 34.67% | 1.174 | -42.13% | 24.328 |
| IS | BL+ML | 1.7778 | 17.25% | 13.70% | 0.805 | -18.99% | 9.403 |
| IS | Hybrid | 3.0363 | 35.97% | 22.47% | 1.222 | -30.53% | 17.197 |
| OOS | EW | 1.7149 | 23.62% | 18.22% | 0.936 | -17.15% | 0.623 |
| OOS | MVO | 3.2031 | 58.04% | 32.84% | 1.381 | -26.86% | 23.822 |
| OOS | BL+ML | 1.9479 | 29.97% | 13.04% | 1.629 | -9.64% | 8.630 |
| OOS | Hybrid | 2.7521 | 48.88% | 22.11% | 1.648 | -18.08% | 16.868 |

NAV bắt đầu bằng 1 ở mỗi kỳ. Turnover tính theo vòng NAV/năm; kết quả **chưa trừ chi phí giao dịch**. Sharpe dùng lợi nhuận vượt lãi suất phi rủi ro hằng ngày, quy đổi theo 252 phiên/năm. [CSV kết quả đầy đủ](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/paper_period/corrected/trusted_baseline_metrics.csv).

**Nhận xét:** BL+ML có biến động và drawdown thấp hơn MVO; Hybrid tăng lợi nhuận so với BL+ML nhưng chịu rủi ro cao hơn. Hybrid Sharpe 1,648 nhỉnh hơn BL+ML 1,629; chưa có kiểm định để kết luận chênh lệch này có ý nghĩa thống kê hoặc đến từ ML.

## 2. Những lỗi đã sửa và kiểm tra đã hoàn thành

| Vấn đề | Kết quả xử lý |
|---|---|
| Dữ liệu VFF bị gán sai danh tính | Baseline sử dụng VFF đã xác minh đúng mã quỹ ID21 |
| GOLD và lịch giá không nhất quán | Dùng một snapshot GOLD; đồng bộ theo các phiên quan sát VNINDEX; không điền ngược giá từ tương lai |
| Nhãn huấn luyện chồng vào validation; trạng thái feature khi dự báo khác khi huấn luyện | Loại nhãn chồng lấn, fit scaler trên phần huấn luyện còn lại; dự báo dùng cùng lịch sử nhân quả |
| Quyết định sau khi biết giá đóng cửa nhưng giả định mua ngay tại giá đó | Chuyển sang thực thi ở giá đóng cửa phiên kế tiếp |
| Tỷ trọng cố định hằng ngày và mất return đầu OOS | Giữ số đơn vị tài sản giữa các lần giao dịch; sửa mốc chuẩn hóa OOS |
| Phân phối lại tỷ trọng sau solver có thể phá giới hạn | Kiểm và xử lý lại ràng buộc sau bước làm sạch tỷ trọng |

Đã lưu nguyên bản code/dữ liệu cũ và nhật ký sửa. **27/27 regression tests**, **52/52 kiểm tra độc lập** đạt; không có vi phạm tỷ trọng vượt tolerance 1e−8. Hai lượt huấn luyện mới cho **13 CSV và dự báo giống hoàn toàn**. Đây là kiểm chứng phép tính trên snapshot đã khai báo; chưa chứng minh mọi giá/NAV đã được công bố đúng thời điểm lịch sử.

## 3. Vấn đề hiện trạng

**Chưa tái tạo chính xác toàn bộ paper.** NAV OOS công bố là EW 1,82; MVO 3,73; BL+ML 1,90; Hybrid 2,86. Kết quả mới khác vì snapshot giá, lịch phiên và cách tính/thực thi đã thay đổi. Log lịch sử khôi phục được các số công bố nhưng kết thúc **27/02/2026**, trong khi văn bản paper ghi tháng 4 và Figure 1 ghi tháng 3. Cần thống nhất kỳ dữ liệu và gắn mỗi bảng với đúng lượt chạy.

| Vấn đề còn mở | Việc cần xử lý |
|---|---|
| Thời điểm công bố và sửa đổi NAV VFF / giá GOLD chưa xác minh | Bổ sung lịch sử công bố; kiểm lại dữ liệu nào thực sự đã biết khi ra quyết định |
| GOLD thiếu metadata về quote gốc, đơn vị, địa điểm và giá đã điền | Xác minh nguồn giá và phạm vi dùng GOLD như một đại diện định giá |
| Chưa rõ giá cổ phiếu đã điều chỉnh chia tách/cổ tức thế nào | Xác minh quy tắc provider; xác định rõ đang đo price return hay total return |
| Thiếu môi trường và artifacts mô hình của lượt paper gốc | Phục hồi để tái tạo toàn bộ; nếu không đủ, ghi rõ kết quả cũ chỉ được tái dựng từ quyết định đã lưu |

Ngoài ra, mô tả Sharpe, cách chuyển dự báo thành BL views và hệ số phạt rủi ro trong PDF chưa khớp code thực thi. Chênh **MVO 3,73 và alpha=1 đạt 3,57** được giải thích: alpha chỉ bằng 1 ở chế độ bình thường, còn stress/crisis vẫn pha BL. Dòng này cần được hiểu là **Hybrid với alpha_normal=1**, không phải MVO thuần trong mọi chế độ.

Hit rate OOS mới: **51,02%** cho toàn bộ dự báo thô đã đủ thời gian quan sát, **50,43%** cho ML views đã qua chuyển đổi/ngưỡng. Hai tỷ lệ dùng tập quan sát khác nhau; không so trực tiếp với **51,9%** của paper để kết luận mô hình tốt hơn hay kém hơn.

Danh sách 30 cổ phiếu vẫn cố định và chi phí giao dịch vẫn bằng 0, cần xử lý ở **Step 7/8**. Nguồn gốc lựa chọn tham số trước OOS còn thiếu bằng chứng; lần chạy lại giữ nguyên tham số và không tối ưu theo kết quả OOS.

## 4. Kết luận và việc tiếp theo

**Đã hoàn thành việc sửa, chạy lại và kiểm chứng phép tính của baseline. Chưa đủ bằng chứng để chứng nhận đầy đủ Step 1.** Ưu tiên xác minh thời điểm công bố dữ liệu và cách điều chỉnh giá cổ phiếu, đồng thời đồng bộ số liệu/phương pháp trong paper. Chưa chạy thí nghiệm Step 2.

[Báo cáo kỹ thuật và bằng chứng chi tiết](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/step1_report.md) · [Kết quả và hồ sơ lượt chạy tháng 4](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/paper_period).

NOT READY FOR STEP 2
