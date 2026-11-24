# Đợt đối soát giá vàng SJC · 24/11/2026

Thay đúng phiên bản chuỗi bid/ask SJC HCM trên cùng kỳ lịch sử. K5, nhịp huấn luyện/chọn rổ/tính tỷ trọng, phép phối view, confidence, mô hình chi phí, hai cửa sổ con và thước đo lấy từ protocol.json đã khóa của GOLD–K5. Dựng lại dữ liệu đủ điều kiện D+1, labels, forecast, prior, posterior, target, NAV và phép kiểm định ghép cặp. B1/B2 được trình bày theo cả hai cách thực thi đã được định nghĩa ở các thí nghiệm trước: gross nguyên gốc Phase 1 và sau phí của nghiên cứu Phase 2.

Điều kiện để cân nhắc theo dõi ngầm là chênh lệch Sharpe sau phí của B2 + view trực tiếp so với B2 dương và nhất quán qua cả hai cửa sổ đã khóa. Ghi cả khoảng tin cậy, drawdown, sai số dự báo và độ nhạy với giá có cờ đứng. Triển khai cho user vẫn theo protocol xác nhận 60 quyết định đã đáo hạn. Không chọn lại một nhánh thắng sau khi xem kết quả.

Snapshot 2026 là bản hồi cứu. D+1 được dùng làm giả định mô phỏng. Thời gian tải dữ liệu được ghi tách biệt với thời gian áp dụng giả định. Báo cáo phạm vi xác minh độc lập và số ngày chưa có bằng chứng cùng sản phẩm, cùng thời điểm.
