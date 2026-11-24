# Nghiệm thu trạng thái tạo đề xuất trên Web, 23/11/2026

Trên bản Chat cuối B2 (`581729a9ae2b`), ba phiên Chromium trên Compose `portfolio-auth-demo` ở cổng 3100 đều hoàn tất chuỗi 4 lượt. Nhà đầu tư yêu cầu tạo đề xuất trong lúc tạm dừng, tải lại hội thoại, hỏi lý do, rồi hỏi lại tình trạng hiện tại. Sau khi đổi sang danh mục thứ hai của cùng chủ, người dùng hỏi kiến thức về Black–Litterman và xem được đoạn nguồn. Mỗi phiên mở lại và tải lại đề xuất cũ. [Bộ kiểm thử](../../apps/web/tests/browser/chat.e2e.ts) · [Tổng hợp phép đo](../../output/rag-status-20261123/browser/candidate-b2/browser-summary.json)

| Chỉ tiêu | Kết quả |
|---|---|
| Trạng thái trong 9 lượt | 3/3 lượt tạo bị chặn có thông điệp nghiệp vụ. 3/3 lượt hỏi lý do dùng mốc kiểm tra trước và nói rõ hệ thống chưa cung cấp lý do chi tiết. 3/3 câu hỏi hiện tại có mốc kiểm tra mới hơn. |
| Quyền xem | Cả 3 phiên chỉ hiện liên kết lịch sử khi dashboard đúng danh mục xác nhận có đề xuất. Liên kết cũ biến mất sau khi đổi danh mục. Tài khoản thứ hai nhận 404 ở 12/12 lần đọc đề xuất, bằng chứng đề xuất, hội thoại và job của chủ thứ nhất. |
| Tác động | 0 lần gọi provider trong 12 lượt. Cả 9 lượt trạng thái không ghi bằng chứng Knowledge, không gọi truy xuất Knowledge và không có dependency ID. Trước và sau mỗi phiên đều có 64 job Portfolio, 62 đề xuất và 64 lượt tính Quant. |
| Nguồn kiến thức | 3/3 câu hỏi trả lời bằng kết quả lexical từ corpus đang phục vụ. Đoạn văn trên Web khớp đoạn trích ghi trong tin nhắn. |
| Dữ liệu sau restart bản B2 | 3/3 hội thoại mới khớp hash trước restart. Hội thoại cũ và đề xuất cũ giữ nguyên ID, run ID, hash tin nhắn, đầu vào, tỷ trọng, facts và evidence. Đã thực sự restart Web, Chat API, Chat worker và Portfolio API. |

Đề xuất và hội thoại đối chứng thuộc tài khoản nhà đầu tư đã đăng nhập. Receipt của lần tính cũ cung cấp các giá trị ghim để đọc lại. Cơ sở dữ liệu có 14 lượt lịch sử `FAILED / SYSTEM_PAUSED` thuộc các chủ khác. Nhánh hiển thị cũ được kiểm bằng [test thành phần](../../apps/web/tests/chat-turn-status.test.tsx). Kết quả Chromium cho nhánh tạm dừng dùng lượt đã lưu của đúng chủ trên backend mới. [Receipt của lần tính cũ](../../output/concise-explanation/paid-final-receipt.json) · [Ảnh thẻ trạng thái đã kiểm tra](../../output/rag-status-20261123/browser/candidate-b2/round-1/status-current.png)

## Độ trễ từ khi bấm gửi đến khi hiện câu trả lời

| Luồng | Số mẫu mỗi bản | p50 A | p95 A | p50 B2 | p95 B2 |
|---|---:|---:|---:|---:|---:|
| Tạo đề xuất khi đang tạm dừng | 3 | 885 ms | 1.414 ms | 1.502 ms | 2.132 ms |
| Hỏi lý do lượt trước | 3 | 886 ms | 952 ms | 1.177 ms | 1.517 ms |
| Kiểm tra tình trạng hiện tại | 3 | 884 ms | 893 ms | 986 ms | 1.708 ms |
| Hỏi kiến thức sau khi đổi danh mục | 3 | 880 ms | 911 ms | 3.046 ms | 4.126 ms |

Bản A và B2 dùng cùng image Web và cùng đề xuất đối chứng. Trên B2 có một đợt nghiệm thu HTTP chạy cùng khoảng thời gian. [Số đo bản A](../../output/rag-status-20261123/browser/browser-summary.json)

Mỗi lần chạy mở một browser context mới và đăng nhập lại. Lượt tạo là lượt gửi đầu tiên của hội thoại. Ba câu tiếp theo dùng cùng phiên đã mở. Các dịch vụ backend chạy liên tục trong ba lần đo. Chưa đo thời gian gửi câu hỏi đầu tiên ngay sau khi backend khởi động lạnh. p50 là trung vị, p95 dùng nearest rank nên bằng giá trị lớn nhất trong ba mẫu.

## Chạy lại

Dùng stack `portfolio-auth-demo`, có hai tài khoản kiểm thử nhà đầu tư, ít nhất hai danh mục của tài khoản thứ nhất và receipt của đề xuất cũ. Worker nghiệm thu phải là worker Chat duy nhất đang chạy của Compose project, với `CHAT_LLM_ENABLED` tắt và `CHAT_PROVIDER_URL` trống. Stack đang ở trạng thái tạm dừng. Dùng Chromium đã cài của project. Mỗi tài khoản có 10 lượt thử đăng nhập trong một cửa sổ 15 phút. Nếu nhiều đợt đo liên tiếp gặp HTTP 429 ở màn hình đăng nhập, chờ cửa sổ hiện tại kết thúc rồi chạy tiếp ở thư mục của lượt chưa có receipt.

Từ gốc repo, chạy lệnh sau để chụp ba bộ giá trị gốc trước khi cập nhật dịch vụ.

```sh
cd apps/web
export PLAYWRIGHT_BASE_URL=http://127.0.0.1:3100 E2E_DISPOSABLE_STACK=1
rag_browser_dir="$(mktemp -d)"
run_browser_rounds() {
  for round in 1 2 3; do
    RAG_STATUS_MODE="$1" RAG_STATUS_OUTPUT="$rag_browser_dir/round-$round" \
      npx --no-install playwright test chat.e2e.ts --grep 'real Chat paused followups' || return 1
  done
}
run_browser_rounds baseline
```

Khi Web, Chat và Portfolio đã chạy phiên bản cần nghiệm thu, kiểm tra ba hội thoại trên cùng cấu hình.

```sh
run_browser_rounds exercise
```

Sau khi restart bốn dịch vụ trên cùng các volume và chờ chúng khỏe, kiểm tra lại trong các phiên đăng nhập mới.

```sh
run_browser_rounds verify
```

Ba giai đoạn ghi file riêng trong thư mục của từng lần chạy. Có thể kiểm tra checksum của [các receipt và ảnh đã đóng băng](../../output/rag-status-20261123/browser/candidate-b2/receipts.sha256) bằng lệnh sau từ gốc repo.

```sh
(cd output/rag-status-20261123/browser/candidate-b2 && shasum -a 256 -c receipts.sha256)
```
