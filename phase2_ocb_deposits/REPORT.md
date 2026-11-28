# Tiền gửi OCB một tháng và VFF trên cùng ngày mở và đáo hạn

Kho lưu mã chứa kết quả tính toán, URL nguồn và hash kiểm chứng. Các PDF và HTML đã tải trong thư mục `evidence/` nằm trong bản lưu nghiên cứu. Dùng URL và hash trong manifest để lấy lại đúng tài liệu khi tái lập.

**Trong 8 kỳ có tài liệu công khai ghi nhận mức lãi trước ngày mở sổ, OCB sinh lãi trung bình 0,309% và NAV VFF tăng 0,572%. Nếu mua mới VFF và bán hết sau một tháng theo kịch bản phí và thuế dưới đây, lợi suất VFF còn −1,540%.** Cả 8 kỳ đều có cùng thứ tự. Các con số là phần trăm lợi suất cho một lần nắm giữ một tháng. [Kết quả từng cặp và hai NAV gốc](runs/20261125-ocb-1m-vff/pairs.csv)

| Mẫu | Số kỳ | OCB đáo hạn | VFF theo NAV | VFF bán hết, kịch bản phí và thuế |
|---|---:|---:|---:|---:|
| Có công bố mức lãi trước ngày mở và có bằng chứng biểu còn áp dụng | 8 | +0,309% | +0,572% | −1,540% |
| Chọn các kỳ sớm nhất không chồng lấn trong 8 kỳ trên | 3 | +0,308% | +0,528% | −1,583% |
| Toàn bộ ngày mở xác minh được khi rà soát hồi cứu | 13 | +0,310% | +0,559% | −1,553% |
| Chọn các kỳ sớm nhất không chồng lấn trong cả 13 kỳ | 6 | +0,310% | +0,542% | −1,569% |

**Ví dụ mở ngày 04/02/2025, đáo hạn 04/03/2025.** Biểu OCB áp dụng từ 01/01 ghi 3,90%/năm. Khảo sát đăng ngày 13/01 đã xác nhận mức này và khảo sát ngày 10/02 vẫn xác nhận cùng biểu từ 01/01. Trong 28 ngày, 10 triệu đồng gửi OCB sinh khoảng 29.918 đồng tiền lãi. NAV VFF tăng từ 23.979,24 lên 24.093,60 đồng/CCQ, tương đương lãi khoảng 47.691 đồng trước chi phí bán. Nếu mua mới và bán hết sau 28 ngày, cùng số vốn đó lỗ khoảng 163.310 đồng theo kịch bản. [Biểu OCB](runs/20261125-ocb-1m-vff/evidence/20250102171454.pdf) · [Khảo sát tháng 1](runs/20261125-ocb-1m-vff/evidence/survey3.html) · [Khảo sát tháng 2](runs/20261125-ocb-1m-vff/evidence/survey32.html)

## Điều kiện chọn ngày

- Kiểm tra trong lịch nghiên cứu 14/01/2020–29/04/2026. Đã rà 46 tệp biểu lãi cá nhân của OCB ứng với 39 ngày hiệu lực khác nhau. Mốc được lấy từ nội dung văn bản vì tên tệp đôi khi lệch một ngày. Một tài liệu lãi suất cơ sở cho vay được nhận diện và loại riêng. Tập nguồn công khai này chưa bao phủ mọi lần thay đổi trong sáu năm. [Danh sách PDF, ngày hiệu lực, URL và hash](runs/20261125-ocb-1m-vff/screened_sources.csv)
- Chấp nhận chính ngày hiệu lực, hoặc một ngày trong khoảng mà nguồn khảo sát **nêu đích danh ngày bắt đầu của biểu đang áp dụng**, khớp lãi suất với PDF OCB. Khoảng xác minh kết thúc đúng ngày khảo sát. Việc hai PDF có cùng mức lãi không tự tạo ra khoảng hiệu lực. Có 1 cặp trùng ngày hiệu lực in trên biểu (14/11/2023) và 12 cặp nằm trong các khoảng được đối chiếu theo cách này. Trong 13 cặp, 8 cặp còn có bài công bố mức lãi đúng sản phẩm **trước** ngày mở. Phần xác nhận sau ngày mở chỉ phục vụ kiểm toán hồi cứu, không mô phỏng tín hiệu mà nhà đầu tư có thể dùng để chọn ngày. [Bảng đối chiếu hiệu lực](runs/20261125-ocb-1m-vff/verified_rates.csv) · [Hồ sơ nguồn](runs/20261125-ocb-1m-vff/evidence.json)
- Giả định một cá nhân gửi 10 triệu đồng, VND, tiết kiệm thông thường tại quầy, nhận lãi cuối kỳ theo biểu cơ sở. Đáo hạn sau một **tháng lịch**. Tiền lãi bằng vốn × lãi suất năm × số ngày thực gửi / 365. Chỉ giữ kỳ có ngày mở và ngày đáo hạn danh nghĩa đều là phiên trong bộ lịch dự án. Kỳ cần dời do ngày nghỉ được loại để tránh suy đoán lịch làm việc của chi nhánh. [Phương pháp tính lãi OCB](runs/20261125-ocb-1m-vff/evidence/20220531144039.pdf) · [Điều khoản tiết kiệm](runs/20261125-ocb-1m-vff/evidence/20240723102005.pdf)
- Ở hai đầu kỳ phải có NAV/CCQ gốc, chưa làm tròn, đúng ngày của VFF, FMarket mã quỹ 21. NAV dùng để đo kết quả sau giao dịch. Không lấy giá điền tiếp từ bảng định giá ngày hoặc dịch sang kỳ NAV kế bên. Trong 213 ngày ứng viên, 62 ngày mở ngoài lịch phiên, 63 ngày đáo hạn ngoài lịch phiên, 1 kỳ ra ngoài mẫu, 61 ngày thiếu NAV mở và 13 kỳ thiếu NAV đáo hạn sau khi đã qua các điều kiện trước. Các ngày mở có cặp chạy từ 14/11/2023 đến 10/06/2025, kỳ cuối đáo hạn 10/07/2025. [Dữ liệu NAV dự án](../trusted_baseline/datasets/funds/full/VFF.csv) · [Nhật ký loại từng ngày](runs/20261125-ocb-1m-vff/excluded.csv)

