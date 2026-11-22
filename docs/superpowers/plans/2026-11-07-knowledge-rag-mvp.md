# Knowledge/RAG MVP và đánh giá hội thoại tiếng Việt

> Bàn giao triển khai cho agent khác. Ngày lập: 07/11/2026.
> Thứ tự bắt buộc: backend → integration thật → frontend → browser thật → review.
> Đây là plan; chưa triển khai Knowledge hoặc cho phép phát sinh phí provider.

## 1. Mục tiêu, quyết định và giới hạn

Người dùng hỏi kiến thức tài chính/phương pháp trong Chat và nhận nội dung có nguồn truy nguyên được. Khi giải thích một đề xuất, tài liệu chỉ bổ sung kiến thức; weights, constraints, policy, timestamps và kết quả luôn lấy từ Portfolio/Quant/Market canonical.

MVP dùng **corpus nhỏ được duyệt và câu trả lời có kiểm soát**. LLM chỉ chọn các đoạn/claim đã duyệt từ kết quả retrieval; backend render nội dung và citations. Không phát prose tài chính tự do rồi gọi đó là đã verify. Đây là mặc định đề xuất vì các câu hỏi lựa chọn trước đó chưa được trả lời.

- Tái sử dụng Python/FastAPI/SQLAlchemy/Alembic/httpx, auth/observability và durable SQL worker của hệ thống. Không thêm agent framework, vector database bên ngoài, reranker hoặc broker topology mới.
- Knowledge có API/worker/migrations và `knowledge_db` riêng. Chat gọi API; không đọc Knowledge SQL, không có FK xuyên service.
- Corpus v1 chỉ chứa kiến thức PUBLIC đã duyệt. Không nhận tài liệu riêng tư, upload PDF, OCR, archive, HTML hoặc URL tùy ý. Không làm admin UI trong đợt này.
- Không hiện thực business preferences/views, holdings/ledger, PAPER, Research, model promotion hoặc thay thuật toán/risk mapping trong plan này.
- Embedding adapter chọn `text-embedding-3-small`, 1536 dimensions; model/dimension/parser/chunker/retrieval version được pin. Giữ nguyên dialogue provider hiện tại, không tự nâng model.
- Paid ingestion/query embedding/LLM evaluation mặc định **tắt**. Không coi API key hiện có hoặc ngân sách Chat cũ là phê duyệt ngân sách đợt này. Đề xuất tổng trần nghiệm thu 1 USD, chỉ bật khi người dùng cho phép; mặc định ngân sách là 0. Không bật Auto Recharge. Không có paid evidence thì báo gate đó `not run`.

Các cơ sở cần đọc: `docs/TECHNICAL_SPECIFICATION_PHASE_2.md` §§9.6, 12, 14; `docs/software/IMPLEMENTATION_STATUS.md`; các plan/handoff Chat và UI mới nhất. Tại lúc lập plan, Chat/LLM và UI V2.3–V2.5 đang chưa commit; không dùng riêng HEAD 7f4ffb8 làm baseline của phần này.

## 2. Backend và hợp đồng

### A. Baseline và hạ tầng an toàn

1. Đọc AGENTS áp dụng, kiểm tra git diff/untracked và các handoff mới nhất. Lưu danh sách baseline; giữ nguyên `extensions_C_v1/`, nghiên cứu, credentials, volumes và thay đổi khác. Không reset/stash/clean hoặc tự commit baseline.
2. Chạy lại unit/typecheck và luồng browser backend thật trên UI hiện tại với provider trả phí tắt: đăng nhập PKCE → onboarding → Chat confirmation → allocation → review → explicit accept → reload/reconnect. Bổ sung case expired → refresh/publish cùng universe → proposal mới; xác nhận target cũ còn nguyên. Sửa blocker liên quan trước khi nối RAG, không refactor diện rộng.
3. Thêm service dưới `services/knowledge/`, dùng cấu trúc owner-service hiện có. API host port 8006; health `/health/live`, `/health/ready`. API không có provider key; worker giữ key cho indexing.
4. Do PostgreSQL hiện tại chưa có pgvector, thêm **Knowledge PostgreSQL riêng** trong local Compose để tránh đổi image/volume của cluster đang phục vụ Portfolio. Dùng PostgreSQL 17 cùng baseline, build extension pgvector từ release chính thức đã pin version/commit; pin image digest sau khi build/verify. Chỉ thêm volume mới, DB không publish host port. Không đổi major PostgreSQL hoặc reset cluster hiện có.
5. Provision owner/migrator/runtime credentials riêng; privileged setup cài extension, runtime chỉ DML. Bootstrap/upgrade/setup/contracts/tracing/boundary checks phải nhận service mới theo pattern hiện có. Không đưa secret vào output, OpenAPI hay Compose config dump.

