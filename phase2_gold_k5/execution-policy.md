# Quy ước thực thi khóa trước so sánh

Ngày 24/11/2026, áp dụng cùng protocol.json. Báo giá lưu trữ theo ngày là proxy. Ở phân tích chính, ngày mang cờ của archive (“không đổi”, có thể là giá giữ nguyên) được định giá bằng midpoint của bản ghi, nhưng bỏ cả sự kiện thực thi của mọi nhánh. Ước lượng khi quyết định dùng duy nhất báo giá đã đủ điều kiện. Phân tích độ nhạy cho phép khớp cả ở giá niêm yết có cờ. Không suy ra mọi ngày có cờ đều đóng cửa.

Trường hợp có tài sản rời K5 hoặc vượt ràng buộc, gate ưu tiên trở về target khả thi ở lần giao dịch đủ điều kiện. Lãi/lỗ và số đơn vị chạy liên tục qua ranh giới kỳ. Tỷ lệ đổi tỷ trọng vàng được tính trên sự kiện, với turnover theo chênh lệch vị thế trước/sau khớp.

Điểm số hồi cứu chính tính trên các return sau 29/09/2023. Hai cửa sổ con đã ghi trong protocol. Fit/căn chỉnh các mô hình mới được phép học thêm khi nhãn trong lịch sử đã đáo hạn; không dùng kết quả OOS để đổi tham số. Tách các nhãn huấn luyện/căn chỉnh đi qua ranh giới phát triển và đánh giá. Kết quả so sánh và toàn bộ dự báo tính lại trong lượt này đều mang nhãn hồi cứu. Sử dụng thời điểm ghi thực tế và hash nguồn khi có một quyết định tương lai đủ điều kiện.
