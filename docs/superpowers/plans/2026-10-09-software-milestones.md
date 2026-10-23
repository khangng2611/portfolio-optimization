# Software milestones implementation plan

**Goal:** Hoàn thiện bốn mốc nền tảng và setup/API testing trên kiến trúc đã chốt.
**Spec:** `docs/superpowers/specs/2026-10-09-software-milestones-design.md`.
**Architecture:** Bổ sung Market Data owner service vào monorepo hiện có; giữ
Identity/BFF, Portfolio/Quant và numerical core boundaries.
**Tech stack:** Python 3.12, FastAPI 0.118.0, SQLAlchemy 2.0.43, Alembic 1.16.5,
PostgreSQL, RabbitMQ quorum queues, Keycloak và Next.js hiện hữu.

## Constraints / review focus

Giữ toàn bộ uncommitted work; không commit/reset volume/realm. Không in secrets.
Kiểm tra idempotency conflict, cross-owner access, duplicate delivery, invalid
units/date ranges, stale/missing snapshot data, failed publish và immutable revisions.

## Task 1 — Market Data (primary agent)

- [x] Viết tests API/auth/idempotency/revision/snapshot/outbox và xem failure.
- [x] Thêm `services/market-data` package/models/migration/API/provider/workflow/worker.
- [x] Mở rộng wire contracts, broker topology và contract exporter; thêm Bearer Swagger.
- [x] Chạy tests Market và toàn bộ backend, migrations; sửa lỗi được chứng minh.

## Task 2 — Infra/CI/staging (independent agent)

- [x] Thêm DB/roles/scopes/audience/broker ACL/topology và Compose processes Market.
- [x] Giữ secrets cũ, tạo upgrade path idempotent cho local stack đã bootstrap.
- [x] Cập nhật CI và thêm staging template fail-closed với external dependencies.
- [x] Test bootstrap/config và ghi giới hạn triển khai staging.

## Task 3 — Core fixtures/versioning (independent agent)

- [x] Thêm fixtures EW/MVO/BL_ML, test determinism và constraints với provenance.
- [x] Viết changelog/compatibility, kiểm tra wheel ngoài source tree.

## Task 4 — Setup/API testing (independent agent)

- [x] Viết hướng dẫn tiếng Việt và reusable setup/check entry point.
- [x] Tạo Postman collection/environment cho auth, portfolio, jobs, Market snapshots.
- [x] Kiểm tra JSON/script/help; cập nhật links README.

## Integration and review

- [x] Full Python/lint/contracts/web gates; Compose/staging configuration.
- [x] Kiểm tra Docker availability; chạy live smoke/boundaries/persistence nếu khả dụng.
- [x] Independent review của các thay đổi, sửa critical/important findings và ghi
  bằng chứng thực tế trong `docs/software/IMPLEMENTATION_STATUS.md`.

## Kết quả

09/10/2026:150 Python tests,21 web tests,lint/contracts/migration roundtrips và
local/staging config đạt. Reviewer độc lập không có Critical/Important blocker.
Docker daemon timeout nên live boundary/smoke/persistence không chạy.
Bằng chứng và phần deferred tại `docs/software/IMPLEMENTATION_STATUS.md`.
