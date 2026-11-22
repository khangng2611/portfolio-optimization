# Tiến độ software app

Cập nhật cấu hình dev 18/11/2026 theo yêu cầu mới nhất. Budget hiện tại 1,00 USD,
quota 100 lượt/approval và 100 lượt/ngày UTC. Giữ approval ID và usage đã ghi nhận,
không reset bộ đếm. Các mức 0,50 USD và quota thấp hơn bên dưới là lịch sử kiểm thử.

## OpenAI explanation acceptance — 22/11/2026, cap 1 USD

Người dùng xác nhận giữ cap1USD; runtime1.00/quotas100/approval/counters giữ nguyên,
embeddings tắt và không đổi Auto Recharge. Offline26passed; native BL_ML model v5
cũ qua explicit confirmation và 2conversations TEST. Recommendation23df1353;
evidenceCOMPLETE, không accept target hoặc thay numerical algorithm/model.

OpenAI gpt-6-luna thật11calls: 8plans được validator chấp nhận,3fallback an toàn;
paid acceptance **PARTIAL, chưa PASS**. Hai follow-up không gửi ID giữ đúng
recommendation, đúng GVR và báo ACB thiếu view. Facts/evidence/claims11/11khớp;
23citation occurrences/3claims khớp corpus knowledge-vi-v1/manifest/hash/pinnedGit.
Citations phương pháp/policy tách khỏi nguồn số liệu canonical run.

Actual tokens21.650input/1.234output; adapter estimate0,003323250USD, reservations
0,0187USD. Chưa đối soát invoice/cache breakdown; không gọi estimate là số tiền
bill thực tế. Paid browser/hybrid/full24-case paid eval NOT RUN. Nội dung còn
lặp/dài; overview có2invalidplans, RSI có1plan thiếu limitation; không đổi prompt
hoặc code trong lượt kiểm thử. Restart Chat API/worker rồi verify đúng hai paid
receipts và hai template receipts cũ đạt, không phát sinh provider calls bởi verify.
Chi tiết/output/checklist tại
[ALLOCATION_EXPLANATION.md](ALLOCATION_EXPLANATION.md), ignored report
`output/allocation-explanation/openai-20261122/quality-report.json`.

## Allocation explanation evidence — 22/11/2026

Đã thêm sidecar Quant → Portfolio, migration nullable c9222026e001, owner/delegated
read API `/recommendations/{id}/evidence`, finite Chat claims và bốn nhóm UI V2.7.
Canonical numerical JSON/hash, algorithms, confirmation/accept và receipts cũ
được giữ độc lập. Legacy thiếu raw views/features trả PARTIAL/NOT_RETAINED,
không infer lại; invalid evidence trả UNAVAILABLE mà không bỏ numerical result.
Chi tiết source/commands/gates tại [ALLOCATION_EXPLANATION.md](ALLOCATION_EXPLANATION.md).

Backend thật MVO DEMO đã có receipt76081cdc; Chat template có receiptfc4d87d6,
explicit confirmation +5follow-ups,0provider calls, worker dev đã khôi phục.
Đây là synthetic numerical inputs qua services/DB/broker thật, không phải
native BL_ML acceptance. Sau đó kiểm đúng scoped readiness thấy BL_ML READY:
đã chạy native v5 cũ, recommendationd022809e-8c99-466b-9f9b-94a15b9e7284,
evidenceCOMPLETE,5MLviews dương/0âm và features5equities,0provider calls.
Giữ model70716105/epoch16/11 và point_in_time_certified=false. Không train/
refresh/publish mới; kết luận blocker universe-level ban đầu không áp dụng
cho portfolio-scoped readiness.

Offline explanation24/24ca synthetic; topic/phrase assertions21/21 so với3/21
renderer cũ, không coi là human/LLM quality score. Lexical heldoutHit@5 vẫn14/16
(87,5%), dev8/8; không gọi embedding/LLM trong eval này. Hybrid NOT RUN.
Paid dry-run bị chặn vì runtime1USD không khớp trần0,50USD đã duyệt trong chat
hiện có; không coi dòng cấu hình dev trên là quyền tăng chi tiêu trong task này.
Không có paid calls mới, không đổi Auto Recharge hoặc counters.

Web168tests, TypeScript/Ruff và production builds đạt. Browser thật sau restart
ở1440/390/375CSSpx đạt, xem đủ4nhóm/5nativeviews/features/2citations, không
overflow/runtime errors; Enter/disclosures và draft-only suggestion hoạt động.
Restart9services đã đổi rồi verify chính native d022, Chat MVO fc4d, backend MVO
7608 và original v5 f1a6 receipts đạt; hashes/messages/usage không đổi. Preservation
các row/artifacts/accounts/volumes/catalog history và154tin nhắn cũ đạt; dev
config nguyên vẹn. Full Python/core đạt960passed,10skipped,1warning; sau đó
nhóm regression future-tail evidence đạt17passed (overlap, không cộng tổng).
Report tại `output/allocation-explanation/verification.json`. Real EW receipt
riêng chưa chạy; unit EW/no-ML đạt. Checklist đề nghị ở runbook, chưa sửa Sheet.
Không kiểm screen reader/thiết bị vật lý hoặc gọi paid OpenAI/hybrid.
Không commit/push/merge hoặc sửa Google Sheet.

## Giải thích đề xuất nối tiếp — 18/11/2026

Đã tái hiện hai câu trong ảnh rơi về input_required/help khi quota nhóm hiện tại
đạt 20 calls. Tham chiếu đề xuất trước đây chỉ được gắn từ LLM intent plan và
bị giới hạn trong 4 tin nhắn. Backend nay tự tìm recommendation card gần nhất
trong đúng owner/conversation/portfolio và trước thời điểm câu hỏi hiện tại.
ID đã chọn rõ ràng vẫn ưu tiên. Lịch sử gửi cho LLM vẫn tối đa 4 tin; chỉ giữ
tham chiếu nội bộ và cờ has_recommendation. Câu hỏi giải thích rõ ràng bỏ qua paid
intent. “Đề xuất nào?” và “Vì sao phân bổ như vậy?” vào luồng giải thích.

Phần giải thích mở sẵn khi được yêu cầu, vẫn đối chiếu canonical facts. Request
không có kết quả phù hợp hỏi mở kết quả hoặc chuẩn bị đề xuất, không trả menu
chung. Thêm CHAT_LLM_APPROVAL_CALL_LIMIT (mặc định 20, chặn khi không hợp lệ,
trần 100). Demo dùng 40 calls/approval, 60 calls/ngày trong budget 0,50 USD đã
phê duyệt. Reservation tiền và kiểm tra owner/grant vẫn giữ hiệu lực.

Offline Chat/Knowledge regression 156 passed, 4 opt-in skips. Các test bổ sung
về quota lỗi và fallback khi hết quota đã chạy cùng bộ test tham chiếu/managed
policy, 20 passed. Web 151 tests và TypeScript đạt. Build Chat/Web đạt.
Luồng thật đọc một recommendation có sẵn, tạo hội thoại thử riêng và đi qua
năm turns. Sau hai turns xen giữa, cả hai câu trong ảnh đều trả đúng ID và
canonical facts/hash, không có allocation mới. Có thêm truy xuất kiến thức theo strategy trong canonical facts và đưa đúng
các đoạn đã cite vào phần giải thích sau khi recheck corpus/quyền. Bản bổ sung
đạt 161 backend tests, 4 opt-in skips. Hai lượt smoke tổng 10 turns dùng 10
provider calls, chi phí ước tính 0.001540250 USD trong budget 0,50 USD đã duyệt.
Receipt ở ignored output/knowledge-rag/followup-receipt.json và
followup-grounded-receipt.json. Chi tiết script/runbook ở KNOWLEDGE_RAG.md. Sau restart
thật Chat API/worker/Web, cả hai receipt mới và 14 receipt cũ đều khớp, usage
không tăng. Browser desktop/mobile mở sẵn phần giải thích từ đúng receipt sau
restart.

## Point-in-time audit model v5 — 18/11/2026

Đã audit read-only model70716105-ef74-4203-bfa6-9657f756e0b6 và đúng receipt
BL_ML f1a6761b-01da-42be-8258-2ecdf1eb3242. Chi tiết và lệnh chạy ở
[POINT_IN_TIME_AUDIT.md](POINT_IN_TIME_AUDIT.md). Không train/approve/publish
lại hoặc đổi model/result/point_in_time_certified; cờ vẫn false.

Hai snapshot training v1/serving v2, mỗi snapshot54.325observation, khớp Market
ledger qua transaction READ ONLY. Không thấy revision/quality đã ghim có
timestamp sau snapshot hoặc decision thật. 99normalized CSV,64metadata sidecar
và120raw references kiểm hash đạt. 35job thiếu sidecar riêng nhưng32job còn
legacy provenance;3job thiếu fetch receipt. Ledger chỉ revision1, published_at
trống cho toàn54.325observations; không chứng minh provider chưa từng sửa giá
trước first-seen. Historical publication/vintages vẫn NOT_EVIDENCED.

Training prefix1.700phiên×30equity có51.000ô:50.963observation nguồn và37carry
theo missing-session declarations. Toàn dependency biết trước epoch16/11 và
trước train thật. Toàn snapshot có96observation first-seen sau epoch, nhưng
ngoài prefix06/11. Model/snapshot artifacts thực sự tạo18/11; không coi chúng
đã sẵn sàng16/11. Chronology thật train/approve/publish/decision18/11 đạt.
Adjustment factors, universe/calendar/tradability chưa kiểm chứng. MAE/RMSE
dùng cùng validation fold với early stopping; chưa phải independent test.

