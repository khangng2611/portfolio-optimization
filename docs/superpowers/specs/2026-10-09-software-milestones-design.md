# Software milestones — 09/10/2026

Theo yêu cầu hiện thực của người dùng trên kiến trúc đã chốt, hoàn thiện nền tảng
hiện hữu bằng Market Data, staging template, fixtures và hướng dẫn setup/test.
Không thay đổi ranh giới service trong đặc tả Phase 2. Giữ nguyên nghiên cứu và
các thay đổi chưa commit đã có trong checkout.

## Phạm vi và giao thức

- Giữ Identity/Keycloak, Next BFF, Portfolio và Quant hiện hữu. Swagger của các
  API có Bearer security scheme để nhập JWT, health không yêu cầu JWT.
- Market Data sở hữu database/migrations, asset master, append-only price
  revisions, ingestion jobs, outbox/inbox và immutable snapshots. Namespace
  `market_service`, Python 3.12 và dependency pin theo các service hiện hữu.
- `POST /api/v1/market/ingestions`: role `data-operator` + scope `market:write`,
  `Idempotency-Key`, HTTP 202. Nhận normalized observations hoặc fetch một
  server-registered CSV dataset bằng dataset ID, không nhận đường dẫn/URL tùy ý.
  CSV stock/fund/gold có unit khai báo; lưu VND/share, VND/unit, VND/tael.
- Worker xử lý command qua durable quorum queue `market.ingest.v1`, ghi inbox,
  revisions và trạng thái job cùng transaction. Outbox chỉ đánh dấu sau broker
  confirm. Retry lỗi transport, stale/invalid input trả lỗi terminal quan sát được.
- Snapshot chốt danh sách assets theo thứ tự và observation revision IDs, content
  hash, date range, source metadata, publication/availability time; missing/stale
  data không tạo READY. Cùng dữ liệu xuất cùng hash; revision mới không sửa snapshot cũ.
  Người đọc cần role hợp lệ và scope `market:read`; job thuộc issuer/subject người tạo.
- Provider registry và CSV import là nền ingestion cho stock/fund/gold. Không
  tuyên bố đã crawl live upstream hay Quant đã tự xây bundle từ Market snapshots.
  Quant vẫn dùng prepared bundles có provenance theo thiết kế hiện hữu.
- Compose local thêm DB/roles riêng, migrations/API/dispatch/consume Market;
  bootstrap giữ credentials cũ, bổ sung secret mới, không reset volumes/realm.
  Có đường nâng cấp cấu hình local cũ có thể chạy lại.
- Staging có deployment template với external DB/broker/Redis/Keycloak, HTTPS,
  secret env và image tags bắt buộc. Không tạo demo/test accounts và không tự deploy.
- Core giữ version `0.1.0`, bổ sung golden numerical fixtures có provenance và
  changelog/compatibility policy. Không tuyên bố parity legacy khi chưa có fixture chứng minh.
- Hướng dẫn tiếng Việt là điểm vào setup, Swagger và Postman; collection/environment
  không chứa credentials. Test client chỉ dùng local disposable realm.

## Nghiệm thu

Python/API/core tests và web tests/typecheck/build; export contracts deterministic;
migrations SQLite và Compose config; core wheel import và fixture ngoài repo.
Live DB/broker/JWT/persistence checks chỉ ghi passed khi thực sự chạy trên Docker.
Nếu Docker daemon không đáp ứng, giữ cấu hình và báo rõ bước chưa kiểm chứng.
