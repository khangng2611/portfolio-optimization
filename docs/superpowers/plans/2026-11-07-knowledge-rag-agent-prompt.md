# Prompt bàn giao cho agent triển khai

Copy nội dung dưới đây cùng file plan Knowledge/RAG MVP sang agent có quyền truy cập workspace này.

```text
Hãy hiện thực Knowledge/RAG MVP và bộ đánh giá hội thoại tiếng Việt cho project:
/Users/nguyenkhang/Documents/MASTER/Thesis/portfolio-optimization

Đọc và thực thi plan:
docs/superpowers/plans/2026-11-07-knowledge-rag-mvp.md

Mục tiêu: Chat trả lời kiến thức có nguồn/corpus version và bổ sung giải thích cho recommendation từ canonical facts. Làm backend/API trước, integration thật đạt rồi mới frontend. Giữ cách trả lời kiểm soát theo plan; không mở rộng thành free-prose agent hoặc thay thuật toán đầu tư.

Trước khi sửa, đọc AGENTS, TECHNICAL_SPECIFICATION_PHASE_2, IMPLEMENTATION_STATUS và các Chat/UI handoff mới nhất; kiểm tra status/diff. Chat/LLM và UI đang có thay đổi chưa commit, phải giữ và tích hợp theo source hiện tại. Không reset/stash/clean, không đụng extensions_C_v1/, nghiên cứu, secrets hoặc dữ liệu/volumes cũ. Không giả định riêng HEAD chứa đủ baseline.

Thực hiện tuần tự K0→K4, TDD cho logic/security mới, reuse house patterns và giữ diff nhỏ. Kiểm thử baseline UI với backend thật trước; nếu có blocker liên quan thì sửa có regression. Tự giải quyết lựa chọn triển khai thông thường theo plan; chỉ hỏi khi gặp xung đột thật về quyền, dữ liệu hoặc phạm vi sản phẩm.

Backend: Knowledge owner-service/DB/worker/migrations, corpus Markdown manifest và lifecycle CLI, scoped retrieval, pgvector, read-only Chat tool, immutable citations/evidence, consent version và provider quotas. Không thay numerical facts/hash, confirmation/accept semantics hoặc tự gọi allocation từ câu hỏi kiến thức.

Frontend: dùng ui-ux-pro-max tại /Users/nguyenkhang/.codex/skills/ui-ux-pro-max/SKILL.md và Figma project “Portfolio Optimization · Product UX · 24.10.2026”, file YKRbiOAJNoVA9DaSZHc7Wc. Đọc design/handoff mới nhất, giữ controls/layout/tokens hiện tại, bổ sung nguồn tham khảo và consent states rồi align API. Không redesign toàn app, không thêm admin UI.

Unit tests có thể inject provider; nghiệm thu backend/browser phải dùng PostgreSQL/Keycloak/Chat/Portfolio/Quant thật. Không mock HTTP hoặc sửa SQL business results để tạo bằng chứng integration. Verify đúng receipt cũ sau restart, không thay bằng chạy luồng mới. Báo tách offline, lexical, hybrid provider thật, browser, persistence và eval; case chưa chạy phải ghi not run.

Chưa có phê duyệt ngân sách mới: không gọi embedding/LLM trả phí, không coi API key hoặc consent/quota cũ là quyền chi tiêu. Hoàn tất phần offline/lexical/adapter/UI không phụ thuộc phí trước. Chuẩn bị lệnh paid acceptance có dry-run, ước tính/cap; chỉ chạy khi người dùng cấp budget cụ thể. Đề xuất cap tổng 1 USD trong plan chưa phải quyền đã được cấp. Không thay Auto Recharge.

Hoàn tất fixtures eval, smoke/verify scripts, setup/runbook và status docs; tự review diff và sửa findings trong phạm vi. Giữ evidence/ảnh/log/cache/credentials ngoài Git. Chưa commit/push/merge hoặc sửa Google Sheet; trả danh sách trạng thái checklist cần cập nhật để người dùng duyệt riêng.

Bàn giao cuối: hành vi/API/migrations đã thay đổi, cách chạy/verify, lệnh và kết quả thực/skips, breakdown eval/usage, bằng chứng restart và giới hạn còn lại. Chỉ đánh dấu hoàn tất các gate thực sự đạt; tiếp tục các việc độc lập nếu paid gate chờ ngân sách.
```