Thêm CLI scripts/audit_model_point_in_time.py và16regression: future revision,
features/labels/hash, scaler validation/purge, K5/features/covariance future
tail, model tương lai và artifact bị thay. Audit logic có red/green; legacy raw
adapter sửa bằng regression, không sửa dữ liệu. Native boundary được inject
trong unit tests liên quan. Full source cuối861Python/core passed,6skipped;
Ruff/diff đạt. Lượt đầu843passed; một lượt giữa có1failure ở test Chat
test_requested_explanation_uses_method_from_canonical_facts_and_cited_passage
đang cập nhật đồng thời, isolated/full chạy lại trên source hiện tại đã đạt;
giữ log và không sửa Chat trong audit này. Browser/RAG eval/backtest/forward
test not run trong audit này.

Original BL_ML và training/review/publication/model receipts kiểm lại đạt;
model/result mục tiêu nguyên vẹn. Preservation tổng quát FAIL riêng bảng
portfolio: log ghi nhận accept200 lúc16:03:09 UTC+7 cho recommendationfafbc9fc
trên portfolio khác (c7a7d035...), cùng accepted_target mới sau capture. Audit
không gọi accept, không xác định actor từ log, không rollback/thay baseline.
Các bảng khác, file hashes, volumes/catalog history đạt. Không đánh dấu toàn bộ
preservation PASS. Giữ nguyên các thay đổi Chat/UI đồng thời trong workspace.

Evidence ngoài Git: output/point-in-time-v5/report.json, market-evidence.json.gz,
verification.json và preservation-diagnostic.json. Chưa commit/push/merge,
sửa Google Sheet hoặc bật certification flag.

## BL_ML v5 epoch16/11 — 18/11/2026, positive gate đạt

User đã duyệt huấn luyện/review model và cho phép provider trong trần tổng
0,50USD đã cấp. Train qua operator HTTP API/ML SQL queue/worker hiện tại,
job3a002f05-cf29-4406-8653-75e04b23bd68 SUCCEEDED sau1attempt, epoch16/11,
training_cutoff06/11, đủ30equity/150native members. Dùng snapshot v1
6aa157bf-aa7d-4b71-bd24-d3d0717ccd21; toàn prefix1700giá/30equity, calendar,
validity mask và từng training-prefix hash khớp chính xác snapshot live v2
8c2dc496-7d83-4cb2-bc3f-aee78732ee73. Không giả hai snapshot cùng ID/hash,
không cần thay NAV policy hoặc rebuild ML worker để train equity.

Model70716105-ef74-4203-bfa6-9657f756e0b6 được kiểm native hashes/load,
runtime/source code hashes, seeds/best_iteration, coverage và chronological
80/20 validation/purge5labels. 39.810 train rows, 10.020 validation rows;
train_label_end30/06/2025 < validation_start01/07/2025; MAE0.0378128444,
RMSE0.0535328016 cho return5phiên. Vẫn point_in_time_certified=false;
đây là operational acceptance, không chứng nhận hiệu quả backtest/đầu tư.

Reviewer dùng identity model-reviewer riêng, API If-Match version1 và
Idempotency-Key; retry giữ đúng review ID/version2. Đã đợi APPROVED và
artifact_ready=true. Approved manifest hash
d511678a0626d8a749b4e4dbd36cc58114702212fa9ba171d180403ecd1cca89;
payload candidate ngoài status/approval metadata nguyên vẹn. Quant resolver
kiểm production input-prefix cả30asset đạt trước publication. Bundle mới
e7587ecf33fe46c7aff88770b2a4d47d51fa90e71d875e8e233c57f4e880e92d
ghim approved model và snapshot live v2, publication SUCCEEDED qua worker.

**BL_ML thật PASS**: danh mục kiểm thử riêng10candidate (8equity+GOLD/VFF),
Chat hiển thị canonical input và nhận confirmation, Portfolio/RabbitMQ/Quant
chạy native inference/CLARABEL. K5 chọn CTG,DGC,FPT,GAS,GVR, active thêm GOLD/
VFF; GOLD có trọng số0, 6tài sản có trọng số dương. Strategy/requested_strategy
đều BL_ML, fallback_reason=null, sum/bounds/defensive đạt (VFF khoảng30%).
Recommendationf1a6761b-01da-42be-8258-2ecdf1eb3242; facts hash
cb8735214a29ffd1c2328a695aca2e25a19d2da75bda7328b4aba6613b16953f
khớp Chat/Portfolio. Inference pin đúng model7071/manifestd511 và epoch16/11.
Chỉ lưu đề xuất, không accept target.

OpenAI explanation VERIFIED: đúng1call, 688input/107output tokens, estimate
0,0001395USD; tracked project estimate sau lượt này0,002791625USD, dưới0,50USD.
Đây là ước tính ledger, không phải hóa đơn provider. Không gọi embedding/hybrid
mới hoặc đổi Auto Recharge. Provider usage nằm trong chính receipt Chat.

Đã restart ML API/worker, Quant API/publication/consume/dispatch, Portfolio
API/consume/dispatch, Chat API/worker và Web. Verify **chính** receipt BL_ML mới
đạt facts/hash/messages/usage/portfolio unchanged; không gửi luồng thay thế.
Training/review/publication receipts, approved manifest hash/150native members,
30prefix, receipt MVO cũ và publication bị từ chối cũ đều khớp sau restart.
Preservation receipt xác nhận rows/models/artifacts/accounts/volumes/catalog
cũ nguyên vẹn. Browser desktop1440/mobile390 đọc cùng đề xuất trước/sau restart
đạt, không tạo job khác. 827 Python/core tests passed, 6 skipped; 8harness tests
mới có red/green, Ruff/diff check đạt. Không đổi API runtime/migration/thuật toán;
script smoke thêm --strategy BL_ML và guard không fallback/native pins; receipt
MVO cũ vẫn verify được. RAG eval/research backtest/web build not run đợt này.

Runbook có request train/review/publication và lệnh smoke/verify. Evidence ngoài
Git: output/bl-ml-epoch-20261116/report.json, chat-flow-receipt.json,
pipeline-receipt.json, audit/log/screenshot cùng thư mục. Chưa commit/push/merge
hoặc sửa Google Sheet; trạng thái gate dưới đây là mốc kiểm tra trước khi train.

## BL_ML live acceptance — 18/11/2026, blocked bởi model epoch

Đã đọc toàn registry thật: đúng3 model, đều APPROVED/artifact_ready. Qua ML
service resolver thật, manifest/native hashes và XGBoost load đều đạt. Model
schema5 duy nhất `34fc4b8d-debe-4986-ab2a-e18b60e1e5f3` phủ30equity/150member,
manifest hash09115d2210636e4b92c2626b0b1d159f82ef7444d4a9a1b679ab107e2942e143.
Model fit_epoch02/11, training_cutoff23/10. Panel hiện tại decision17/11 yêu cầu
fit_epoch16/11, training price end06/11; production check trả
MODEL_EPOCH_MISMATCH. FPT training-prefix hash cũng khác. Model schema4
81449d2a-2e38-4e01-b695-cdac4a4bbb57 và schema3
47f3981b-268f-44c7-b508-c5458ee90331 không dùng cho selected schema5.
Không có CANDIDATE khác hoặc model đã duyệt phù hợp trong registry lúc kiểm tra.

Đã probe publication qua operator HTTP API/SQL queue/worker thật, dùng current
live snapshot và model v5 APPROVED cũ. Job6a9a1884-8114-450b-a1dc-93e82b1ebdb1
bị FAILED/PUBLICATION_INVALID sau1attempt; compatibility audit chỉ rõ epoch
không khớp. Không tạo bundle mới hoặc đổi con trỏ publication hiện tại.
Bundle live b2a2d5c87dfa5d6d129f9341b3a6b641274d8a38a662936dc8b5ffc4e9d77946
giữ nguyên; EW/MVO READY, BL_ML MODEL_UNAVAILABLE vì chưa gắn model tương thích.

Sau restart Quant API/publication worker, đúng job/hash từ chối vẫn khớp.
Receipt đề xuất MVO cũ vẫn khớp nguyên IDs/facts/messages/usage; preservation
receipt xác nhận rows/models/artifacts/accounts/volumes/catalog giữ nguyên.
5 offline readiness/publication/worker gate tests đạt. Không đổi runtime code,
train/review model, chỉnh epoch, lùi clock hoặc gọi provider trả phí (0 USD).

**Chưa đạt positive BL_ML gate:** chưa chạy native inference/Chat allocation
BL_ML, chưa có receipt đề xuất BL_ML mới để verify sau restart; browser/eval
not run. Receipt publication thất bại chỉ là negative gate, không thay thế
receipt allocation. Cần model schema5 APPROVED đúng epoch16/11 và matching
training-prefix/coverage trước khi tiếp tục; không tự huấn luyện trong phạm vi
user đang cấm train. Evidence ngoài Git: output/bl-ml-live/report.json và
publication-receipt.json. Runbook ghi preflight và tiêu chí acceptance cần chạy.
Chưa commit/push/merge hoặc sửa Google Sheet.

## NAV live v2 — 18/11/2026

User duyệt tách policy live khỏi buffer baseline. Snapshot selected mới dùng
`user-selection-live-nav-v2`: NAV VFF source/identity/hash đã được Market xác
minh, quality PASS và first-seen thật được dùng sau snapshot verification,
không chờ thêm 5 phiên. Tuổi vẫn tính từ ngày NAV tại Việt Nam, <=7 ngày.
Chỉ dùng ngày định giá không vượt phiên hoàn tất 18:00 mới nhất. NAV history
cho thống kê live căn theo valuation date; không chứng nhận publication ở quá
khứ và không dùng thay baseline backtest. GOLD/equity không đổi.

Snapshot/bundle cũ và selected v1/schema2 vẫn đọc theo policy cũ. Version mới
được pin qua snapshot/hash, bundle provenance, command SelectionContext và
selection hash; worker từ chối policy khác panel. OpenAPI Quant, event command
và schema context mở rộng enum, giữ default v1 cho command cũ. Không migration,
backfill, đổi thuật toán hay sửa numerical result/TTL/hash cũ.