### B. Corpus, indexing và lifecycle

- Đặt corpus nội bộ tại `services/knowledge/corpus/`: manifest và 12 ghi chú tiếng Việt ngắn do dự án soạn, mỗi ghi chú 2–4 đoạn/claim độc lập đã đối chiếu nguồn. Chủ đề: EW; MVO; covariance; diversification; Black–Litterman; ML views; risk profile/policy; target khác holdings; freshness; model approval; phí và turnover; giới hạn backtest. Không hứa hiệu suất hay suitability.
- Mỗi claim có ID ổn định, text được duyệt, source title/HTTPS URL/section locator, ngôn ngữ và reference tối thiểu. Dùng nguồn sơ cấp/official hoặc nghiên cứu gốc; kiểm tra URL và quyền lưu trữ, không chép toàn văn tài liệu ngoài. Tách kiến thức phương pháp khỏi quy tắc riêng của ứng dụng.
- Manifest gồm document key/version, content SHA-256, visibility=PUBLIC, published_at nếu biết, available_at thực tế, parser/chunker version và provenance review. Không bịa ngày xuất bản hoặc backdate availability. Bản đầu bắt đầu DRAFT; activation là thao tác operator rõ ràng có audit.
- CLI đọc UTF-8 Markdown/JSON dưới corpus root; chặn path traversal/symlink ra ngoài, binary/oversize/HTML/script, hash mismatch và thiếu metadata. Giới hạn 64 KiB/document, 1 MiB/batch, 1000 chunks/corpus. Không tải URL trong runtime; URL chỉ là citation đã kiểm tra lúc chuẩn bị corpus. Phạm vi này chưa đáp ứng ingestion PDF/malware scan/arbitrary URL của full spec.
- Dữ liệu Knowledge: document versions/chunks, corpus versions/membership, indexing jobs, embedding invocation ledger và lifecycle audit. Dùng typed timestamps, immutable hashes; mỗi đoạn đã duyệt là một chunk để citation không cắt rời nghĩa. Không chia lại âm thầm khi parser/chunker đổi.
- Job flow DRAFT → INDEXING → READY hoặc FAILED; active corpus là pointer sang một READY version. Worker leased/fenced/deduped/checkpointed; POST chỉ enqueue. Activate/deactivate có version precondition và idempotency. Activate corpus mới là atomic pointer swap, không để truy vấn thấy nửa batch; rollback bằng chọn lại READY version đã có.
- Không xóa document version/chunk đã được cite trong MVP. Deactivate loại khỏi retrieval mới, giữ explanation cũ và citation evidence; legal deletion/full lifecycle là công việc riêng.

### C. API và quyền

Hợp đồng Knowledge v1 tối thiểu, cùng error/pagination/idempotency/If-Match conventions hiện có:

| API | Quyền và hành vi |
| --- | --- |
| `POST /api/v1/knowledge/indexing-jobs` | `data-operator` + `knowledge:write`; nhận normalized manifest/notes từ CLI, 202 + job reference; không nhận arbitrary URL/path. |
| `GET /api/v1/knowledge/indexing-jobs/{id}` | Operator có scope; status/progress counts/errors an toàn. |
| `GET /api/v1/knowledge/corpora` | Operator có scope; version/status/active/hash. |
| `POST /api/v1/knowledge/corpora/{id}/activate` | Operator, If-Match + idempotency; chỉ READY, audit actor/reason. |
| `POST /api/v1/knowledge/corpora/{id}/deactivate` | Operator, If-Match + idempotency; không xóa evidence cũ. |
| `POST /internal/v1/knowledge/retrieve` | Authenticated Chat machine client + `knowledge:retrieve`, đúng audience; không expose qua public BFF. |

Retrieval request gồm query đã redaction, server-selected corpus version và `as_of` do Chat chốt khi bắt đầu lượt. Không nhận owner/role/visibility/SQL/URL do LLM chọn. Query embedding là vector tùy chọn từ Chat worker; kiểm dimension/model/index version và finite numeric values. Knowledge không gọi provider trong đường request retrieval.

Response gồm corpus/version/hash, retrieval/index versions, mode (`HYBRID`/`LEXICAL`), reason và tối đa 5 passages: document_version_id, chunk_id, claim_id, text/hash, source title/URL/locator, published_at/available_at. Không trả vectors hoặc credential nội bộ.

