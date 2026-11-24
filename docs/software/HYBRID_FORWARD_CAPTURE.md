# Thu thập dữ liệu walk-forward HYBRID MVO 60%

[Bản khóa phương án và kỳ đánh giá](../superpowers/plans/2026-11-23-hybrid-mvo60-walk-forward.md) áp dụng từ 24/11/2026 đến 23/11/2027. Container local `hybrid-forward-capture` bắt đầu thu lúc **19:00 GMT+7** và có thể bắt đầu muộn đến trước **20:00 GMT+7**, mốc thông tin của quyết định nghiên cứu. Nếu một nguồn lỗi hoặc tập phiên cổ phiếu còn thiếu, bộ thu có thể thử lại sau 10 phút, tối đa ba lượt hoàn tất trước cutoff. Mỗi lượt giữ receipt riêng. Từ 24/11 đến 30/11/2027, các lượt thu thập phục vụ đối soát dữ liệu định giá đến sau khi kỳ kết thúc.

## Bằng chứng dữ liệu

Kho local `output/hybrid-mvo60-forward/` chứa các lượt `evaluation`, `settlement` và `rehearsal` tách riêng. Mỗi lượt ghi manifest, một receipt cho từng phản hồi, và summary. Nội dung phản hồi được nén và lưu theo SHA-256 của byte gốc. Một lỗi mạng hoặc lỗi kiểm dữ liệu được ghi vào receipt của nguồn. Lượt gián đoạn có thể còn các receipt nguồn đã lưu dù chưa có summary. Giữ cả các phản hồi bị từ chối để điều tra.

Bộ thu thập lấy lịch VNINDEX và lịch sử điều chỉnh của 30 mã KBS, archive giá bán SJC HCM và NAV VFF sản phẩm 21. Dữ liệu GOLD khởi tạo đến hết tháng 04/2026 lấy từ seed đã kiểm SHA-256. Từ tháng 05/2026, mỗi lượt lưu đúng phiên bản archive tháng mà nguồn trả. Mã băm raw và thời gian nhận cho phép xác định phiên bản đã biết tại từng cutoff. Trường `available_by_decision` yêu cầu bản ghi vượt kiểm tra parser và phản hồi đến trước hoặc đúng mốc 20:00 của phiên tương ứng. Trạng thái `recorded` xác nhận việc lưu nguồn. Kiểm độ phủ qua `recent_stock_gaps`, `latest_gold_date`, `latest_nav_date` và nguồn gốc mỗi receipt. Quant vẫn chạy kiểm chất lượng và kiểm model riêng khi phát hành đầu vào phục vụ.

Khi dựng panel cho một quyết định, chỉ chọn các receipt hợp lệ đã nhận trước mốc quyết định. Giữ revision và hash của từng đầu vào đã dùng, gồm phiên bản dữ liệu huấn luyện. Không dùng ngày NAV, ngày giá hoặc giờ khởi chạy để thay cho thời điểm nhận. Ngày máy tắt, mất mạng hoặc tỉnh sau khung thu thập có thể thiếu bằng chứng. Ghi khoảng trống theo lịch kỳ đã khóa. Theo dõi receipt và so với lịch VNINDEX trước khi đánh giá. Service nghiên cứu `hybrid-forward-study` đọc các receipt này để dựng panel và kiểm tra từng cutoff.

## Kiểm trên máy local

Lịch được khai báo trong [Compose overlay](../../infra/local/compose.hybrid-forward.yaml). Mở log bằng `docker logs portfolio-auth-demo-hybrid-forward-capture-1`. Docker Desktop và máy local cần hoạt động trong khung giờ thu. Khi khởi động lại stack, giữ overlay để Compose tiếp tục quản lý container này. Sau 30/11/2027, lịch ngừng gọi nguồn.

Chạy lại trong khung giờ nếu phát hiện lượt lỗi. Giữ tham số `--rehearsal` cho một lượt kiểm riêng ngoài lịch.

```sh
.venv-software/bin/python -m market_service.hybrid_forward_capture \
  --directory output/hybrid-mvo60-forward \
  --gold-seed output/hybrid-mvo60-forward/setup/gold-warmup.csv \
  --protocol output/hybrid-mvo60-forward/setup/protocol.md \
  --rehearsal
```

Giữ kho bằng chứng cùng bản sao protocol, seed và receipt hashes để tái lập kỳ kiểm định. Kích thước đo được trên lượt thu đầu tiên khoảng 1,6 MiB. Dung lượng tăng theo các phiên bản dữ liệu thực tế mà nguồn trả.

## Tính quyết định và chấm kỳ MVO 60%

Service `hybrid-forward-study` chạy độc lập với Web và Quant phục vụ người dùng. Image nghiên cứu không có kết nối mạng hay thông tin đăng nhập. Volume nguồn gắn chỉ đọc, thư mục kết quả nằm tại `output/hybrid-mvo60-forward/study/`.