TDD: đã quan sát tests live-policy và command-pin thất bại trước implementation.
Regression phủ NAV latest, verification time/first-seen, input tương lai,
quality/product identity, ngày 7/8, cutoff 18:00, reload immutable panel,
v1 còn lag, equity/GOLD không đổi và command-policy mismatch. 819 Python/core
tests passed, 6 skipped; focused cuối 20 passed/1 skipped. Ruff, contract export,
build ba backend image và diff check đạt. Fixture selected-source dùng ngày
Việt Nam hiện tại khi đọc rows vừa ingest, giữ nguyên ngày nguồn frozen và
test backdated cutoff; không nới business clock để làm test xanh.

**Backend thật PASS** qua Auth/JWT, PostgreSQL, publication worker, Chat review/
confirmation, Portfolio, RabbitMQ và Quant. Snapshot
8c2dc496-7d83-4cb2-bc3f-aee78732ee73, bundle hash
b2a2d5c87dfa5d6d129f9341b3a6b641274d8a38a662936dc8b5ffc4e9d77946.
VFF đủ điều kiện là NAV 17/11, tuổi 1 ngày; EW/MVO READY. MVO cho danh mục
kiểm thử FPT/VFF trả optimal bằng CLARABEL, 50/50, đạt sum/bounds/defensive.
Recommendation 829f5c78-fcda-41e5-99fd-6266ff25dead, canonical facts hash
196d415260d144b266435bc7033cf607179eba43a8d2f67a8c280cafb71ce09b
khớp Chat/Portfolio. Chỉ lưu đề xuất, không accept target.

Đã restart Portfolio/Quant API/workers, Market API, Chat API/worker và Web;
verify chính receipt mới và receipt stale cũ đạt, không gửi luồng thay thế.
Preservation receipt xác nhận rows, artifacts, accounts, volumes/catalog cũ
nguyên vẹn. Browser chỉ mở cùng đề xuất đã lưu, desktop1440/mobile390 đạt.
Provider tạm tắt khi test, usage rỗng/chi phí mới 0; đã khôi phục config dev
LLM bật, query embeddings tắt. BL_ML not run (MODEL_UNAVAILABLE, bundle không
ghim model); RAG eval not run vì không đổi truy xuất/LLM trong đợt này.

Lần readiness đầu bị INPUT_UNAVAILABLE do recreate thiếu override cờ selection;
đã khôi phục override local cũ trước khi chạy gate đạt. Runbook ghi rõ overlay
để tránh mất cờ khi recreate. Evidence ngoài Git: output/live-nav-policy/report.json,
receipt/log/screenshot cùng thư mục. Chưa commit/push/merge hoặc sửa Google Sheet.

## Làm mới đầu vào và lỗi Chat — 18/11/2026

Đã refresh nguồn thật cho 32 tài sản, toàn bộ AVAILABLE/PASS, cutoff phiên hoàn
tất 17/11. Snapshot mới 6aa157bf-aa7d-4b71-bd24-d3d0717ccd21, 54.325 observations,
hash b058ab86a698027154cd6e62386c81354f4f52e9194dbaf542171b9952e16537.
Publication 6f819d9d-25cf-45af-b7a3-a8f5ba437a60 SUCCEEDED qua operator API/worker,
bundle hash 96c887a99734c6365f5a10a5fe47ffeafe76063a4ef8c157f821154cf3e3d747,
valid_until 19/11/2026 14:24:17 UTC+7. Giữ publication/rows/artifacts cũ.

**Chưa đạt luồng tạo đề xuất thành công.** Lỗi INPUT_EXPIRED đã hết trên readiness,
nhưng MVO bị chặn VFF_STALE. Nguồn NAV có đến 17/11, trong khi observation đủ
điều kiện theo buffer 5 phiên chỉ đến 10/11, tuổi 8 ngày so với ngưỡng 7 ngày.
Không đổi buffer/freshness, clock, SQL business results hoặc huấn luyện model để
làm gate xanh. Chưa có recommendation mới từ lượt này.

Chat đọc allowlist mã lỗi ở cả Portfolio error envelope và FastAPI detail, giữ
INPUT_EXPIRED/VFF_STALE/GOLD_STALE/ASSET_DATA_STALE qua job/SSE. Không chuyển tiếp
raw upstream message. UI phân biệt bộ đầu vào hết hạn và NAV VFF quá cũ, chỉ rõ
nhờ operator cập nhật/phát hành dữ liệu rồi tạo yêu cầu mới, xem lại và xác nhận.
Lượt live expiry đầu tiên còn bị generic STALE_OR_INVALID_INPUT vì adapter chưa
đọc envelope của Portfolio. Giữ row FAILED đó; sửa bằng regression cho envelope
thật rồi chạy lại nhánh stale trên bộ mới. Live expiry trên bản cuối chưa chạy.

143 Chat/Knowledge tests passed, 4 opt-in skipped; 147 web tests, TypeScript,
Ruff và production Chat/Web builds đạt. API thật đi qua review/confirmation và
chặn đúng VFF_STALE. Browser desktop/mobile hiển thị đúng lý do và bước tiếp.
Sau restart Chat API/worker/Web, cùng receipt stale vẫn khớp message/error/usage.
Preservation receipt xác nhận rows, artifacts, accounts, volumes và catalog cũ
được giữ. Đợt này không tạo LLM invocation. Full positive MVO và BL_ML not run.

Lệnh verification mới nằm trong scripts/smoke_chat_input_refresh.py. Bằng chứng
ngoài Git ở output/chat-input-refresh/report.json và output/playwright/input-refresh.
Chưa commit/push/Google Sheet.

## OpenAI do dev cấu hình — 18/11/2026

Đã bỏ checkbox OpenAI, popup dữ liệu gửi đi và luồng đổi consent khỏi composer.
Giữ phần nguồn kiến thức và các lựa chọn nghiệp vụ của hội thoại. Dev điều khiển
qua CHAT_LLM_ENABLED và CHAT_QUERY_EMBEDDINGS_ENABLED, embedding mặc định tắt.
Key, budget và quota tiếp tục ở worker. Dữ liệu consent cũ chỉ giữ để tương thích
receipt, không còn quyết định quyền gửi ra provider. API preferences trả 403 sau
khi kiểm tra owner. Yêu cầu tạo conversation cấp consent cũng bị từ chối.
Không migration/backfill các hội thoại cũ.

Offline 128 Chat/Knowledge tests passed, 4 opt-in storage probes skipped;
145 web tests, TypeScript, Ruff và production Chat/Web builds đạt. Test mới
kiểm user không tự bật provider, config dev áp dụng cho hội thoại cũ, tắt dev
chặn cả cache/provider và embedding có công tắc riêng. Impeccable detector không
có findings. Browser thật đã gửi tin nhắn từ hội thoại có historical consent=false,
nhận OpenAI response VERIFIED theo cấu hình dev. UI không có hai controls đã bỏ,
options vẫn dùng bàn phím được, 1440px/390px không tràn ngang. Browser harness đã
được sửa phần URL polling và locator khi các câu trả lời giống nhau.

Test config dev tắt chạy thật đạt 1/1, 0 provider calls và portfolio hash không
đổi. Đã bật lại CHAT_LLM_ENABLED=1, CHAT_QUERY_EMBEDDINGS_ENABLED=0. Sau restart
Chat API/worker/Web, 12 receipt cũ +2 receipt hồi quy cũ +receipt dev-disabled và
receipt browser mới đều khớp nội dung/usage. Browser receipt dùng cùng thuật toán
Node JSON.stringify khi kiểm hash để giữ đúng biểu diễn số thập phân.
Đợt browser phát sinh 8 calls trong approval hồi quy đã cấp trước đó. Tổng cộng
hai approval vẫn nằm trong trần 0,50 USD. Không chạy lại full paid/hybrid eval.

Demo vẫn ở 127.0.0.1:3100. File ignored managed-web-port.yaml ghim APP_ORIGIN và
port để tránh dùng origin localhost:3000 mặc định khi recreate. Cấu hình và cách
chạy nằm ở đầu KNOWLEDGE_RAG.md. Bộ eval contextual v2 thể hiện cấu hình dev,
giữ fixture v1 và các receipt trước đó nguyên vẹn. Chưa commit/push/Google Sheet.

## Hội thoại theo ngữ cảnh OpenAI — 18/11/2026

API key cũ vẫn còn trong file ignored có quyền 600. Demo portfolio-auth-demo
trước đó chỉ chạy Compose nền nên worker chưa nạp key/provider. Đã bật lại
kết nối bằng overlay Chat LLM cũ, thêm CHAT_CONTEXTUAL_REPLIES=1 và budget mới
tổng 0,50 USD theo phê duyệt người dùng.

Prompt chat-dialogue-v3 nhận diện cách nói tạo đề xuất và câu trả lời nối tiếp.
Prompt chat-response-v3 sinh lời dẫn và câu hỏi bổ sung sau khi backend xác định
state thật. Schema giới hạn 600 ký tự, transport giữ tối đa 384 output tokens,
response có deadline 5 giây và giữ tổng budget thời gian của turn. Số liệu tiếp
tục render từ facts card, kiến thức từ excerpts/citations đã ghim. Response có
reservation riêng theo job/purpose, dùng chung budget group với intent/explanation.
Không có migration hay thay đổi public request schema.