- Lọc PUBLIC + corpus membership + active/eligible state + available_at <= as_of trong SQL **trước** ranking/limit/context. Bản không PUBLIC bị từ chối ở ingestion v1 và luôn bị loại ở retrieval, kể cả nếu tồn tại qua fixture/migration. Không tin client-supplied scope.
- Text search dùng PostgreSQL full-text `simple` và Unicode normalization; vector dùng exact cosine trên tập đã lọc. Hai nhánh lấy tối đa 20 ứng viên, hợp nhất Reciprocal Rank Fusion với k=60, top 5, tie-break chunk ID. Corpus nhỏ chưa cần HNSW/IVFFlat.
- Lexical branch chỉ nhận match thật. Vector branch chỉ nhận cosine similarity >= 0.45, policy version `knowledge-retrieval-v1`; đây là ngưỡng ban đầu phải báo cáo trong eval, không tự hạ để làm gate xanh. Nếu hết chứng cứ thì trả danh sách rỗng có reason.
- Timeout Knowledge 3 giây và context passages <=8000 UTF-8 bytes. Provider/query embedding lỗi hoặc chưa được phép thì lexical retrieval; Knowledge lỗi thì Chat dùng template/thiếu bằng chứng. Không làm hỏng allocation đã có.

### D. Embeddings, consent và Chat orchestration

- Index embeddings chỉ gửi PUBLIC notes đã duyệt. Query embeddings chỉ nhận query đã redaction; không gửi profile, weights, IDs, toàn lịch sử hoặc ledger. Giữ key trong worker qua overlay opt-in.
- Tái sử dụng checkbox `llm_consent`, bổ sung consent version: version 2 nói rõ external LLM **và embedding truy vấn**. API preferences nhận thêm optional `consent_version`; client cũ mặc định version 1. Existing consent=true vẫn phục vụ hành vi LLM cũ nhưng **không** cho phép query embedding mới cho tới khi xác nhận version 2. Không tự upgrade consent trong DB. Consent off/revoke chặn outbound cả hai đường.
- Query embedding chạy trong Chat worker qua adapter nhỏ dùng httpx; indexing adapter chạy ở Knowledge worker. Reuse nguyên tắc invocation reservation, bounds và no-paid-retry; không tách framework chung chỉ để tái sử dụng vài dòng.
- Embedding requests có deadline 5 giây, response/body/input limits và kiểm vector chiều dài 1536/finite/nonzero. Invocation index dedupe theo content hash + model/dimension; query dedupe theo job + purpose. Reservation trước I/O, persist output trước bước sau; crash/timeout không rõ kết quả không tự gọi trả phí lại. Không ghi query/prompt/vectors/key vào logs/SSE.
- Mặc định acceptance tối đa 100 embedding requests và 20 dialogue requests, đồng thời chịu ngân sách USD được user cấp. Giá phải kiểm từ official docs ở execution time; reserve chi phí upper-bound trước request và đối soát actual token usage. Không có giá/giới hạn rõ thì fail closed. Replay không tạo invocation mới; counter tách ingestion/query/dialogue và báo tổng thực, uncertain reservations riêng.
- Thêm `intent="knowledge"` vào message schema, intent classifier, UI options và pending-message validator. Câu hỏi tổng quát không bắt tạo danh mục; giữ owner/account authorization và grant preflight hiện có cho delayed work. Không lấy quyền từ nội dung passage.
- `retrieve_knowledge` là tool read-only trong Chat allowlist. Lưu retrieval checkpoint theo job để restart dùng cùng corpus/chunks. Nếu corpus deactivated trước publish, kiểm tra lại và trả thiếu bằng chứng; không lặng lẽ đổi sang corpus khác giữa lượt.
- Với câu hỏi knowledge: cho LLM chọn tối đa 3 claim references từ candidate set bằng schema strict; backend chỉ render approved text tương ứng, không nhận prose/URL/số liệu do model tạo. Không provider/consent thì hiển thị tối đa 3 passages như **đoạn tham khảo**, không gắn nhãn AI đã xác minh ý nghĩa. Không có evidence thì nói thiếu nguồn.
- Với explanation đề xuất: giữ canonical render hiện có, thêm phần kiến thức tham khảo riêng có citations; không dùng tài liệu giải thích nguyên nhân weight cụ thể hay tự suy metric chưa có.
- Không tăng số lượt dialogue trên mỗi job: knowledge selection dùng purpose `explanation` hiện có, tối đa một intent + một explanation. Extend schema có version và preserve model/prompt provenance. Không để budget cũ và mới đếm lệch hoặc chạy hai explanation calls.
- Chat lưu immutable evidence riêng: corpus/index/retrieval/prompt/schema versions, retrieved/selected chunk IDs, source locators, excerpts tối thiểu, query hash, verification/fallback reason, usage và latency. `evidence_hash` riêng; không thay `facts_hash`, input hash hoặc quantitative results cũ. Không FK sang Knowledge.
- Chat message thêm type `knowledge`; recommendation card thêm optional `knowledge` evidence/citations. Hỗ trợ history cũ không có trường mới. SSE chỉ phát nội dung đã render/kiểm references, không stream raw provider tokens hoặc passage instructions.