- Runner khóa mã nguồn, protocol, cấu hình và phiên bản thư viện tại `evaluation/manifest.json`. Mỗi lượt thử có thư mục riêng tại `rehearsals/`. Khi khởi động lại cùng kỳ, mã và môi trường phải khớp manifest.
- Phiên VNINDEX đầu tiên từ 24/11/2026 là mốc 0. Mỗi 5 phiên, runner dùng dữ liệu đã nhận trong cửa sổ thu để tính quyết định trước 20:00. K5 chọn lại mỗi 20 phiên. Model được fit riêng cho nghiên cứu mỗi 10 phiên và ghi các booster native, hash dữ liệu fit, scaler, seed, thời điểm kết thúc nhãn và validation trong `artifacts/models/`.
- Mỗi quyết định có receipt tại `evaluation/ledger/YYYY-MM-DD.json`. Bốn phương án dùng cùng panel, K5, model, views, trạng thái thị trường và các ràng buộc của từng hồ sơ. Nếu VFF vượt freshness 7 ngày sau khi áp dụng buffer 5 phiên, receipt ghi ngày NAV, tuổi dữ liệu và `HOLD`. Có thể giữ model đã fit trên cổ phiếu cho kỳ tiếp theo. Một cutoff bị lỡ được ghi rõ khi lịch VNINDEX kế tiếp xác nhận phiên. Việc xử lý muộn không sinh tỷ trọng cho một quyết định trong quá khứ.
- Sau 30/11/2027, bộ chấm chọn lượt settlement gần nhất có lịch khớp và giá hợp lệ cho toàn kỳ, ghi các lượt bị loại rồi khóa input tại `scoring-inputs.json`. Mỗi phương án khớp tại giá đóng cửa phiên kế tiếp, trừ 10 bps trên turnover một chiều và hưởng lợi suất của tỷ trọng mới từ phiên sau. Kết quả `final.json` có phí, turnover, drawdown, biến động, tỷ trọng chênh lệch và lợi suất theo regime. Thiếu giá cần đối soát sẽ xuất hiện trong log. Thiếu bằng chứng thời điểm hoặc thiếu kỳ bình thường có tỷ trọng Tăng trưởng khác v1 sẽ cho `INSUFFICIENT_EVIDENCE`.

Từ thư mục repo, các lệnh sau chỉ tác động đến hai service nghiên cứu. Trên stack đang chạy cần giữ cùng project, env file và các Compose overlay đã dùng khi khởi động.

```sh
study_compose() {
  docker compose -p portfolio-auth-demo --env-file infra/local/.generated/.env \
    -f infra/local/compose.yaml -f infra/local/compose.hybrid-forward.yaml "$@"
}
# Image ML local cung cấp các thư viện solver và XGBoost. Lệnh build chỉ tạo image.
study_compose build ml-migrate
study_compose build hybrid-forward-study
study_compose up -d --no-deps hybrid-forward-capture hybrid-forward-study
study_compose logs --tail=20 hybrid-forward-study
study_compose run --rm --no-deps hybrid-forward-study rehearsal
```

Khi cần đối soát receipt, kiểm tra `status`, `reason`, `panel.availability` và `state.model`. Bộ thu cần Docker hoạt động cả khung 19:00–20:00 giờ Việt Nam. Không thay image nghiên cứu giữa kỳ nếu hash đã khóa thay đổi. Sau khi đã có hồ sơ chấm, lần khởi động lại đọc lại cùng kết quả.

### Quyết định phát hành

Để phát hành ứng viên, người phụ trách đối chiếu `final.json` với protocol, manifest, receipt và kết quả của cả ba hồ sơ. Khi được chấp thuận sau khi kết thúc kỳ, deploy phiên bản Portfolio API, Portfolio consumer và Quant consumer có hỗ trợ pin `hybrid-growth-normal-mvo60-v1`. Trong cấu hình Portfolio API, gắn báo cáo đã duyệt chỉ đọc tại `/run/hybrid-study/final.json` và đặt `HYBRID_REVIEWED_REPORT_SHA256` bằng SHA-256 của đúng file. Bật chế độ HYBRID theo quy trình pilot hiện có khi hai nhánh Quant đều READY. Thiếu file, sai hash, mở sớm hoặc báo cáo chưa đạt sẽ trả `SYSTEM_PAUSED` khi đã yêu cầu dùng ứng viên. Nếu không cấu hình digest, policy hiện tại vẫn dùng phiên bản v1. Luồng reviewer model và freshness của stack phục vụ tiếp tục áp dụng. Trước khi mở rộng cho người dùng, kiểm tra tạo mới, chấp nhận và mở lại đúng đề xuất trên desktop và mobile theo protocol.