| Gate | Kết quả |
| --- | --- |
| Offline | 125 Chat/Knowledge tests passed, 4 opt-in storage probes skipped. 10 fixtures tiếng Việt với injected adapter đạt. Ruff, format và diff check đạt. |
| Provider thật lượt đầu | 10/12 turns đạt, 18 calls. D01 bỏ qua response do time budget, D07 trả fallback an toàn vì output chứa thông tin bị validator chặn. Giữ nguyên report lần đầu. |
| Hồi quy provider trên bản sửa | D01 và D07 đạt 2/2, thêm 3 calls. Không chạy lại toàn bộ 10 cases trên bản cuối. |
| Persistence | Sau restart Chat API/worker, đúng 12 receipts ban đầu và 2 receipts hồi quy đều khớp message/usage. Portfolio hash trước/sau khớp. |
| Browser | Đăng nhập UI bằng tài khoản kiểm thử và mở lại đúng hai hội thoại hồi quy sau restart. Câu trả lời đã lưu hiển thị đúng. Không gửi lượt chat mới qua browser. |
| Usage thực | Tổng 21 calls, 8.410 input +745 output tokens, ước tính bảo thủ 0,001423750 USD. 0 uncertain reservations. Tổng reserved 0,0357 USD. Đây không phải hóa đơn. |

Daily cap được đặt 40 để chạy thêm hồi quy cùng ngày. Mỗi approval vẫn có cap
20 textual calls và ngân sách bền vững. Hai approval của đợt này có tổng upper
reservation cho textual calls 0,068 USD, nằm trong trần 0,50 USD. Demo đang dùng
approval hồi quy và file ignored .generated/chat-contextual.env. Các hội thoại
eval đã tắt consent sau khi xong. File source của worker khớp checkout.

Free prose ở đây giới hạn lời dẫn/hỏi thêm, chưa tổng hợp nhận định tài chính tự
do. Validator ký tự/PII/URL/số và prompt không chứng minh đúng ngữ nghĩa của mọi
câu tự nhiên. Bộ contextual cases là regression/dev, không phải held-out mới.
Full release eval/human review và numerical research parity không được chứng
nhận bởi gate này. Chi tiết và lệnh chạy trong KNOWLEDGE_RAG.md và CHAT_LLM_PLAN.md.

## Knowledge/RAG lexical MVP — 07/11/2026

Đã hiện thực Knowledge owner API/DB/leased worker, PostgreSQL 17.11 + pgvector 0.8.1
ở cluster/volume mới, 12 ghi chú PUBLIC / 24 claims, manifest/CLI/lifecycle, scoped
lexical + exact-cosine adapter, Chat tool chỉ đọc, retrieval checkpoint, immutable
evidence hash, consent v1/v2 và provider reservations/caps. Không đổi core,
quantitative facts/hash, confirmation/accept semantics hoặc tự allocation từ câu hỏi
kiến thức. API port 8006; migrations Knowledge `k10000000001..04`, Chat
`c10000000003`. [Runbook/API/commands](KNOWLEDGE_RAG.md).

**Chưa nghiệm thu release RAG.** Giữ corpus/eval đã đóng băng; không sửa expected
cases hoặc hạ ngưỡng để pass. Semantic/provider gate chưa chạy do chưa có budget
mới. Offline intent và lexical held-out hiện dưới ngưỡng.

| Layer | Kết quả thực trong đợt này |
| --- | --- |
| K0 baseline | HEAD `67540341a7819cfc4cc8ea4b202a325bafd0b583`; ban đầu không có tracked diff. 537 Python +4 skips, 134 web; Chat API, bốn Chat browser journeys, P0 expired-input/re-auth và ba PostgreSQL concurrency probes đạt. Provider được tắt trước browser. |
| Offline cuối | **571 Python/core passed, 1 skipped** (Market concurrency URL chưa cấu hình); ba Chat PostgreSQL probes và một Knowledge PostgreSQL probe chạy thật. **138 web tests**, TypeScript, Ruff và production images Chat/Knowledge/Web đạt. 12 contracts export ổn định; migration/metadata PostgreSQL và Compose config đạt. |
| Storage/auth/lifecycle | Indexing/dedupe/alias-key conflict, READY activation, atomic swap/deactivate/rollback, stale precondition và cited history bất biến chạy thật. DB runtime DML/denied DDL/owner/cross-DB, broker ACLs, machine audiences/scopes và Knowledge immutable-row checks đạt. Synthetic vectors trong isolated PostgreSQL schema kiểm exact cosine 1536, model/threshold/PUBLIC/cutoff/draft/no-match và concurrent pointer swap; đây **không** là real-provider hybrid evidence. |
| Chat/authorization | Real Keycloak/Portfolio/Quant/Knowledge: knowledge không cần portfolio, consent v1/v2/off, missing evidence, canonical facts equality, cross-owner history/SSE đạt. 47 delegation probes /305.53s, gồm hết hạn thật sau 5 phút và account restore, đạt. Knowledge outage vẫn trả canonical facts đúng + thiếu nguồn. |
| Browser/UI | Figma đúng file/project, đọc V2.5 qua figma-mcp-go sau official MCP quota; giữ controls/layout/tokens. PKCE, nguồn bằng bàn phím, consent renewal/revoke, 390px/desktop, no-source/reload và canonical source + explicit accept đạt. Đã sửa focus sau renewal bằng browser regression. Impeccable detector 0 findings; rendered muted-text contrast 5.66:1. Không chứng nhận full screen reader/thiết bị thật. |
| Persistence | Sau restart thật Chat API/worker, Knowledge API/worker, Web: cùng Knowledge, Chat-Knowledge, outage-canonical và browser source/target receipts khớp IDs/corpus/chunks/evidence/facts/history; invocation không tăng. Original Chat browser và Market browser receipts đạt; P0 API receipt đạt. Runtime Python source hash khớp images (Chat14 files, Knowledge10); hai workers không có provider key/budget mới. |
| Strict API receipt incident | Initial Knowledge browser case đã accept proposal của API fixture, tăng portfolio summary version1→2. Strict original Chat API receipt **fail summary hash**; không ghi đè hoặc nới checker. Diagnostic đọc thật xác nhận original facts/input/history/conversation vẫn khớp. Harness đã sửa: tạo/accept portfolio riêng và assert API fixture không đổi; case mới đạt, receipt riêng. Đây không biến failure cũ thành pass. |
| Historical regressions | Market–Quant receipt dừng ở parity load vì prepared input cũ expired. P1 browser receipt fail current BL_ML availability tại dòng281, sau khi model/manifest/snapshot pins khớp. Không sửa expiry/data hoặc chạy luồng mới để thay bằng chứng; full historical gates này chưa đạt trong đợt này. |
| Eval v1 | 60 cases:20 dev/40 held-out,24 answerable +24 safety/abstention +12 canonical/multi-turn; SHA256 `bbd12e32e888737bcc23c51261a92675d2ac16d2706ce573853ae0356802f4f3`. Intent dev18/20, held-out30/40 (**75%**, yêu cầu90%). Lexical Hit@5 dev8/8, held-out12/16 (**75%**, yêu cầu90%). Lexical abstention áp dụng dev2/2 +held-out2/2; không suy thành toàn bộ safety eval. Full 60-case live conversation eval và human support/relevance review: **not run**. |
| Performance/usage | 28 real lexical API samples: retrieval server p50 **6.887ms**, p95 **12.685ms**; HTTP p50 28.116ms/p95 47.292ms. Không tính đó là load/SLO certification. Ingestion/query/dialogue calls **0/0/0**, actual tokens0, new uncertain reservations0, estimated spend$0. Paid/hybrid latency/quality/cost: **not run**. |
| Review | Review độc lập tìm 7 Important findings, không Critical; sửa với RED→GREEN và full green suites: routing/billing, redacted question, stable CLI availability, alias keys, DB snapshot, strict paid assessments và checkpointed paid resume. Bổ sung turn-budget fallback và fixture-isolation regression. Không commit/push/merge/Google Sheet; giữ concurrent sticky-shell CSS riêng. |

Lệnh chính đã chạy: `CHAT_POSTGRES_TEST=1 KNOWLEDGE_POSTGRES_TEST=1 .venv-software/bin/python -m pytest tests/software packages/portfolio-core/tests -q`, `npm --prefix apps/web test`, `npm --prefix apps/web run typecheck`, Compose build/config, Alembic check, `smoke_knowledge.py`, `smoke_chat_knowledge.py`, `smoke_knowledge_lifecycle.py`, `smoke_chat_authorization.py`, real boundary probes, `eval_knowledge.py --mode offline/lexical`, browser Knowledge/Chat/Market/P1 persistence. Chi tiết command/result được giữ trong ignored `output/knowledge-rag/`; receipts giữ trong ignored `.generated`, không vào Git.

Paid preparation có dry-run mặc định0, trần đề xuất1USD **chưa được cấp**; reservation
bounds tối đa100 embeddings +20 dialogue (~$0.050 upper bound với giá đã đối chiếu),
partition20/20/60%. Chỉ workers được nhận key qua overlay opt-in. Replay giữ stable
keys/jobs, uncertain outcome không tự gọi trả phí lại; representative gate kiểm
usage thật/fully embedded corpus/intent/claims/abstention, không chỉ nhãn HYBRID.
Không thay Auto Recharge. Xem runbook để cấp cấu hình sau khi có budget cụ thể.

Đề nghị checklist để người dùng duyệt riêng, **chưa cập nhật Google Sheet**:

| Mục | Trạng thái đề nghị / giới hạn |
| --- | --- |
| KN-01 | Local owner-service/API/DB/worker: đạt phạm vi MVP; không production certification. |
| KN-02 | **Partial**: manifest + curated Markdown đạt; PDF/URL/OCR/malware pipeline chưa làm. |
| KN-03/04/05 | **Partial**: pinned pgvector/scoped lexical/storage + citations/Chat integration đạt local; semantic provider/full eval chưa đạt. |
| KN-06 | **Partial**: lifecycle MVP swap/deactivate/rollback/audit; không full legal deletion/retention. |
| CHAT-04/05/13 | **Partial**: read-only tool, controlled claims, evidence/consent/quota và local safety gates; paid/full conversation eval còn mở. |
| FE-22 | Source/consent UI local đạt; giữ giới hạn browser QA, chưa full accessibility certification. |
| DB-07 | Owner cluster/migrations/runtime grants local đạt; không đổi existing PostgreSQL volume/image. |
| E2E-08 | **Partial / chưa release**: local lexical/browser receipts đạt theo phạm vi trên; paid, full eval/human review và các historical failures còn mở. |