## 3. Frontend sau backend integration

- Dùng `ui-ux-pro-max` và đúng Figma file `YKRbiOAJNoVA9DaSZHc7Wc`, project “Portfolio Optimization · Product UX · 24.10.2026”. Đọc handoff V2.5 và trạng thái mới nhất khi triển khai, tái sử dụng Chat workspace, controls, spacing/tokens; không quay lại layout cũ hoặc redesign toàn app.
- Thêm mục đích hỏi kiến thức, knowledge card, phần “Nguồn tham khảo” mở rộng: title, section, document version/date nếu có và excerpt liên quan. Link HTTPS an toàn mở tab mới, chống XSS; không render raw HTML từ notes/provider.
- Phân biệt nguồn kiến thức với dữ liệu và kết quả danh mục. Hiển thị lexical/template/missing evidence bằng lời dễ hiểu, không dùng score retrieval như confidence tài chính.
- Checkbox consent có copy/version mới và yêu cầu xác nhận lại cho query embedding; quyền tắt luôn rõ ràng. Không tự bật khi mở hội thoại hoặc chuyển tab.
- Giữ explicit allocation confirmation/accept, SSE cursor/reconnect, history pagination, owner/session isolation, pending retry và focus/keyboard/mobile của V2.5. Không thêm corpus admin UI; CLI đủ vận hành MVP.

## 4. Kiểm thử và điều kiện nghiệm thu

Thực hiện TDD cho trust boundaries/state mới. Tests unit có injected provider; bằng chứng integration phải là services/DB/auth thật. Không dùng route interception hoặc sửa SQL business results để chứng minh luồng thật.

### Gates theo thứ tự

1. **Baseline:** ghi source revision + fingerprint diff của working tree và test results thực. Mốc lịch sử 06/11 có 536 Python/core + 4 skips, 131 web tests; UI V2.5 có thể làm số lượng thay đổi. Không dùng số lịch sử làm kết quả mới.
2. **Storage/auth/indexing:** real PostgreSQL + pgvector, migrations/metadata và DB grants; reject wrong role/audience/scope/nonpublic manifest/path traversal/hash mismatch. Duplicate POST cùng body trả cùng job; khác body conflict. Crash/retry/fencing không tạo double chunks/corpus hoặc double paid invocation. Atomic activate/rollback và history citation bất biến.
3. **Retrieval:** text tiếng Việt có/không dấu, acronyms EW/MVO/BL_ML, exact cosine thật, model/dimension mismatch, no-match, source-after-cutoff, draft/deactivated/nonpublic content, deterministic ordering và outage fallback. Unit fake embeddings phải được ghi là unit; live hybrid gate dùng provider embeddings thật khi được phép.
4. **Chat/security:** cross-owner conversation/job/history/SSE, grant expiry/revoke/account disabled, prompt injection trong query/passage, forged claim/URL/fact IDs, stale canonical facts, consent v1/v2/off/revoke và crashes trước/sau outbound call. Không có unsolicited allocation/accept/trade/promotion hoặc dữ liệu riêng trong context/logs.
5. **Eval:** tạo 60 cases có expected intent, allowed claim IDs/canonical facts, expected abstention và category; 20 dev + 40 held-out, đóng băng trước tuning. Có single/multi-turn, ambiguity, sai số/nguồn, stale/cutoff, injection/cross-owner, no evidence và outage. Ít nhất 20 answerable và 20 safety/abstention cases; không để tổng điểm che lỗi nhóm nhỏ.
6. **Ngưỡng release MVP:** 0 unauthorized mutation/data leak và 100% numerical fidelity, citation-reference integrity, confirmation/consent safety trên cases áp dụng; retrieval Hit@5 >=90% trên answerable held-out; intent >=90%; unsupported abstention >=95%. Human review kiểm support/relevance cho toàn bộ answerable held-out, >=95% claims được hỗ trợ. Báo mẫu số; LLM judge không là bằng chứng duy nhất. Không hạ ngưỡng/xóa case để pass.
7. **Performance/cost:** đo retrieval server p50/p95 riêng lexical/hybrid (không tính provider latency), mục tiêu p95 <=1 giây trên corpus v1; đo toàn turn và xác nhận deadlines/fallback. Báo actual tokens/calls và cost estimate có nguồn giá; không gọi estimate là hóa đơn. Paid eval mặc định chưa chạy; sau khi cấp budget chạy ít nhất 10 cases thực đại diện trong trần trước full batch.
8. **Browser thật:** PKCE → knowledge question → source card → bật consent v2 nếu đã cho phép provider → follow-up → giải thích recommendation với canonical card + knowledge sources → explicit accept ở UI hiện có. No-source/provider/Knowledge outage, consent revoke, 390px/desktop, keyboard, reconnect/session expiry và reload. Restart Chat/Knowledge API/workers/Web, verify đúng receipt cũ/corpus/chunks/evidence hashes và invocation count không tăng. Không tự restart stack ngoài local đã xác nhận.
9. **Regression/review:** toàn Python/core/web suites, tsc, Ruff scoped, production build, stable OpenAPI export, Compose config và real boundaries. Chạy lại Chat/P1/Market receipts phù hợp, không bịa GitHub CI/staging/UAT. Đọc lại diff, bỏ artifact/log/screenshot/design dump khỏi changes được bàn giao; giữ tests/fixtures eval/curated notes cần tái lập.

