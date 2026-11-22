# Release demo kín v0.1.0-demo.1

Ngày chuẩn bị 11/11/2026. Release được chốt trên nhánh
`codex/private-vps-demo`, từ base commit
`67540341a7819cfc4cc8ea4b202a325bafd0b583` và snapshot mã phần mềm hiện có.
Tag `v0.1.0-demo.1` xác định commit nguồn để dựng lại trên VPS.

## Phạm vi

- Luồng nghiệm thu gồm Auth nội bộ, hồ sơ rủi ro, danh mục DEMO, EW/MVO,
  accepted target, ownership và lịch sử sau restart.
- Snapshot giữ mã Chat, Knowledge và Phase 1 đang tích hợp với ứng dụng.
  Các tính năng này có điều kiện chuẩn bị dữ liệu và nghiệm thu riêng.
- Dùng Compose hiện có, mọi published port bind loopback, browser đi qua SSH.
- Thêm `scripts/check_private_demo.py`, regression tests và gate cấu hình trong CI.
- Nguồn trong release gồm migration, contract, lockfile, fixture và corpus Markdown.
  Credentials, volume, output nghiên cứu, model đã fit và `.generated` được giữ
  ở ngoài snapshot chuyển sang VPS.

## Kiểm tra trên máy phát triển

Các lệnh chạy trong checkout release với Python venv và `npm ci` riêng.

| Kiểm tra | Kết quả |
| --- | --- |
| Cài dependency qua `setup_software.py prepare` | Đạt, `pip check` đạt |
| Python/software và portfolio-core | 602 passed, 5 skipped |
| Private-demo regression trong bộ Python | 17 passed |
| Ruff theo phạm vi CI, gồm lệnh kiểm tra demo | Đạt |
| Web Vitest | 136 passed |
| TypeScript | Đạt |
| Next.js production build với dependencies trong checkout | Đạt |
| Production Web Docker image | Build đạt, container riêng trả 200 cho `/health/live` và `/login` |
| Export contracts từ package của checkout release | 12 contracts, ổn định |
| Generated Compose thực tế | 30 services, loopback rõ ràng, provider gate đạt |
| Staging template placeholder validation | Đạt phạm vi cú pháp template cũ |
| npm audit cho production dependencies | 0 advisory được báo cáo |

Năm test được skip gồm ba Chat PostgreSQL storage/concurrency probes, một
Knowledge PostgreSQL probe và một Market concurrency probe. Các test này cần
DB dùng riêng và opt-in. Suite có một deprecation warning Starlette/AnyIO.

Full npm audit báo ba dependency bị ảnh hưởng trong nhóm công cụ test, gồm
Vite mức high và Vitest/@vitest/mocker mức moderate. Web được chạy bằng image
production standalone trong hướng dẫn demo. Xem các advisory của
[Vite](https://github.com/advisories/GHSA-587h-7wmj-h5pm) và
[Vitest](https://github.com/advisories/GHSA-qxg6-89mg-rqv8).

Web image kiểm tra có ID
`sha256:2b87630745b5ea878aa62473245e18bb4b9eab71e29b69557f08956ad84bf268`.

## Nghiệm thu trên VPS

Các gate trên kiểm chứng mã và cấu hình. Lần chuẩn bị release này chưa kết nối
VPS, chạy lại toàn bộ stack bằng volume mới hoặc browser end-to-end trên VPS.
Docker build trên máy ARM cũng cần được đối chiếu với lần build amd64 thật.

Thực hiện [runbook demo kín](PRIVATE_VPS_DEMO.md) và ghi nhận từng checkbox
nghiệm thu tại cuối runbook. Chỉ đánh dấu bản cài VPS sẵn sàng khi các bước API,
browser, ownership, persistence và kiểm tra cổng public đều đạt.