## Ý nghĩa khi so với danh mục

Cột NAV VFF bằng NAV cuối chia NAV đầu trừ 1. Đây là mức thay đổi giá trị của phần nắm giữ. Cột bán hết giả định nhà đầu tư cá nhân mua mới với phí mua 0%, bán toàn bộ khi dưới 12 tháng, phí mua lại 2% và thuế 0,1% tính trên giá trị bán. Công thức là (NAV cuối / NAV đầu) × (1 − 0,020 − 0,001) − 1. Mức 2,1% đánh trên cả giá trị chứng chỉ quỹ, nên có thể lớn hơn toàn bộ mức tăng NAV trong tháng. Ba bản tin quỹ cho các thời điểm trong giai đoạn thử ghi nhận biểu phí này. Mô phỏng bỏ qua làm tròn số đơn vị, phí chuyển tiền, thời gian tiền về và ưu đãi riêng của đại lý. Chưa kiểm chứng việc khớp từng lệnh hoặc quyền lợi phân phối riêng ngoài NAV. [VinaCapital 10/2023](runs/20261125-ocb-1m-vff/evidence/20231115.pdf) · [11/2024](runs/20261125-ocb-1m-vff/evidence/20241213.pdf) · [06/2025](runs/20261125-ocb-1m-vff/evidence/20250715.pdf) · [Cách tính tiền bán trong bản cáo bạch VFF](https://vinacapital.com/wp-content/uploads/2025/07/20250725_VFF-Ban-cao-bach-sua-doi-bo-sung-07.2025.pdf)

Có thể ghi vào báo cáo Phase 2 rằng **trong mẫu này, OCB cho số tiền cuối kỳ cao hơn khi khoản đầu tư được mở mới và cần bán hết VFF đúng một tháng sau đó**. Với một vị thế VFF đã có sẵn hoặc được tiếp tục nắm giữ, tuổi lô và phần thực bán quyết định phí. Các cặp chồng lấn, số giai đoạn thị trường ít và việc chỉ lấy ngày có đủ chứng từ hạn chế khả năng khái quát. Ứng dụng tái cân bằng mỗi 5 phiên cần mô hình riêng về tiền gửi bị khóa, đáo hạn và rút sớm trước khi cân nhắc thay VFF.

Có thể tái lập ngoại tuyến từ thư mục gốc bằng `venv/bin/python phase2_ocb_deposits/runs/20261125-ocb-1m-vff/replay.py`. Script xác minh hash các đầu vào, tạo lại từng cặp, lý do loại và các chỉ tiêu trung bình số học. [Manifest](runs/20261125-ocb-1m-vff/manifest.json) · [Kết quả tổng hợp](runs/20261125-ocb-1m-vff/results.json)

Mô phỏng tiếp theo đã chạy 23 lần tái cân bằng HYBRID cách nhau 5 phiên, theo dõi gốc OCB còn khóa, lãi khi rút một phần và phí bán theo từng lô VFF. [Kết quả mô phỏng danh mục](rebalance_5/REPORT.md)