Release local mặc định Knowledge lexical hoạt động; hybrid/paid capability chỉ được đánh dấu hoàn tất sau gate provider thật. Không gọi lexical-only là đã nghiệm thu semantic RAG. Nếu một safety gate fail, RAG ở trạng thái chưa nghiệm thu, Chat canonical/template tiếp tục dùng được.

## 5. Chia việc và đầu ra bàn giao

| Mốc | Đầu ra phải kiểm chứng trước khi sang bước sau |
| --- | --- |
| K0 — nền hiện tại | Baseline source/test inventory; browser backend thật trên UI mới; blockers liên quan đã xử lý. |
| K1 — Knowledge backend | DB/pgvector/migrations/auth, corpus CLI/indexing/lifecycle và lexical retrieval thật. |
| K2 — retrieval + Chat | Embedding opt-in/ledger, hybrid adapter, read-only tool, consent version, immutable evidence; integration/restart/security tests đạt. |
| K3 — UI | Citation cards/copy/consent theo Figma hiện tại, unit/fixtures QA và browser backend thật. |
| K4 — nghiệm thu | Eval/report/receipts, regression/review, setup/runbook/status/checklist phản ánh đúng phạm vi và giới hạn. |

- Commit source cho corpus manifest/curated notes, eval dataset/runner và smoke scripts tái chạy được. Không commit provider vectors/cache, credentials, raw logs, screenshots, receipts hay full external PDFs.
- CLI/runner phải có offline mặc định, paid opt-in và verify-receipt; tài liệu ghi lệnh đúng theo implementation cuối cùng, cách index/activate/deactivate/rollback, ngân sách và fallback. Không để lệnh placeholder.
- Báo API/schema/migration changes, commands/results/skips, eval breakdown, measured usage và source fingerprints. Cập nhật `IMPLEMENTATION_STATUS.md` bằng bằng chứng mới; không làm mới bằng chứng cũ chỉ bằng đổi ngày.
- Checklist: đối chiếu KN-01..05, CHAT-04/05/13, FE-22, DB-07, E2E-08 và thêm granular rows nếu cần. KN-02 chỉ hoàn thành phần manifest Markdown; KN-06 chỉ lifecycle MVP. Không tick full PDF/URL ingestion, private corpus, historical research RAG hay production lifecycle.
- Không tự commit/push/merge hoặc cập nhật Google Sheet nếu prompt triển khai không cấp các hành động đó. Bàn giao diff sạch trong phạm vi feature và danh sách checklist đề nghị cập nhật; giữ baseline/unrelated changes.

### Nguồn kỹ thuật đã đối chiếu khi lập plan

- [OpenAI embedding guide](https://developers.openai.com/api/docs/guides/embeddings): reference model/dimension. Agent phải kiểm lại availability, request limits và giá lúc thực thi; không suy từ credits Chat cũ.
- [pgvector official repository](https://github.com/pgvector/pgvector): exact vector search/PostgreSQL integration. Pin release/build tương thích ở K1; không dùng latest.

### Các phần cố ý để sau

Admin upload/PDF/OCR/crawler/malware pipeline; private/tenant corpus; ANN/reranking; free prose generation; full deletion/retention automation; Research historical RAG; production HA/load certification. Rủi ro còn lại: corpus nhỏ giới hạn mức bao phủ, source citation không tự chứng minh correctness của claim, redaction chưa đảm bảo loại mọi PII tự do, và paid/provider gates cần ngân sách riêng.
