# Giải thích ngắn mặc định

Người dùng đã duyệt hướng này trong chat: trả lời ngắn, chi tiết mở thêm, giữ nguồn/evidence; regression/eval tiếng Việt trước OpenAI thật trong cap1USD hiện tại.

Giữ finite claims/templates. Metric claims tách RSI/MACD/momentum theo mã; câu hỏi RSI chỉ lấy RSI và ngày đã ghim. Claim có summary ngắn cùng text đầy đủ; không thay quantitative evidence/facts/hash. Overview liên hệ hồ sơ/rổ/selection/views; focused answer chỉ phần được hỏi. Confidence vẫn ghi rõ không phải xác suất khi được hỏi.

Coverage claim chỉ kết luận không có view âm trong các ML views đã lưu khi evidence COMPLETE; PARTIAL/UNAVAILABLE báo chưa đủ dữ kiện, không suy toàn universe/model. Corpus passages giữ trong citations, không lặp trong prose. Finite provider schema dùng enum từ allowed IDs và required IDs theo câu hỏi; validator độc lập vẫn kiểm hash/group/asset, fallback giữ nguyên.

UI v2 hiện answer trước phần chi tiết đang đóng mặc định; nội dung đầy đủ, evidence, nguồn, audit và canonical allocation vẫn truy cập được. Legacy messages không viết lại và giữ hành vi đọc hiện tại. Không redesign, thêm dependency hoặc đổi controls.

Đã cân nhắc: chỉ sửa prompt ít diff nhưng không tách được feature dump; free prose linh hoạt nhưng vượt scope/khó kiểm số liệu; chọn chia nhỏ claims + summary deterministic với finite LLM selector, theo hướng người dùng đã duyệt.

Không sửa lỗi chọn strategy, HYBRID, thuật toán/model/data/receipt cũ; giữ các thay đổi đồng thời. Không commit/push/merge/Sheet. Cap1USD/approval/quotas/counters/Auto Recharge giữ nguyên. Report usage thực tách estimate/invoice.
