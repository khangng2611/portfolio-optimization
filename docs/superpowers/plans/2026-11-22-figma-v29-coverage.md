# Portfolio Optimization · Độ phủ Figma V2.9

Phạm vi gồm các frame mới được nối từ điểm mở prototype và luồng desktop/mobile đang phục vụ trên cổng 3100. Các bước được prototype dẫn về V2.8 tiếp tục dùng giao diện và nghiệp vụ hiện hành. [Figma V2.9](https://www.figma.com/design/YKRbiOAJNoVA9DaSZHc7Wc/?node-id=249-23234)

| Frame desktop / mobile | Route | Thực hiện và nghiệm thu |
| --- | --- | --- |
| `249:23235/24000`, `249:23510/24070`, `249:23756/24116`, `250:27852/28097` | `#overview` | Một hành động chính cho đề xuất hợp lệ, mục tiêu đã lưu, hồ sơ cần hoàn tất hoặc trạng thái tạm dừng. Đề xuất mới được ưu tiên khi cùng có mục tiêu đã lưu. Khi sửa vốn hoặc rổ, số liệu hiện tại đổi và bản mục tiêu đã lưu được đối chiếu nguyên vẹn qua API. |
| `250:24160/25193`, `250:24434/25265`, `250:24708/25337`, `250:24951/25381`, `250:27127/27439` | `#proposal`, `#proposal?focus=history`, `#proposal?focus=request` | Một khối lý do, tác động và việc tiếp theo cho đề xuất cũ. Nhánh sẵn sàng mở bước xem lại yêu cầu. Nhánh tạm dừng hoặc chưa xác định readiness giữ phân bổ cũ, mục căn cứ và lối mở lịch sử. Trên app, mục căn cứ mở trong màn review. |
| `250:27486/27771` | `#asset-prices?asset=…` | Liên kết mã trong biểu đồ và bảng mở lịch sử giá của đúng mã có trong danh mục giá. Nút trở lại phục hồi đúng route phân bổ. App giữ trang lịch sử giá, bộ lọc và kỳ đang hỗ trợ. |
| `250:25436/26202`, `250:25690/26254`, `250:25943/26306`, `250:28177/28436` | `#create` | Kế hoạch và rổ là hai phần trong bước 1. Giữ nháp khi quay lại, giải thích điều kiện đi tiếp và điều kiện tính, dùng bộ chọn V2.7. Luồng legacy vẫn chọn bộ tài sản. |
| `250:26364/26781`, `250:26578/26887`, `250:26982/27373`, `250:26469/26832`, `250:26683/26938` | `#chat`, `#chat?conversation=…` | Hỏi trước, tên tùy chọn, gợi ý điền nháp, lượt đầu gửi một lần qua luồng idempotency hiện hành. Phân bổ mở từ ngữ cảnh, dữ kiện và nguồn mở từ lượt trả lời. Nguồn mở cạnh hội thoại ở màn rộng và trong hộp thoại ở màn hẹp. |

## Kiểm chứng

- 175 test Vitest, TypeScript và production build của Web đã qua. Bảy kịch bản Playwright đã qua trên Chromium với viewport desktop, tablet và mobile, gồm 375, 390, 768 và 1440 CSS px. Kiểm tra bổ sung đối chiếu trích dẫn Knowledge của lượt trả lời mới với API. Receipt Knowledge cũ trả 404 ở lượt kiểm persistence.
- Bản local báo `SYSTEM_PAUSED`. Kịch bản nhánh sẵn sàng thay phản hồi readiness trong trình duyệt để kiểm tra bước xem lại yêu cầu và số lần gọi tạo đề xuất bằng 0. Trường hợp đề xuất đang chờ cùng mục tiêu cũ và cấu hình onboarding legacy cũng dùng fixture trình duyệt. Các bài sửa vốn/rổ và gửi Chat dùng tài khoản hoặc danh mục kiểm thử trên backend local.
- Báo cáo Playwright và ảnh đã che tên tài khoản nằm trong `output/playwright/sanitized`. Các ảnh có tiền tố `v29-` ghi lại trạng thái mới, onboarding và Chat. Ảnh `overview-edited-target-desktop.png` và `overview-edited-target-mobile.png` ghi lại vốn hiện tại và vốn mục tiêu trước khi hoàn nguyên giá trị của danh mục kiểm thử.
