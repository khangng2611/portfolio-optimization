# Phase 2 · Quyết định tái cân bằng và danh mục mô phỏng

**Câu hỏi nghiên cứu.** Với cùng dòng tỷ trọng HYBRID, kiểm tra độ lệch trước khi giao dịch có giảm giao dịch và chi phí mà vẫn duy trì hiệu quả sau phí hay không? Phạm vi sản phẩm là một danh mục mô phỏng VND trên mỗi danh mục user, có vốn đầu kỳ, không nạp/rút thêm trong bản đầu. Giữ VFF. OCB là đối chứng nghiên cứu đã báo cáo riêng.

## 1. Khóa thiết kế trước khi xem kết quả mới

- Dùng [310 ngày mục tiêu HYBRID](../../../outputs/step1/Step1_Submission_Readiness_20261012/04_Baseline_Target_Weights.csv) từ 19/02/2020 đến 28/04/2026 làm tập ứng viên. Kiểm giao của giá, lịch, NAV, báo giá vàng hai chiều và biểu phí, rồi công bố số ngày thực dùng cùng lý do loại. Không tự giới hạn theo các ngày kiểm chứng lãi suất OCB.
- Đối chiếu [quy ước thực thi GOLD–K5](../../../phase2_gold_k5/execution-policy.md) và [kế toán OCB/VFF theo lô](../../../phase2_ocb_deposits/rebalance_5/REPORT.md). Quy tắc đã thử ở GOLD–K5 dựa vào lợi ích và chi phí. Thí nghiệm này kiểm riêng ngưỡng lệch tỷ trọng trên HYBRID. Kiểm tra khả năng tái dùng code và điều khoản theo từng giai đoạn.
- Cho cả ba phương án cùng vốn 10 triệu đồng, cùng giao dịch mở danh mục đầu tiên, cùng dữ liệu đủ điều kiện khi quyết định, lịch khớp và cách định giá. A giữ nguyên số lượng sau lần mua đầu, kể cả khi mã rời K5 trừ sự kiện bắt buộc như hủy niêm yết. B giao dịch về mục tiêu khả thi mỗi 5 phiên. C xem xét cùng ngày với B, chỉ giao dịch khi độ lệch đạt ngưỡng. Độ lệch bằng một nửa tổng chênh lệch tuyệt đối giữa tỷ trọng trước giao dịch và mục tiêu, tính cả tiền mặt và tài sản có mục tiêu bằng 0. Xử lý lệnh chờ trước khi lập lệnh mới. Đăng ký trước các ngoại lệ bắt buộc của B/C và đếm riêng.
- Đề xuất thử ngưỡng 2%, 5%, 10% trên tập phát triển. Chọn một ngưỡng bằng quy tắc ghi trước (đề xuất lợi suất ròng cao nhất, hòa thì chọn turnover thấp hơn). Khóa ngưỡng, chi phí, lịch và ngày cắt trước khi chạy phần đánh giá theo thời gian. Phần lịch sử đã được dự án xem phải ghi rõ là đánh giá hồi cứu. Không chọn lại ngưỡng sau khi nhìn kết quả.
- **Đầu ra nghiệm thu:** protocol có ngày cắt, phạm vi dữ liệu đã đối soát, hash đầu vào, quy tắc xử lý dữ liệu thiếu và bảng kê phí. Phase 1 tiếp tục là mốc tham chiếu.

## 2. Chạy và phản biện ba phương án

- Dùng một sổ giao dịch cho cả ba nhánh. Ghi số lượng, tiền khả dụng, tiền giữ cho lệnh mua, tiền bán chờ về, phí và thuế. Cổ phiếu có quy ước lô và thanh toán công khai; vàng mua theo giá bán, bán theo giá mua của cửa hàng; VFF tính phí theo tuổi phần thực bán và khớp theo lịch quỹ. Bất kỳ quy ước chia lẻ, giá đại diện hay tiền về sớm nào cũng phải ghi là giả định. Tách giá có thể dùng để ra quyết định khỏi giá khớp sau đó.
- Xuất biểu đồ NAV theo cùng lịch, lợi suất ròng, drawdown tối đa, turnover, số ngày thực giao dịch và chi phí theo tài sản. Báo chênh lệch B−A và C−B theo cùng ngày, theo các giai đoạn định trước và độ nhạy phí/thanh khoản. Kiểm tra kết quả có phụ thuộc một vài phiên, vốn giả định hoặc một ngưỡng cụ thể không.
- **Cửa nghiệm thu:** tiền khả dụng không âm, không dùng hai lần tiền chờ, sổ giao dịch khớp NAV từng phiên. A chỉ có giao dịch khởi tạo và sự kiện bắt buộc. Khi đặt ngưỡng bằng 0, C phải tái tạo B trên cùng đầu vào. Chạy lại từ dữ liệu đóng băng cho cùng kết quả. Chỉ đề xuất ngưỡng mặc định nếu bằng chứng ngoài tập chọn ngưỡng đủ ổn định. Nếu kết quả lẫn lộn, công bố đánh đổi và giữ luồng thủ công.

## 3. Đưa một giao dịch mô phỏng đi hết luồng ứng dụng

