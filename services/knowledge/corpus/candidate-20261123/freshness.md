## freshness-definition
Đề xuất mới phải dùng dữ liệu đủ mới theo chính sách hệ thống; nguồn và thời điểm được ghim trong kết quả.
## freshness-history
Tỷ trọng và nguồn dữ liệu của một mục tiêu đã lưu được ghim theo đề xuất gốc. Dữ liệu mới hết hạn có thể chặn lần tính tiếp theo, còn người dùng vẫn xem được lịch sử mục tiêu của mình.
## freshness-window
Với rổ tài sản đã chọn, hệ thống chỉ xét các quan sát đã khả dụng tại lúc kiểm tra. Tuổi dữ liệu tính theo ngày lịch từ ngày quan sát tới ngày kiểm tra. Quan sát đủ điều kiện gần nhất quá 7 ngày sẽ chặn việc tạo đề xuất mới.
## vff-nav-availability
Với dữ liệu VFF theo chính sách baseline hoặc selected v1, hệ thống chờ 5 phiên giao dịch để NAV đủ điều kiện rồi kiểm tra tuổi NAV theo ngưỡng 7 ngày lịch. Với selected live NAV v2, NAV đã thu thập và xác minh dùng được từ lúc khả dụng mà không chờ thêm 5 phiên. Cả hai chính sách tính tuổi từ ngày NAV.