### Cập nhật truy xuất tiếng Việt — 09/11/2026

`knowledge-retrieval-v2` thử cụm thuật ngữ trong corpus khi truy vấn đầy đủ
không có kết quả. Chat chấp nhận cả v1 và v2. Giữ nguyên Markdown, corpus đang
active, PostgreSQL + pgvector và bộ eval v1. Không cần migration hay reindex.

| Eval cùng bộ dữ liệu | v1 | v2 |
| --- | --- | --- |
| Lexical Hit@5 dev | 8/8 | 8/8 |
| Lexical Hit@5 held-out | 12/16 (75%) | **14/16 (87,5%)**, dưới ngưỡng 90% |
| Lexical abstention áp dụng dev / held-out | 2/2 và 2/2 | 2/2 và 2/2 |
| Offline intent dev / held-out | 18/20 và 30/40 | 18/20 và 30/40 |

A22 và A23 tìm được nguồn được chấp nhận. A21 chỉ tìm được định nghĩa EW,
chưa hỗ trợ câu hỏi về bảo đảm lợi nhuận. A24 vẫn thiếu nguồn phù hợp. Đây là
eval lexical trên Knowledge API thật, 28 lượt truy xuất mỗi bản. Server p50/p95
từ 3,53/5,84 ms lên 5,37/11,77 ms trong hai lần đo local. Báo cáo trước/sau nằm
trong thư mục ignored `output/knowledge-rag/`. Full live conversation eval,
human support review, browser và paid hybrid không chạy lại trong đợt này.

Python/core 572 passed, 1 skipped (Market concurrency). Sau khi restart Chat
và Knowledge API/worker, receipt Chat v1 gốc và receipt diễn đạt lại v2 đều khớp.
Hai file receipt gốc giữ nguyên checksum. Hash response của Knowledge API v1
bao gồm `retrieval_version`. Đối chiếu cùng query/corpus/cutoff sau nâng cấp xác
nhận payload chỉ khác trường phiên bản. Ledger không có reservation mới cho
ingestion, query embedding hoặc dialogue trong đợt đo.

### Thử nghiệm query rewriting tiếng Việt — 09/11/2026

Chat có điểm nối adapter nội bộ, tắt ở worker mặc định. Adapter thử một truy vấn
lexical sau khi lượt kiến thức không có kết quả. Với câu nối tiếp, ngữ cảnh chỉ
gồm một chủ đề từ trích dẫn trong câu trả lời kiến thức liền trước của cùng hội
thoại. Giữ scope/corpus/cutoff và chỉ lưu hash của truy vấn viết lại thành công.

Eval `eval-vi-rewrite-v1` chạy hai nhánh trên Chat/Knowledge API thật với cùng
corpus và 10 ca mới. Hit@5 và tỷ lệ có ít nhất một trích dẫn đúng trong tin nhắn
đều tăng từ **2/7 lên 7/7**. Ba ca cần abstain đều đạt ở cả hai nhánh. Adapter
được gọi 6 lần, trong đó 5 lần tìm được nguồn và 1 câu ngoài corpus vẫn thiếu
nguồn. Các truy vấn viết lại do fixture cung cấp. Đây là phép đo đường truy xuất
và xuất bản trích dẫn. Chất lượng model local, paid hybrid và browser không chạy.
Bộ eval 60 ca trước vẫn giữ nguyên. Python/core **578 passed, 1 skipped**.
Sau restart Chat API/worker, cả 20 receipt eval và receipt Chat Knowledge cũ
đều khớp. Runner chỉ dừng và khởi động lại đúng container Chat worker.


## Chat LLM phương án B — 05/11/2026

Đã nối OpenAI Responses thật với `gpt-6-luna`, reasoning none, strict schemas,
context ngắn và consent theo conversation (mặc định tắt). LLM chỉ trả intent/
strategy/reference và fact plan; backend giữ quyền tools, canonical facts,
confirmation và explicit accept UI. Không phát prose tài chính chưa kiểm chứng.
Worker có quota ngày UTC, invocation ledger/fencing/dedupe, actual usage và
fallback; provider key chỉ ở worker qua overlay opt-in, không đổi Auto Recharge.

Live browser đã đi qua PKCE → bật consent → thiếu strategy/hỏi lại → MVO follow-up
→ confirmation → Portfolio/RabbitMQ/Quant thật → giải thích → hỏi tiếp đúng cùng
recommendation → tắt consent → explicit accept UI. Tổng **5 OpenAI calls**, actual
usage **1786 input + 196 output tokens**; ước tính bảo thủ **$0.00032125**, không
phải số tiền hóa đơn. Không HTTP interception hay tạo giả SQL results. Market
được refresh KBS đến 04/11/2026, schedule tắt; không dùng dữ liệu hết hạn/DEMO.

Gate đầu dừng ở phép cộng usage sau khi đã accept: message của lượt hỏi tiếp
chỉ mang explanation metadata, thiếu interpretation usage trong phép cộng.
Đã sửa bằng owner-scoped `provider_usage` trên job API và regression RED→GREEN.
Để tiết kiệm, đối chiếu lại chính jobs/requests/ledger đã lưu bằng đọc SQL và
canonical HTTP, không sửa business rows hoặc gọi model lần nữa. Browser receipt
verification sau restart Chat API/worker/Web đạt; replay giữ cùng IDs/hashes/
history và ledger vẫn 5 calls. Gate cap thật ở mức đã dùng 5 trả TEMPLATE với
DAILY_BUDGET_EXHAUSTED, canonical facts giữ nguyên và không thêm invocation.
Fault injection HTTPS proxy loopback từ chối kết nối cũng trả
TEMPLATE trước khi tới OpenAI: ledger hiện 6 reservations, chỉ 5 có paid usage.
Proxy đã được gỡ; worker trở lại quota 20/ngày.