- Từ mục tiêu đã chấp nhận, user mở tài khoản mô phỏng bằng vốn giả định. Danh mục cũ chỉ có mục tiêu bắt đầu với tiền mặt khi user chủ động khởi tạo. Không suy diễn giao dịch quá khứ.
- Hiện vị thế, mục tiêu, chênh lệch, lệnh dự kiến, phí ước tính, giá và thời điểm dữ liệu. User xác nhận hoặc bỏ qua. Xác nhận tạo lệnh mô phỏng; ghi thay đổi số lượng khi khớp và cập nhật tiền khả dụng khi thanh toán. Hết hiệu lực báo giá hoặc mục tiêu đổi thì yêu cầu xem lại.
- Tái dùng quy tắc kế toán đã kiểm chứng ở bước 2. Gắn giao dịch với user, danh mục, phiên bản mục tiêu, thời điểm quyết định và nguồn giá. Kiểm quyền, tính nguyên tử và chống ghi hai lần khi bấm lại.
- **Cửa nghiệm thu:** cùng chuỗi mục tiêu và giá thử phải cho số lượng, phí và tiền cuối giống bộ mô phỏng. Kiểm luồng bỏ qua, lệnh chờ, khớp, tiền về, tải lại trang, gửi lặp và truy cập chéo tài khoản.

## 4. Hiện lời/lỗ và nhắc xem xét

- Tự định giá khi có dữ liệu mới. Tổng tài sản bằng tiền mặt (kể cả phần đã dành mua) cộng tiền bán chờ về và giá trị vị thế còn sở hữu, mỗi khoản chỉ ghi một lần. Khi vốn đầu kỳ là dòng tiền ngoài duy nhất, lời/lỗ ròng bằng tổng tài sản trừ vốn đầu kỳ. Lợi suất bằng lời/lỗ ròng chia vốn đầu kỳ. NAV dùng cho biểu đồ bao gồm vị thế chưa bán và các chi phí đã phát sinh.
- Màn hình hiển thị biểu đồ giá trị theo ngày, lời/lỗ VND và %, tiền sẵn dùng/chờ về, phí đã trả và ngày định giá. Báo giá cũ/thiếu phải có trạng thái. Nếu chưa khởi tạo thì hiện hướng dẫn, không vẽ lịch sử giả định.
- Gợi ý với danh mục đã khởi tạo và có mục tiêu: lấy phiên khởi tạo làm mốc, mặc định **xem xét** mỗi 5 phiên thị trường. Mỗi kỳ lưu thời điểm kiểm tra và mục tiêu được đối chiếu. User vẫn xem trước và yêu cầu giao dịch mô phỏng sớm nếu dữ liệu hợp lệ. Giao dịch thủ công được ghi riêng, không đặt lại lịch kiểm tra định kỳ. Lệnh đang chờ được đối soát để tránh gửi trùng. Yêu cầu một mục tiêu mới vẫn dùng luồng tạo và chấp nhận đề xuất hiện hành.
- **Cửa nghiệm thu:** đối soát ít nhất một ngày chưa khớp, một ngày bán có phí và một ngày tiền về giữa biểu đồ và sổ. Kiểm ngày nghỉ, hai user có ngày bắt đầu khác nhau, bỏ qua nhắc, và việc nhắc không tạo lệnh. Demo trọn luồng với cùng một bộ giá cố định.

## Quyết định về thời hạn và tự động hóa

24 và 36 tháng mô tả thời hạn mục tiêu, hiện cùng thuộc nhóm 12 đến dưới 60 tháng trong [hồ sơ rủi ro](../../../services/portfolio/src/portfolio_service/policy.py). Giữ cơ chế đó cho bản đầu. Một lịch xem xét cá nhân hóa cần bằng chứng riêng. Sau so sánh chính, có thể thử 5/10/20 phiên, cùng mục tiêu và chi phí ở mỗi mốc, so sánh trong các cửa sổ 24/36 tháng, công bố số cửa sổ độc lập và mức chồng lấn. Cần có đủ dữ liệu và tiêu chí phù hợp theo mục tiêu/rủi ro trước khi suy ra lịch phù hợp với từng nhóm.

Tự động hóa định giá, biểu đồ và nhắc xem xét. Quyền khởi tạo lệnh thuộc về user. Nếu sau này cần chế độ chỉ theo dõi, triển khai riêng tùy chọn tự giao dịch mô phỏng có bật/tắt rõ ràng, chính sách, giới hạn và lịch sử quyết định. Báo cáo đánh giá chiến lược tự động phải dùng luồng kiểm soát được, tách khỏi lịch sử có can thiệp thủ công.

## Kết quả triển khai ngày 27/11/2026

Đã khóa 310 ngày mục tiêu và chạy lại hai lần với cùng dữ liệu. Trên 641 phiên đánh giá, ngưỡng được chọn 2% tái tạo toàn bộ giao dịch của B, còn A có lợi suất cao hơn khoảng 1,06 điểm phần trăm và drawdown sâu hơn khoảng 6,69 điểm phần trăm. Ứng dụng dùng nhắc xem xét thủ công sau mỗi 5 phiên của danh mục, hiển thị độ lệch và chi phí. [Báo cáo cùng chi tiết kiểm tra độ nhạy](../../../phase2_rebalance/REPORT.md)

Hai màn hình **Tài sản và hiệu suất** và **Tái cân bằng** dùng sổ giao dịch chung với bộ mô phỏng. Migration Portfolio bổ sung tài khoản và quyết định. Worker xử lý giá mới, xác nhận lặp dùng cùng quyết định, ngày khớp quỹ và ngày có NAV được theo dõi riêng. [Hướng dẫn chạy local](../../../infra/local/README.md#phase-2--danh-mục-mô-phỏng) · [Kiểm thử API đối soát sổ](../../../tests/software/test_paper_account.py) · [Kiểm thử giao diện trên API mô phỏng thật](../../../apps/web/tests/paper-browser/lifecycle.e2e.ts)
