# Thiết kế lại Figma cho ứng dụng lập kế hoạch danh mục

Ngày 24/11/2026. Tài liệu dành cho người thiết kế và người duyệt prototype. Điểm xuất phát là section V2.10 trên trang “Nhà đầu tư & hội thoại”. Vòng này lập kế hoạch. Các frame và phép thử bên dưới là đầu ra của vòng thiết kế kế tiếp. [Mở Figma V2.10](https://www.figma.com/design/YKRbiOAJNoVA9DaSZHc7Wc/?node-id=256-28546)

## 1. Đọc năm ảnh tham chiếu

| Ảnh | Quyết định đem lại hiệu quả | Chuyển sang ứng dụng danh mục |
| --- | --- | --- |
| 1 · Đăng nhập | Trên desktop, mảng tối và đường cong lớn tạo dấu hiệu nhận diện ở một bên. Form bên kia có cạnh trái thẳng, nhãn sát trường và một nút chính. Trên điện thoại, mảng nhận diện trở thành đầu trang. | Dùng một đường cong đặc trưng ở màn truy cập; trên mobile thu mảng thương hiệu đủ để thấy trường và nút đăng nhập sớm. Chỉ vẽ phương thức truy cập dự án đang hỗ trợ. |
| 2 · Chọn giao diện | Mỗi mẫu dùng cùng một con số, bố cục và biểu đồ thu nhỏ. Viền và dấu kiểm làm rõ lựa chọn ngay cả khi màu gần nhau. | Dùng các bản thu nhỏ song song trên bảng duyệt Figma để so phong cách với cùng dữ liệu. Mượn dấu kiểm kèm nhãn cho hàng tài sản đã chọn. Bộ chọn theme trong sản phẩm nằm ngoài phạm vi vòng này. |
| 3 · Sổ chi tiêu | Việc đến hạn nằm ngang ở đầu. Con số chính nằm trực tiếp trên nền, biểu đồ đứng cạnh; thanh tỷ lệ phía dưới nối với từng nhãn. Bảng, số và biểu đồ có chức năng riêng. | Khi cần xử lý, đặt thông báo phía trên vùng đọc số liệu. Khi có mục tiêu, ghép vốn tại lần lưu với cơ cấu cùng lần lưu. Dùng bề mặt trắng cho phần cần đọc như một nhóm. |
| 4 · Hồng pastel | Màu mận giữ chữ và số rõ trên nền hồng nhạt. Minh họa trái tim chỉ xuất hiện ở khối tổng; danh sách và biểu đồ vẫn có nền sạch. | Thử mảng màu nhạt và hình khối thương hiệu ở đầu onboarding hoặc trạng thái mới bắt đầu. Giữ nền biểu đồ phẳng và các nhãn giá rõ. |
| 5 · Đen và vàng | Ở cùng bố cục, thay nền, chữ, điểm nhấn và đường lưới vẫn giữ được nhịp đọc. Vàng sáng tập trung vào kỳ đang xem. | Dùng một frame tối để thử độ bền của hệ màu. Tách màu đánh dấu lựa chọn khỏi màu cảnh báo và màu đại diện tài sản vàng. |

Mô tả dùng khi tìm mẫu là *personal finance dashboard*, *editorial dashboard layout*, *Swiss grid typography*, *semantic color tokens* và *portfolio allocation breakdown*. Cụm “dashboard tài chính cá nhân có bố cục biên tập” mô tả sự kết hợp quan sát được. Mối liên hệ với Swiss Style nằm ở lưới, chữ sans serif và bố cục bất đối xứng. Năm ảnh là nguồn trực tiếp cho nhận xét về giao diện HB. [Thư viện Quốc gia Thụy Sĩ](https://www.nb.admin.ch/en/the-international-style-1950-1970)

## 2. Nguồn nghiên cứu và quyết định áp dụng

- **Monarch Money.** Báo cáo cho phép chọn một phần biểu đồ để xem các giao dịch phía sau. Mượn quan hệ tổng thể → thành phần → chi tiết. Tại dự án, chạm hàng FPT sẽ mở lịch sử giá FPT nếu có dữ liệu, còn thao tác xem phân bổ sẽ mở bảng tỷ trọng cùng bản đề xuất. [Monarch Reports](https://help.monarch.com/hc/en-us/articles/21846787088916-Using-Reports)
- **Wealthfront.** Việc tùy chỉnh danh mục phân biệt chọn khoản đầu tư và chỉnh tỷ lệ. Dự án có quyền thao tác riêng: người dùng chọn rổ ứng viên, hệ thống tính tỷ trọng, người dùng xem lại rồi quyết định lưu. Rổ nên có hành động “Thêm”, còn phân bổ trình bày phần trăm và ngày tính. [Wealthfront Portfolio](https://support.wealthfront.com/hc/en-us/articles/360059631751-Customizing-your-Wealthfront-Portfolio)
- **Finhay HayBuddy.** Hướng tiếp cận là trả lời trực tiếp và cô đọng. Dùng một kết luận ngắn đầu câu trả lời; nguồn và dữ kiện có thể mở theo lượt. Giữ nguyên mốc dữ liệu cuối ngày của dự án. [Finhay Securities](https://fhsc.com.vn/tro-ly-dau-tu-ai-haybuddy)
- **IBM Carbon.** Bảng màu định tính dùng để phân biệt các nhóm. Gán màu theo loại tài sản và giữ ý nghĩa qua biểu đồ, chú giải và bảng. Trả lại đầy đủ tên và tỷ trọng cho người đọc qua chữ. [Carbon Data Visualization](https://www.carbondesignsystem.com/building-blocks/data-visualization/color-palettes)

## 3. Ba phương án để so trên cùng dữ liệu

| Phương án | Bản thử trong Figma | Quyết định |
| --- | --- | --- |
| Sáng, nền bạc hà và chữ đậm | Nền sáng rất nhẹ, chữ mực, xanh rừng cho hành động. Một con số lớn, một thanh tỷ trọng và các dòng số căn phải. | Hướng chính. Gần ảnh 3, dễ đọc tiếng Việt và tận dụng được nhận diện đang có. |
| Pastel ấm | Dùng cùng lưới, thêm mảng hồng đất hoặc kem và một nét cong ở phần chào. | So trên onboarding hoặc đăng nhập. Kiểm tra điểm nhấn có còn dẫn mắt tới trường cần nhập. |
| Tối, điểm nhấn vàng nhạt | Dùng cùng số liệu với bản sáng, đổi giá trị màu cho nền, chữ và đường lưới. | Một phép thử trên Tổng quan. Chỉ nhân rộng sau khi duyệt độ rõ của trạng thái và chú giải. |

**Thông số khởi điểm để vẽ.** Giữ Be Vietnam Pro. Thử số chính 48–56 px trên desktop, 32–40 px trên mobile; số tiền và phần trăm trong bảng dùng chữ số cùng bề rộng, căn phải. Thân bài 16 px; nhãn 13–14 px. Thử với số tiền dài, đơn vị ₫ và chữ tiếng Việt hai dòng. Desktop 1440 px dùng lưới 12 cột trong vùng nội dung, cách cột 24 px. Mobile 390 px dùng 4 cột, lề 16 px. Bo 12 px cho nhóm dữ liệu, 8 px cho điều khiển; dành đường cong lớn cho vùng nhận diện. Dùng khoảng cách 8/16/24/32 px để thể hiện nội dung nào thuộc cùng nhóm.

**Màu.** Nền thử #F2F7F5, mặt đọc #FFFFFF, chữ mực #152F2B, nút chính #14674D, vùng được chọn #E7EFE8. Trạng thái cần chú ý dùng chữ #80510A trên nền #FFF2D9. Tách biến màu cho thương hiệu, trạng thái, dữ liệu và đường focus. Quỹ, cổ phiếu, vàng giữ thứ tự và màu ổn định; khi loại chưa xác định, dùng nhãn riêng. Đo tương phản trên từng cặp trước khi chốt.

## 4. Hai bố cục cần dựng đầu tiên

**A · Đã lưu mục tiêu.** Dùng lại dữ liệu minh họa V2.10: vốn kế hoạch hiện tại 120 triệu đồng, vốn tại lần lưu 100 triệu đồng, VFF 50%, FPT 35%, GOLD 15%. Đây là trường hợp kiểm tra xem cách đặt số lớn có khiến người đọc hiểu nhầm cơ sở tính. [Frame gốc desktop](https://www.figma.com/design/YKRbiOAJNoVA9DaSZHc7Wc/?node-id=257-31223) · [Frame gốc mobile](https://www.figma.com/design/YKRbiOAJNoVA9DaSZHc7Wc/?node-id=257-31500)

| Vùng đọc | Desktop | Mobile |
| --- | --- | --- |
| Đầu trang | Tên kế hoạch, vốn hiện tại, thời hạn, hồ sơ trên cùng một cụm. | Tên ở dòng đầu. Ngữ cảnh tối đa hai dòng, vẫn ghi rõ “Vốn hiện tại”. |
| Cơ cấu đã lưu | Bên trái là “Vốn tại lần lưu”, số lớn 100.000.000 ₫ và ngày lưu. Bên phải là “Phân bổ đã lưu”, một thanh 100% theo nhóm và chú giải có số. | Gom nhãn, số tiền, ngày và thanh tỷ trọng thành một khối. Khi chỉ có một nhóm, đọc được tên và 100% ngay bên dưới. |
| Chi tiết | Bảng thẳng hàng theo mã, tỷ trọng, số tiền và lối xem giá. Đặt lịch sử mục tiêu cạnh ngày lưu. | Hàng hai dòng; tỷ trọng ở cuối hàng, số tiền ngay dưới. Với danh sách dài, cho mở toàn bộ; mã có tỷ trọng 0% vẫn truy xuất được. |

**B · Tạm dừng, chưa có đề xuất.** Đặt “Tạm dừng tạo đề xuất”, lý do và “Hỏi về kế hoạch” ngay dưới tên danh mục. Thay vùng phân bổ bằng vốn kế hoạch, thời hạn và rổ đã chọn, dùng dữ liệu sẵn có. Khi có lịch sử thì hành động chính chuyển thành “Xem lịch sử đề xuất”. Với đề xuất cũ hết hạn, hiển thị “Phân bổ của lần tính cũ”, ngày dữ liệu và lối mở căn cứ. Chỉ hiển thị “Xem lại đầu vào” khi hệ thống cho phép. [Frame tạm dừng](https://www.figma.com/design/YKRbiOAJNoVA9DaSZHc7Wc/?node-id=257-28844)

## 5. Kế hoạch dựng Figma

| Thứ tự | Công việc | Đầu ra để duyệt |
| --- | --- | --- |
| 1 · Chọn hướng | Tạo section mới khi bắt đầu thực hiện. Đặt cạnh nhau ảnh 3, frame hiện tại và bản đề xuất ở cùng chiều rộng. Dựng A và B trên desktop 1440 và mobile 390 bằng dữ liệu trên. Thử hai biến thể màu ở mức mẫu nhỏ. | Bốn frame chính và một bảng so sánh. Duyệt bằng hai câu hỏi “Khoản vốn nào dùng tính tỷ trọng?” và “Tôi có thể làm gì khi tạm dừng?”. |
| 2 · Chốt component | Dùng Figma Variables cho màu theo vai trò, Text Styles cho nhãn, số lớn và số trong bảng. Dùng Auto Layout cho tiêu đề kế hoạch, khối số liệu, thông báo có hành động, thanh tỷ trọng + chú giải, hàng tài sản, dòng mở rộng và khung soạn chat. | Mỗi component có instance trên màn thật. Kiểm tra lựa chọn, focus, disabled, thiếu dữ liệu và nhãn dài ở các component liên quan. |
| 3 · Mở rộng luồng quyết định | Dựng cặp desktop/mobile cho có đề xuất chờ, mục tiêu cũ cùng đề xuất mới, hết hạn có thể tính lại, hết hạn + tạm dừng và chưa xác minh được điều kiện. Nối đến lịch sử, xem lại đầu vào, căn cứ và giá đúng mã. | Prototype đi hết mỗi nhánh. Nhãn, ngày, tỷ trọng và đích đến luôn cùng bản đề xuất. |
| 4 · Rổ, chat và truy cập | Rổ dùng danh sách gọn có dấu chọn và lý do cần VFF khi chính sách yêu cầu. Chat giữ khung soạn tại cùng vị trí qua màn bắt đầu và đã trả lời, nguồn gắn với từng lượt. Đăng nhập dùng bố cục hai mảng. Sau khi duyệt, áp dụng component vào danh sách danh mục, hồ sơ và cài đặt hiện hữu. | Prototype chọn rổ → quay lại còn nháp; tạm dừng → chat đúng danh mục → mở nguồn; đăng nhập trên hai kích thước. Nhánh tự chọn rổ bốn bước và nhánh bộ tài sản có sẵn dùng tiến trình hiện hành riêng. |
| 5 · Kiểm tra và bàn giao | Kiểm ở 375, 390, 768 và 1440 px. Ghi frame nguồn, component và phần tương ứng đang có trong app. | Link section, prototype, ảnh render, bảng các trạng thái đã thử và các điểm cần xác minh khi triển khai. |

### Điều kiện duyệt prototype

- Đưa frame mục tiêu đã lưu cho người mới và hỏi “35% FPT tương ứng bao nhiêu tiền?”. Với mẫu trên, họ tìm được 35 triệu đồng và chỉ ra mốc vốn 100 triệu đồng. Nếu nhầm với 120 triệu, sửa thứ bậc chữ và vị trí trước khi đổi màu.
- Ở mobile 390 × 844, người dùng nhìn thấy lý do tạm dừng và hành động khả dụng trước lần cuộn đầu. Khung chat giữ đúng danh mục, gợi ý chỉ điền nháp. Bàn phím mô phỏng và thanh điều hướng không che nút gửi.
- Ở bước rổ, ít nhất một hàng và nút “Thêm” hiện trọn trước khi cuộn. Kiểm với rổ trống, nhiều mã, mã tỷ trọng 0% sau khi tính và tên doanh nghiệp dài. Tách số mã được cân nhắc khỏi số mã thực sự được phân bổ.
- Khi mở lịch sử giá, nhìn thấy mã, đơn vị, ngày và nguồn; khi quay lại, giữ đúng kết quả đang xem. Ở bản thiếu dữ liệu, dùng trạng thái trống. Chỉ đưa tỷ trọng đã có và giá lịch sử của từng mã lên biểu đồ tương ứng.
- Kiểm tra nút chính bằng bàn phím, chữ thường tương phản tối thiểu 4,5:1, vùng tương tác chính hướng tới 44 × 44 px, chú giải có tên và số bên cạnh màu. Việc kiểm chứng trình đọc màn hình và bàn phím thật thuộc vòng triển khai web.

### Tính khả thi

Trong mã nguồn hiện có, Tổng quan đã phân nhánh theo điều kiện tính, bản mục tiêu và lịch sử. Phân bổ có vốn tại lần tính, mã, tỷ trọng, bảng chi tiết và liên kết lịch sử giá. Có thể đổi thứ bậc thị giác, tính tổng theo nhóm từ cùng một bản phân bổ và tái sử dụng dữ liệu hiện hữu. Cần thống nhất ánh xạ màu theo loại ở cả biểu đồ lẫn bảng; có chỗ hiện lấy màu theo vị trí của mã. Giữ nguyên các bước xem lại và xác nhận. Vòng thiết kế không phụ thuộc vào việc mở tính năng tính mới, bổ sung số dư thực tế hay tính hiệu suất danh mục.
