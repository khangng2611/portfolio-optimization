# Hội thoại V2.4 — bàn giao

[Figma V2.4](https://www.figma.com/design/YKRbiOAJNoVA9DaSZHc7Wc/?node-id=109-200933). Sáu frame desktop/mobile, giữ nguyên các section trước. Thiết kế có text, controls, hàng phân bổ và navigation chỉnh sửa được; tái sử dụng Be Vietnam Pro, màu, styles, variables và button components hiện có.

| Trước | Sau |
| --- | --- |
| Cả cụm chat bị căn giữa, khoảng trống sát menu chính | Workspace bám lề nội dung; danh sách hội thoại 240 px và vùng trao đổi là hai cột chính. |
| Panel ngữ cảnh cao bên phải | Tên danh mục, vốn kế hoạch và hồ sơ nằm gọn trên đầu vùng trao đổi. Mở chi tiết để đổi danh mục, đọc giới hạn/phiên bản hoặc mở danh mục. Escape đóng và trả focus. |
| Trạng thái trải ngang rộng hơn tin nhắn/ô nhập | Cùng một trục đọc giới hạn bề rộng. Khi câu trả lời hoặc thẻ xác nhận đã hiện, bỏ thông báo hoàn tất trùng lặp. |
| Mọi COMPLETE đều nói kết quả được lưu | Câu trả lời thường không còn tạo cảm giác vừa lưu đề xuất hay chấp nhận mục tiêu. Lỗi, đang xử lý, cấp lại quyền và tiếp nhận chưa rõ vẫn hiện. |
| Giải thích kỹ thuật hiện thường xuyên | Nguồn hỗ trợ nằm trong phần mở rộng. Trợ giúp hệ thống mở thành vùng đọc giới hạn chiều cao, giữ ô nhập trong tầm nhìn. |
| Màn ngang thấp mất vùng đọc | Thu gọn header/context và ô nhập; link tất cả hội thoại vẫn truy cập được khi danh sách tạm ẩn. |

Prototype mô phỏng mở/đóng ngữ cảnh và từ kết quả mở màn xem lại đề xuất V2.3. Dữ liệu minh họa. Không gọi API hoặc LLM; không mô phỏng mọi tổ hợp hội thoại. Mobile chuyển sang một cột, danh sách hội thoại thu gọn.

Source UI thay đổi tại `chat-workspace.tsx`, `ui-refresh.css`, `chat-types.ts`; thêm regression tests cho trạng thái lượt trao đổi. Không thay API, thuật toán, policy, risk scoring, consent đã lưu, idempotency hoặc role gates. Nội dung lịch sử do backend trả về được giữ nguyên; các câu cũ có thuật ngữ nội bộ không bị viết lại.

Kiểm tra trình duyệt sử dụng route fixtures đã làm sạch, gồm hội thoại ngắn, kết quả, xác nhận, đang xử lý, lỗi, cấp lại quyền và pending retry; không tạo job/accept/LLM thật. Xem `output/playwright/chat-v24/verification.json` và screenshots để biết kết quả cuối. Không xem đây là chứng nhận đầy đủ về screen reader, bàn phím ảo thiết bị thật hoặc backend persistence.
