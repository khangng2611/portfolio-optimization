# UI controls V2.5 — bàn giao

[Figma section](https://www.figma.com/design/YKRbiOAJNoVA9DaSZHc7Wc/?node-id=116-201746). Sáu frame desktop/mobile cho chat, tùy chọn và hồ sơ; component family icon buttons, focus/disabled, selection chips và logout có nhãn. Các section trước được giữ nguyên.

Giữ Be Vietnam Pro, màu xanh/kem và semantics nghiệp vụ. Bổ sung quy tắc controls dùng chung vì refresh, paging và tùy chọn đang lặp lại với nhãn dài, kích thước và vị trí khác nhau. Không tạo palette hoặc font mới.

| Phạm vi | Thay đổi |
| --- | --- |
| Tài khoản / Đăng xuất | Neo tại mép phải viewport, cùng inset trên các tab. Loại khỏi các selector giới hạn bề rộng form/reading lane. Desktop giữ nhãn; màn nhỏ dùng icon có tên truy cập. |
| Refresh | Một `IconButton` có tên truy cập và tooltip khi hover/focus, vùng bấm 44 px. Áp dụng hội thoại, readiness, dữ liệu, lịch cập nhật và mô hình. |
| Phân trang | Mũi tên trước/sau trên một hàng, giữ text vị trí trang/kết quả và trạng thái disabled. Dùng cho investor lists/chat và cả hai pager vận hành. Logic limit/offset giữ nguyên. |
| Tùy chọn chat | 7 mục đích có icon + nhãn ngắn, 4 chiến lược có tên phương pháp rõ. Native radio hỗ trợ phím mũi tên. Tự động vẫn là mặc định, lựa chọn không gửi yêu cầu. Escape đóng và trả focus. |
| Popup chat | Giới hạn theo khoảng trống thực phía trên composer, cập nhật khi textarea hoặc trường mã đề xuất thay đổi. Nội dung dài cuộn trong popup. |
| Search / native select | Search/filter/sort icons ở portfolio toolbar và chevron nhất quán cho native selects toàn workspace; giữ native keyboard interaction. |
| Hành động nghiệp vụ | Giữ nhãn cho tạo/xác nhận/chấp nhận và các quyết định vận hành. Không biến mọi hành động thành icon khó đoán. |

Source: `action-controls.tsx`, `workspace-shell.tsx`, `portfolio-lifecycle.tsx`, `chat-workspace.tsx`, `operation-ui.tsx`, `market-operations.tsx`, `data-refresh.tsx`, `model-operations.tsx`, `ui-refresh.css` và local chevron SVG. Browser journey locators được cập nhật theo các lựa chọn radio mới; API payload và workflow không thay đổi.

Prototype chỉ mô phỏng mở/đóng tùy chọn. Lớp Figma options mobile có chiều cao nội dung để đọc đầy đủ; runtime popup được giới hạn theo viewport và cuộn. Native text, glyphs, controls và các nhóm lựa chọn vẫn chỉnh sửa được. API export node không cung cấp visibility; một số layer cũ được giữ và ẩn khi thay controls.

Kiểm tra: xem `output/playwright/controls-v25/verification.json`, screenshots và log. Browser fixtures đã làm sạch; không logout tài khoản thật, gọi LLM, tạo optimization job, accept target, promote model hoặc thay backend. Chưa chứng nhận toàn bộ screen reader/native soft keyboard. Nội dung lịch sử do backend trả về không bị viết lại.