Offline: 539 Python/core + 1 skip ngoài phạm vi, 104 web tests, TypeScript,
Ruff, 11 contracts và production builds đạt tại mốc kiểm tra. Đã bổ sung thêm
PostgreSQL storage probe cho quota LLM đồng thời (callbacks injected, không gọi
provider); ba Chat PostgreSQL concurrency probes đạt. Read-only review tìm lỗi
cách viết “BL + ML”; đã sửa với regression test. Explanation planner nhận câu hỏi đã redaction để chọn
sections đúng trọng tâm. Bổ sung owner grant/account
preflight trước interpretation, nên revoke/disable chặn cả lượt gửi context ra LLM.
Xem
[setup/giới hạn credits](SETUP_AND_API_TESTING.md#openai-dialogue--phương-án-b-05112026).

Giới hạn: chưa đánh giá rộng chất lượng hội thoại tiếng Việt/full RAG; explanation
vẫn là finite fact plan do backend render; model alias chưa có dated snapshot;
redaction không bảo đảm loại mọi PII tự do; số tiền chỉ ước tính. Full paid lifecycle
không chạy lại sau sửa phép cộng usage; kiểm chứng lại trên chính receipt cũ để
không tốn thêm credits. Không tuyên bố production/HA hoặc GitHub CI đã chạy.

## Chat MVP — kiểm chứng local 04/11/2026

Đã hiện thực vertical slice Chat trên API thật, kiểm thử backend trước frontend:

- `chat_db`, migration/API riêng (Swagger port 8005), leased SQL worker, conversations,
  messages, jobs, event sequence và tool audit. HTTP 202 trả resource references;
  client_message_id/key/body conflict, quota theo owner, retry/deadline, fencing
  và dependency checkpoint chống duplicate khi restart.
- Portfolio cấp/kiểm tra delegation 5 phút, binding user/service/conversation/job/
  resource/tool, expiry/revoke và account/role hiện hành qua Identity. Chỉ lượt
  structured-confirmed được cấp request_allocation; không có accept/trade/promote
  trong tools. Market cung cấp observations/source/timestamps từ database owner.
- Canonical recommendation/facts/versions được refetch; provider schema chỉ chọn
  fact-template sections. Deadline tổng 5 giây, body budgets, durable one-call/job;
  unconfigured/outage/unverified output dùng template, giữ nguyên quantitative
  result. Template v2 dùng câu tiếng Việt, hashes trong phần đối chiếu.
- BFF relay SSE có Last-Event-ID/header isolation, session expiry, backpressure;
  events bền vững 7 ngày và reset khi quá retention. Browser có list/history paging,
  review cards, job progress, canonical cards, explicit retry/reauthorize, deep
  links/reload và mở proposal để accept rõ ràng bằng UI hiện có.

Bằng chứng cuối: **508 Python/core tests passed, 1 skipped** (opt-in có sẵn ngoài
Chat); hai storage concurrency tests Chat chạy trên PostgreSQL thật. **102 web
tests**, TypeScript, Ruff, production Docker build và 11 contracts đạt. DB/broker/
Identity boundaries và PostgreSQL migration/metadata check đạt. Read-only review
phát hiện các race/recovery/budget/SSE defects; đã sửa và có regression tests.

Real API gate normal/outage/restart đạt trên Keycloak, PostgreSQL, RabbitMQ,
Portfolio/Quant thực; snapshot KBS FPT/MWG/VCB đến 03/11/2026, không HTTP interception
hoặc tạo giả SQL results. Gate authorization riêng **47 probes / 305.34s** đạt,
bao gồm hết hạn thực sau 5 phút, revoke, account disable/restore, sai binding/tool,
stale portfolio/risk và rejected expired real inputs. Bob đã được khôi phục;
không tự accept từ API harness.

Browser thật đạt 4 cases thường (PKCE→conversation→confirmation→allocation→verified
facts/template→accept UI; expiry/explicit retry; hai races), 1 case provider outage,
và 2 receipt cases sau restart. Có nhận accepted SSE event trong browser khi worker
đang dừng, lưu cursor, offline và tiếp tục cùng job sau restart. Race tests chỉ
làm chậm network response thật qua Chromium, không thay response. Desktop/390px
đã kiểm tra và xem screenshot; Figma F01/F02/F03 trong đúng project 24.10.2026 và
ui-ux-pro-max; giữ shell/tokens/assets/AllocationView hiện có.

Receipts không token ở `infra/local/.generated/chat-*-receipt.json`; báo cáo/ảnh
ở `output/playwright/sanitized/chat-*.json/png`, không vào Git. Sau restart 9 tiến
trình Chat/Web/Portfolio/Quant, IDs, input/facts/target hashes và lịch sử khớp.
Đã scan logs: không có configured secrets, bearer strings hoặc grant references;
installed Chat/Portfolio source hashes khớp workspace. Worker outage đã trở lại
cấu hình bình thường. Xem [API/worker](SETUP_AND_API_TESTING.md#chat-mvp-api-và-worker)
và [browser gate](../../apps/web/tests/browser/README.md#chat-mvp-real-stack-gates).

Trong triển khai, disk-full làm Docker treo. Theo yêu cầu người dùng, đã dọn
**13.61GB build cache +1.758GB dangling images**; giữ containers/volumes/secrets/
data, phục hồi Docker và kiểm chứng lại. Lịch KBS thử nghiệm đang tắt. Giữ nguyên
`extensions_C_v1/`, nghiên cứu/core và dữ liệu cũ. Chưa commit/push.
Sau build cuối, dọn thêm 3.325 GB build cache + 699.5 MB dangling images;
11 volumes giữ nguyên, ổ đĩa còn 8.9 GiB. Health và cả hai API receipts vẫn đạt.

Giới hạn: intent/tool allowlist deterministic; hosted provider dùng protocol
`fact-plan-v1`, chưa cấu hình provider thương mại/SDK riêng. Chưa có full RAG/
Knowledge, Chat AMQP continuation consumer (worker reconcile bằng owner API),
production HA/load/SLO certification; GitHub CI chưa chạy bản này. Market calendar
vẫn là observed VNINDEX sessions, không coi ingestion availability là historical
point-in-time proof. Đây là local MVP, không chứng nhận nghiên cứu/production.

## P1 — kiểm chứng local 27/10/2026

Đã bổ sung ba luồng và UI nối API thật:

- Data Refresh: schedule/job bền vững, chạy tay hoặc timer, KBS stock adapter cố
  định và raw/normalized SHA-256, kiểm tra toàn lô trước snapshot. Mỗi lần fetch
  đối chiếu toàn bộ khoảng lịch sử adjusted đã cấu hình; chỉ revision mới/thay
  đổi được thêm vào storage. Không ghép các adjustment vintage bằng fetch riêng
  cửa sổ overlap. Calendar là phiên VNINDEX quan sát được, chưa được xác nhận độc
  lập; ingestion availability không chứng minh historical point-in-time data.
- ML Operations MVP: `ml_db`, migrator/API/worker riêng (Swagger port 8004),
  snapshot/hash-pinned training được kích hoạt thủ công, candidate và review
  APPROVED/REJECTED có reason/If-Match/idempotency. HTTP chỉ enqueue; worker không
  tự duyệt. Publication nhận `approved_model_id`, resolve manifest tin cậy ở server
  và chờ artifact đã materialize. ML tạm dùng lại Quant training/feature helpers;
  chưa hoàn tất việc tách thư viện dùng chung, không thay core/risk mapping.
- Risk reassessment: preview thuần đọc, confirmation có If-Match/key, revision UUID
  bất biến và lịch sử phân trang. Profile mới tăng version danh mục; proposal cũ
  không được accept. Target đã chấp nhận giữ allocation/policy cũ; queued input/hash
  legacy không bị sửa và lịch sử chưa biết không bị bịa/backfill.

BFF giữ session/CSRF và allowlist upstream theo Portfolio/Market/Quant/ML;
operator/reviewer/investor có role gates riêng. Chỉ refresh/ML/publication workers
được ghi artifact thuộc owner; các API và optimizer đọc read-only. Local upgrade
bổ sung DB/scopes/clients/migrations, giữ secrets và volumes hiện có.

Đã thêm gate P1 nguồn thật và receipt sau restart, gồm manual refresh + actual
scheduler tick, training/reviewer/publication và risk → BL_ML → accepted target.
**Kiểm chứng mới: 451 Python/core tests, 84 web tests**, Ruff, TypeScript,
production build và 10 contracts ổn định. Một PostgreSQL concurrency test opt-in
skip trong gate mặc định; probe fencing trên PostgreSQL thật và DB/broker/Identity
boundaries chạy riêng đạt. Sáu browser gates đạt: P1, P0 và Market lifecycle cùng
đối chiếu chính receipt sau restart. P1 dùng KBS FPT/MWG/VCB đến 26/10/2026;
không mock HTTP hoặc tạo giả kết quả SQL. Đã restart 14 tiến trình ứng dụng, giữ
nguyên model/snapshot/input hash, quyết định review, risk UUID và cả allocation
cũ/mới. Lịch tự động thử nghiệm đã tắt, replay không bật lại hoặc tạo thêm job.

Model UI hiển thị model được chọn theo từng universe từ Quant readiness, checksum
và tương thích BL_ML; trạng thái hết hạn tự cập nhật trên trang đang mở. UI dùng
ui-ux-pro-max và các khung Figma I01/I02/I07–I10/I34/I35; hồ sơ rủi ro tái sử dụng
wizard/review hiện có. Kiểm tra desktop và 390px đạt; không coi các trạng thái
prototype VALIDATED/PRODUCTION là lifecycle đã hiện thực trong MVP. GitHub CI
chưa chạy trên bản thay đổi này. Báo cáo đã lọc ở
`output/playwright/sanitized/p1-lifecycle.json` và `p1-persistence.json`, receipt
không token ở `infra/local/.generated/p1-browser-receipt.json`.
Xem [cách chạy](../../apps/web/tests/browser/README.md#p1-real-provider-model-and-risk-gate)
và [setup/API](SETUP_AND_API_TESTING.md). Chưa tuyên bố CI GitHub, production
certification hoặc đầy đủ mọi lifecycle/screen tương lai trong Figma.

Các mục bên dưới giữ nguyên bằng chứng và giới hạn tại từng mốc lịch sử.

## Market Data Operations — cập nhật 27/10/2026

Đã bổ sung registry SQL bất biến từ trusted CSV inventory, đăng ký có
Idempotency-Key, lịch sử ingestion phân trang và báo cáo chất lượng
PASS/QUARANTINED/NOT_CHECKED. Lô dữ liệu được kiểm tra trước khi ghi giá;
snapshot ghim revision/hash và kiểm tra chất lượng các revision được chọn.

Data operator có thể enqueue/list/get publication của mình với snapshot ID/hash
và universe cố định. API chỉ ghi SQL queue; worker riêng phát hành bundle và retry
lỗi tạm thời. Frontend `/#market` nối đầy đủ nguồn → ingestion → chất lượng →
snapshot → phát hành, với role gate, CSRF, phân trang và deep links.

Kiểm chứng: **385 Python/core tests / 64 web tests**, Ruff, TypeScript,
production build, 9 contracts và DB/broker/Identity boundaries. Một PostgreSQL
concurrency test opt-in được chạy riêng và đạt; gate mặc định skip test này.
Năm browser gates trên backend thật đạt: Market lifecycle, outage/retry,
Market restart persistence, P0 lifecycle và P0 restart persistence. Luồng giá thật
FPT/HPG/VCB đi đến accepted target; retry giữ đúng job/hash và lịch sử giữ nguyên
sau restart. CI GitHub chưa chạy.

Giới hạn: trusted CSV/import; lịch phiên chỉ kiểm đủ khi nguồn có
`expected_sessions`. Metadata thiếu basis/known-at có cảnh báo, chưa được coi là
đã xác minh. UI bám Figma I01; I02–I06 chưa đối chiếu chi tiết do hạn mức đọc MCP.
Xem [hướng dẫn UI](../../apps/web/README.md) và [vận hành local](../../infra/local/README.md).

## P0 — cập nhật 25/10/2026

Đã bổ sung readiness dữ liệu/model có mã nguyên nhân và thời hạn; publication
jobs bền vững với lease fencing, retry/idempotency, recovery và lịch cấu hình.
Worker dùng Quant DB và Market snapshot-reader; Quant API/optimizer giữ artifact
mount read-only. Lịch mặc định tắt; không tự crawl, train hoặc duyệt model.

UI theo design hiện có hỗ trợ sửa tên/vốn có If-Match/conflict recovery, tìm/lọc/
sắp xếp/phân trang từ server, lịch sử target, so sánh proposal và deep link/reload.
Phiên hết hạn chỉ lưu đích điều hướng, không tự gửi lại mutation.

Kiểm chứng: **336 Python/core tests / 60 web tests**, Ruff, typecheck, build và
contracts đạt. Browser thật đã qua PKCE → onboarding → EW/target → history → sửa
đồng thời/412 → MVO/compare → expiry → 401/đăng nhập lại; sau restart giữ cùng
target/proposal/allocation hash. Job publish từ snapshot Market giá thật và model
được duyệt đã SUCCEEDED, retry cùng key và đọc lại sau restart giữ cùng kết quả.
Workflow đã nối browser lifecycle/persistence với Playwright pin và artifacts
đã lọc; chưa chạy workflow này trên GitHub. Xem [browser gate](../../apps/web/tests/browser/README.md)
và [publication worker](../../infra/local/README.md#durable-operator-publication).

## UI — cập nhật 25/10/2026

UI trên cổng 3000 hỗ trợ onboarding có review, universe thật/minh họa, danh sách
danh mục, biểu đồ/bảng phân bổ, accepted target và dashboard. Luồng browser thật
đã kiểm chứng OIDC/PKCE → tạo danh mục → MVO → lưu target → reload/restart.
Kiểm tra offline: **248 Python tests / 52 web tests**, lint, typecheck và build.
Giữ các smoke scripts để chạy lại; ảnh chụp và receipts local không lưu trong Git.

## Market → Quant — cập nhật 24/10/2026

Đã nối snapshot giá thật FPT/VCB/HPG đến features, numerical bundle, approved
XGBoost, BL_ML và accepted target trên stack local. Dữ liệu đến **23/10/2026**;
serving/core cùng bước sai số weights < `1e-10`. UI chọn universe từ catalog và
phân biệt real/demo. **248 Python / 51 web tests** cùng lint/typecheck/build,
contracts/migrations, live boundary probes, restart receipts và browser thật đạt.
[Chi tiết, cách chạy và giới hạn](MARKET_QUANT_BRIDGE.md).

Các cập nhật 23/10 bên dưới là lịch sử trước khi nối bridge.


## Tuần 6–7 — cập nhật 23/10/2026

G2 local đã kiểm chứng qua browser thật: OIDC → wizard → portfolio/policy →
MVO proposal → accept target → dashboard. Native XGBoost approved manifest → BL_ML
qua RabbitMQ đã đạt same-step parity, max |Δweight| = 0 trên synthetic inputs.
MVO/Market/target/ML receipts giữ nguyên sau restart. **219 Python tests / 49 web
tests**, typecheck/build/lint/contracts/migrations và live boundary probes đạt.

Hợp đồng và cách dùng: [WEEKS_6_7.md](WEEKS_6_7.md).
Chưa hoàn tất full ML Platform, Market→features, representative selection, ledger,
Chat/RAG hoặc nghiên cứu selection/ablation. Các mốc bên dưới là lịch sử.

## OpenTelemetry + Jaeger — kiểm chứng local ngày 10/10/2026

Distributed tracing đã bật bằng `compose.tracing.yaml`, có manual spans cho
BFF/API, outbox dispatch, RabbitMQ publish/consume, numerical allocation và
lưu kết quả. Context nullable được lưu cùng Job/Run/Outbox transaction; không
thay Envelope, input hash hoặc core `0.1.0`. Polling có trace riêng và link tới
trace submission. UI hiện link **Xem trace trong Jaeger** cho job/kết quả mới.

| Kiểm tra | Bằng chứng mới |
| --- | --- |
| Offline Python/API/core | **188 passed**, 1 warning Starlette/AnyIO có sẵn; scoped Ruff đạt. Migrations additive/legacy null, retry/restart, hash/idempotency và privacy được kiểm tra. |
| Web/BFF | **44 passed**, không skip; typecheck và production Docker build đạt. Filter bỏ Next/auth spans trước batch; exporter treo/lỗi không làm hỏng business response. |
| Contracts/config/setup | Export 9 contracts lặp giữ hash; base + tracing overlay hợp lệ; `prepare --tracing --enable-test-client`, `check --tracing` và `up --tracing --skip-install --skip-build` đạt. |
| Real migrations/persistence | Ba owner migrations exit 0; old schema-2 receipt đọc lại đúng recommendation, Market job/snapshot, hash/history/ownership sau cập nhật. DB/broker/identity boundaries đạt. |
| Tracing flow + fault probes | `scripts/smoke_tracing.py --restart-dispatcher --collector-outage` đạt: business MVO + Market/snapshot chạy khi Jaeger dừng; job QUEUED được dispatch sau restart vẫn giữ origin trace; fresh BFF code/PKCE/CSRF flow và Market ingestion xuất đầy đủ spans. |
| Jaeger/UI | Recommendation **17 spans / 7 process names**, Market **7 spans / 3 process names**. Trình duyệt thật đăng nhập alice, mở persisted result và thấy link đúng trace. Jaeger timeline xác nhận `portfolio_core.allocate` và đường kết quả về Portfolio. |
| Logs/privacy/review | Origin recommendation khớp **10 JSON log records / 6 processes**; không có generated credentials trong logs và không có tested private values/unsafe attributes trong trace. Hai lượt review độc lập; findings đã sửa và regression tests đạt. |

Trace recommendation tại thời điểm kiểm chứng:
[6829e4532520eb66e029b75af708f464](http://localhost:16686/trace/6829e4532520eb66e029b75af708f464).
Market:
[337dd2cb4a49c2c6d6cb23aa2613ae17](http://localhost:16686/trace/337dd2cb4a49c2c6d6cb23aa2613ae17).
Receipt không token: `infra/local/.generated/tracing-receipt.json`.
[Ảnh timeline](assets/tracing-recommendation-2026-10-10.jpg).

Mạng tải pip trong Docker chỉ khoảng 20 kB/s trong lần build đầu; build đó được
dừng, rồi ba backend images được build từ **source hiện tại và Linux wheels tải
từ PyPI trên host**, đúng runtime constraints. Dockerfile tạm chỉ thay cách lấy
dependency bằng `--no-index --find-links`/`--no-build-isolation`; `pip check` trong
images đạt. SDK source SHA-256 trong container khớp source checkout. Cấu hình
Docker credentials tạm được dùng; config toàn cục, generated secrets và volumes
được giữ nguyên. Temporary wheelhouse đã xóa; không prune/reset.

Jaeger dùng RAM; restart collector mất trace history, application data vẫn còn.
Các job trước tracing có null fields, không tái dựng được timings cũ. Đây là
observability local; chưa có centralized log storage/Loki, retention backend,
metrics/alerts hay staging tracing deployment. `npm audit` còn 3 high findings
trên Next/sharp/source-map-js hiện hữu; không thuộc dependencies OTel vừa thêm.
GitHub workflow mới chưa chạy trên GitHub. Xem [hướng dẫn tracing](TRACING.md).

Các mục bên dưới lưu lịch sử của những lần triển khai/kiểm chứng trước.

## Lần chạy lại 10/10/2026 — stack local đã hoạt động

Dung lượng host đã tăng lên khoảng 14 GiB trước chạy, còn khoảng 12 GiB sau
build. Docker server 27.5.1 đã phản hồi. Đã khắc phục các lỗi runtime và chạy
thành công stack hiện hành, giữ nguyên generated credentials và named volumes.

| Kiểm tra mới | Kết quả |
| --- | --- |
| Startup/migrations | **passed**: Keycloak và ba backend migration exit 0; web/APIs/infrastructure healthy. `setup_software.py up --enable-test-client --skip-install --skip-build` exit 0 với images mới đã build. |
| DB/broker/identity boundaries | **passed**: PostgreSQL owner/runtime DML, denied DDL/role escalation/cross-DB; quorum/DLQ và publisher/consumer ACLs; web password grant bị từ chối và test-client Market claims hợp lệ. |
| Real API workflow | **passed**: JWT thật, async MVO qua broker, idempotency, ownership, provenance/history, missing-model rejection; Market ingestion và snapshot thật. |
| Persistence | **passed**: restart cả chín Portfolio/Quant/Market API/worker processes rồi đọc lại receipt cũ, IDs/hash và ownership không đổi. |
| BFF HTTP integration | **passed**: real authorization code + PKCE callback, cookie session, CSRF mutation, async polling/result và logout. HTTPX phải mô phỏng riêng việc gửi Secure cookies trên localhost; không sửa cookie policy của app. Chưa kiểm tra visual UI bằng trình duyệt thật. |
| Offline regressions/review | **passed**: **153 Python tests**, một cảnh báo Starlette/AnyIO có sẵn; software Ruff đạt. Reviewer độc lập kiểm tra các sửa auth/broker, không có important finding. |
| URLs | Web `http://localhost:3000`; Swagger Portfolio/Quant/Market `http://localhost:8001/docs`, `:8002/docs`, `:8003/docs` đều HTTP 200. |

Các lỗi phát hiện và xử lý:

1. Container `identity-migrate` cũ lỗi `java.io.EOFException` khi đọc Quarkus
   serialized application. Image chạy được trong container sạch; tạo lại riêng
   container migration đã giải quyết, database/realm hiện có được giữ nguyên.
2. JWT Keycloak thiếu `sub`, khiến Portfolio HTTP 401. Bootstrap trước đó tự
   khai báo client scopes nhưng thiếu `basic`/Subject mapper. Đã thêm scope mapper
   và attach default cho web/service/test client; upgrade sửa realm cũ theo cách
   additive, không thay users/secrets/grants. Token verifier vẫn bắt buộc `sub`.
   [Keycloak xác nhận Subject mapper thuộc basic scope](https://github.com/keycloak/keycloak/blob/main/docs/documentation/upgrading/topics/changes/changes-25_0_0.adoc).
3. Script boundary gọi sai endpoint permissions (HTTP 404); đã đổi sang
   `/api/vhosts/portfolio/permissions` theo
   [RabbitMQ HTTP API](https://www.rabbitmq.com/docs/http-api-reference).
   Đồng thời sửa `basic_qos` với đủ `prefetch_size`, `prefetch_count`, `a_global`
   theo chữ ký thư viện đang cài. Cả hai có regression RED→GREEN và live check.
4. Build web mặc định mắc ở `docker-credential-desktop`, dù anonymous registry
   probe và pinned Node manifest đạt. Đã build bằng **DOCKER_CONFIG tạm và
   DOCKER_HOST tường minh**, không sửa login config toàn cục. Images hiện đã có;
   dùng `--skip-build` chỉ khi source/image khớp. Hướng dẫn có workaround cho lần
   cần build mới nếu helper còn mắc.

Receipt local schema 2 được tạo lúc `2026-10-10T04:13:42.979100+00:00`, không
chứa token. Quant demo mới:
`demo-20261010T040659196977Z`, SHA-256
`5f3cf99abc4404b6f2c0bc0affd9f3dac7b463074fa53f958bd6a27e13edf220`.
Market artifact mới `demo-stock-20261010T040659200563Z.csv`, SHA-256
`557c1f6b01c7eb435b4048ba432e878a2c688884f5680e1558f28ff501db609d`.
Old bundles, CSVs, users và volumes giữ nguyên. Demo vẫn là dữ liệu tổng hợp,
không chứng minh live provider/trained-model parity hoặc staging deployment.

Các phần dưới lưu lịch sử chẩn đoán trước khi khắc phục; trạng thái blocked
trong chúng đã được cập nhật bằng bằng chứng của lần chạy lại bên trên.

## Chẩn đoán runtime ngày 10/10/2026

- Đã chạy `setup_software.py check` và `up --enable-test-client --skip-install`:
  cả hai dừng tại prerequisite Docker daemon sau timeout 20 giây.
- `docker context show` trả `desktop-linux`; truy vấn Docker server và Compose
  `ps -a` đều timeout 8 giây. Compose `config --quiet` vẫn hợp lệ.
- Filesystem host còn khoảng 493 MiB lúc kiểm tra, báo 100% capacity.
- Docker backend log lúc **10:42:16 ngày 10/10/2026 (Asia/Ho_Chi_Minh)** ghi
  `Failed to write to log file dockerd ... no space left on device`.
  Docker daemon đồng thời báo `input/output error` khi mở
  `/var/lib/docker/buildkit/executor/runc-log.json` và `overlay2/.../lower`.
- Đây là bằng chứng lỗi storage/hạ tầng Docker. Chưa thể kiểm tra lỗi bên trong
  application services bằng stack thật. Cần giải phóng dung lượng host trước,
  khởi động lại Docker bình thường rồi kiểm tra daemon và chạy lại setup.
  Dữ liệu, generated credentials và Docker volumes được giữ nguyên trong đợt
  chẩn đoán này; không thực hiện prune/reset.

Phần dưới là record hiện thực và kiểm chứng offline ngày 09/10/2026.

Đối chiếu theo yêu cầu người dùng và kiến trúc đã chốt. Trước đợt này đã có
Identity/BFF, Portfolio/Quant, outbox/inbox, core package và CI; baseline **84
Python tests đạt**. Đợt này bổ sung Market Data, staging template, fixtures/versioning
và hướng dẫn setup/API. Mã nguồn và cấu hình đạt các kiểm tra offline bên dưới;
**chưa xác nhận toàn bộ stack thật hoặc staging đã triển khai**.

## Các mốc

| Mốc | Đã có trong mã/cấu hình | Giới hạn còn lại |
| --- | --- | --- |
| Service foundation, contracts, CI, dev/staging | Monorepo Next BFF, Portfolio, Quant, Market; package/image/migrations/health riêng. Ba OpenAPI với Swagger Bearer; sáu JSON contracts/DTO schemas. CI Python/web/local stack/persistence và staging config. Local Compose + external-dependency staging template. | GitHub workflow chưa được chạy từ thay đổi này; staging chưa deploy. Các service của use case tương lai được giữ trong kiến trúc, chưa tạo empty scaffolds. |
| Keycloak, BFF session, ownership, schema theo use case | Code/PKCE, state/nonce, encrypted Redis tokens, opaque HttpOnly cookie, CSRF/refresh/logout; issuer/audience/expiry/signature/roles/scopes. Owner-scoped Portfolio/recommendations/jobs, Market creator-scoped ingestion jobs. DB owner/migrator/runtime riêng; migrations cho ba application DB. | Tests BFF/OIDC/Redis đạt; chưa chạy login thật với Keycloak/browser trong đợt này. SQLite không chứng minh runtime grants PostgreSQL. |
| Market ingestion/snapshots, durable jobs, outbox/inbox | `market_service`, CSV registry hash-pinned và normalized observations stock/fund/gold; explicit unit conversion; append-only revisions; atomic job/outbox và inbox/revision/status; durable quorum queue/DLQ; deadlines. Immutable snapshot pins/hashes, cutoff theo ingestion availability, missing/stale/ambiguous-source checks. Local upgrade giữ secrets/volumes/realm. | Provider baseline là CSV/import; chưa có live upstream crawler, exchange calendar/corporate actions. Market snapshots chưa tự xây numerical bundle cho Quant. Live broker/ACL/upgrade/persistence checks chưa chạy được. |
| Tách core, fixtures, version hóa app | Wheel `portfolio-core==0.1.0`, không dựa root globals/paths. Năm synthetic golden cases EW/MVO/BL_ML, 15 tests mới. Changelog và compatibility policy phân biệt refactor/legacy preservation với app behavior changes. | Fixtures chứng minh numerical contract hiện hữu, chưa chứng minh toàn bộ Phase 1 ranking/selection/trained-model parity. Không thay runtime/core version trong đợt này. |

## Bằng chứng kiểm chứng

Các lệnh chạy ngày 09/10/2026, múi giờ Asia/Ho_Chi_Minh:

| Layer | Trạng thái | Bằng chứng |
| --- | --- | --- |
| Python/API/core | **passed** | `.venv-software/bin/python -m pytest tests/software packages/portfolio-core/tests -q`: **150 passed**, 1 cảnh báo deprecated alias của Starlette/AnyIO. |
| Software lint | **passed** | Ruff trên packages/services/tests/software/infra và bốn software scripts. Broad lint `scripts/` phát hiện 56 lỗi có sẵn trong scripts nghiên cứu; không sửa nghiên cứu để làm software CI xanh. |
| HTTP/event contracts | **passed** | Export 9 JSON files; export lặp giữ nguyên SHA-256. Bearer security scheme có ở protected operations, health không cần token. |
| DB migrations | **passed (SQLite)** | Cả Portfolio, Quant và Market upgrade → metadata check → downgrade → upgrade. Chưa thay thế kiểm tra PostgreSQL thật. |
| Web/BFF | **passed (offline/local isolated tests)** | **21 tests**, `npm run typecheck` và `npm run build`. Suite Redis recovery đã chạy, không skip; OIDC transport deterministic ký JWT thật nhưng không phải live Keycloak login. |
| Core wheel | **passed** | Build/install vào venv tạm ngoài repo, import từ site-packages; copied suite **68 passed, 1 expected skip** do không có legacy source trong wheel environment. Deliberate risk-aversion mutation bị golden fixture phát hiện, sau restore suite đạt. |
| Local/staging config | **passed** | Hai Compose `config --quiet`; staging validator với example sentinel values đạt, strict mode từ chối placeholders. Không deploy staging. |
| Setup/Postman | **passed** | `setup_software.py prepare --enable-test-client --skip-install` dùng lại venv/node_modules và giữ credentials. `setup_software.py verify` chạy toàn bộ offline gates thành công. Postman 35 requests, 41 event scripts parse đúng; JSON hợp lệ và secrets/token values để trống. |
| Live Docker infrastructure/API/BFF/persistence | **blocked** | Docker Desktop process có tồn tại nhưng daemon `docker info` timeout trong probe 8 giây và `setup ... check` timeout 20 giây. Không có bằng chứng migration/grants/JWT/RabbitMQ/restart từ stack thật trong đợt này. |
| Independent source/config review | **passed** | Reviewer độc lập không tìm thấy Critical/Important blocker đã kiểm chứng; không thay live verification bằng review. |

## Chạy tiếp trên máy khi Docker đáp ứng

Theo [hướng dẫn setup và API](SETUP_AND_API_TESTING.md), điểm vào là:

```sh
python3 scripts/setup_software.py up --enable-test-client --refresh-demo
python3 scripts/setup_software.py verify --live
```

Lệnh `up` dùng dependency environment đã hợp lệ, build images, bật dependency
services, reconcile DB/broker/realm local cũ rồi chạy toàn bộ stack. Giữ credentials
và volumes; demo refresh tạo artifact identity mới. Smoke tạo dữ liệu demo và
receipt không chứa token cho Portfolio recommendation và Market job/snapshot.
Sau restart workers, `scripts/smoke_software.py --verify-receipt` đọc lại đúng
IDs/hashes cũ; hướng dẫn có lệnh restart đầy đủ.

Không đánh dấu live integration, provider crawling, numerical research parity
hoặc staging deployment hoàn tất chỉ từ các kết quả offline này. Chưa commit,
push hoặc deploy thay đổi; giữ các file/chỉnh sửa đã có của người dùng.


### Chat merge verification — 07/11/2026

- Fresh local verification: 540 Python/core tests passed with all three real
  PostgreSQL concurrency probes enabled; one unrelated opt-in test skipped.
  Web: 134 tests, TypeScript and production build passed. Ruff, 11 contract
  exports, Compose configuration and real DB/broker/Identity boundaries passed.
- Real Chat API lifecycle and four browser journeys passed: PKCE/confirmation/
  MVO/result/explicit accept/reconnect, session reauthorization, late refresh and
  late conversation creation. After restarting Chat/Portfolio/Quant processes,
  API and browser replay verified the same history, facts, input hashes and target.
- Initial browser attempts correctly failed on expired prepared real inputs.
  Renewed the existing immutable real snapshot through the standard publisher
  with freshness validation, then regenerated the API receipt before browser use.
  No source prices or stored expiration fields were edited.
- Fixed CSV metadata validation mixing host-local dates with the UTC observation
  contract; a regression reproduces local midnight before UTC midnight.
  Refresh rejection tests now use the Vietnamese business cutoff.
- CI exposed a setup test relying on the developer's existing venv executable;
  its fixture now selects the current runner's Python explicitly.
- The clean CI stack also exposed a stale G2 smoke assertion predating versioned
  risk policies. Updated it to check profile and revision-bound policy ID;
  17 onboarding/risk tests and the real G2 lifecycle passed after refreshing DEMO.
- Paid LLM, provider-outage and five-minute live grant-expiry gates were not
  repeated in this merge run. Prior dated evidence above remains historical.
  Knowledge RAG and untracked research extensions are outside this PR.
