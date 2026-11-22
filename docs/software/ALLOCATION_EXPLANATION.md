# Giải thích phân bổ có evidence

Triển khai theo [plan](../superpowers/plans/2026-11-22-allocation-explanation.md) và [thiết kế](../superpowers/specs/2026-11-22-allocation-explanation-design.md). Phần này giúp đọc kết quả đã tính, không thay đổi mô hình đầu tư, trọng số, input/result/facts hash, confirmation hoặc accept target.

## OpenAI thật — 22/11/2026, cap 1 USD

Người dùng đã xác nhận giữ cap **1 USD** cho đợt này, thay mức 0,50 USD của gate trước. Runtime đã là `KNOWLEDGE_BUDGET_USD=1.00`, approval/day quotas 100; giữ nguyên approval ID, counters, embeddings disabled và Auto Recharge. Không sửa prompt/code/model/solver để làm đẹp kết quả. Stack dùng local Auth JWT, PostgreSQL, broker, Chat/Portfolio/Quant thật; không mock HTTP hoặc sửa business SQL.

Đã chạy offline trước: **26 passed**, một warning deprecation. Tiếp theo chạy native BL_ML với model v5 đã duyệt vào một portfolio TEST riêng, qua explicit confirmation; recommendation `23df1353-2021-4d8d-bc19-c232b1f70148`, evidence COMPLETE, không fallback numerical, không accept target. Một conversation thứ hai đọc đúng recommendation này để thử câu nối tiếp mà không gửi recommendation ID.

| Gate | Kết quả thực |
| --- | --- |
| OpenAI Responses transport/schema | 11/11 trả usage và plan; không timeout/auth/quota error |
| Plan được validator chấp nhận | **8/11**; paid acceptance toàn bộ **PARTIAL**, chưa PASS |
| Deterministic fallback | 3/11; giữ nội dung đúng evidence |
| Facts/evidence/rendered claims | 11/11 khớp; không đổi numerical result |
| Follow-up không explicit ID | 2/2 giữ đúng recommendation; GVR đúng mã, ACB báo thiếu view |
| Corpus citations | 23 occurrences, 3 unique claims; đúng version/hash/text/manifest và pinned source Git blob |
| Chi phí mới | Actual usage: 21.650 input + 1.234 output tokens; adapter estimate **0,003323250 USD** |
| Reservations mới | 11 × 0,0017 = 0,0187 USD; không phải tiền đã bill |
| Hybrid/browser trong lượt paid | NOT RUN; embeddings vẫn tắt; browser template trước đó báo riêng |

Ba plan bị từ chối: sau confirmation chỉ chọn `limitations` nên thiếu nhóm overview; câu overview có claim ID `view_GVR` kèm ký tự lạ; một câu RSI chọn `features_CTG` nhưng thiếu `limitations`. Transport ghi VERIFIED chỉ nghĩa parse/schema hợp lệ; quyết định an toàn cuối cùng ở validator theo question/topic/hash. Không coi các lượt fallback là OpenAI acceptance PASS.

Đọc trực tiếp output: câu hỏi view/rổ/hồ sơ/K5/RSI/mã cụ thể đều có dữ kiện đã ghim; CTG RSI14 59.341, GVR view khoảng +0,61%/5 phiên. Không dựng view âm khi cả 5 views đều dương. Nội dung còn dài, lặp các đoạn BL_ML ở câu hỏi hẹp; RSI trả cả bộ features. Câu hỏi view tích cực/tiêu cực chưa nói rõ bằng câu riêng rằng run này không có view âm. Đây là đánh giá thủ công của agent trên 11 outputs, không phải human study hoặc full 24-case paid eval.

Nguồn Chat đã cite: `ml-views-definition`, `ml-views-limit` (ML views · BL_ML, v1), `risk-policy-boundary` (Hồ sơ rủi ro và policy, v1), corpus `knowledge-vi-v1`. Cả ba trỏ tới spec commit `67540341a7819cfc4cc8ea4b202a325bafd0b583`, locators `7.4 Train, publish, serve` và `8.1 Risk policy compiler`. Những đoạn này hỗ trợ phương pháp/policy; số liệu riêng của recommendation lấy từ canonical run evidence, không từ corpus. Đã kiểm Git blob nguồn có thật ở local; HTTP availability của URL nguồn chưa kiểm. Các citations được lexical retrieval chọn rồi recheck corpus/quyền; trong luồng finite explanation này OpenAI chọn **claim IDs**, không tự chọn/cấp các citation IDs.

Chi phí phải đọc đúng: token counts do OpenAI response trả là usage thực; **0,003323250 USD là estimate bảo thủ** của adapter, dùng input 0,125/output 0,50 USD/million. Theo [model pricing đã kiểm 22/11](https://developers.openai.com/api/docs/models/gpt-6-luna.md), nếu toàn bộ input uncached standard thì phép tính là 0,002782 USD. Ledger không giữ cache read/write breakdown; không truy vấn billing/admin, nên **invoice amount chưa đối soát**, không gắn nhãn estimate là actual billed USD. Usage chỉ gồm 11 job IDs của smoke, tách khỏi calls ngoài lượt test đang diễn ra đồng thời. Provider latency 1,372–2,152 giây, median 1,724 giây; chưa phải end-to-end hoặc load benchmark.

Sau khi kiểm không có Chat jobs đang xử lý, đã restart riêng Chat API/worker rồi verify **chính** hai paid receipts cùng hai template receipts cũ (d022/fc4d): facts/evidence/messages/citations/usage giữ nguyên, không gửi luồng thay thế hoặc gọi provider trong verify. Runtime config/cap giữ nguyên.

Receipt, từng output, raw finite plans, usage và kiểm trích dẫn nằm trong ignored `output/allocation-explanation/openai-20261122/`: `receipt.json`, `contextual-receipt.json`, `quality-report.json`, `audit.json`. Không stage evidence/logs/credentials. Nên ưu tiên các cải tiến tiếp theo: ràng buộc claim IDs bằng enum theo candidates; làm rõ overview sau confirmation; giảm lặp nguồn/feature dump; nói rõ khi không có view âm. Chưa triển khai các thay đổi đó trong lượt kiểm thử này.

Lệnh verify (chỉ đọc, không gọi provider):

```sh
.venv-software/bin/python scripts/smoke_allocation_explanation.py --verify-receipt --receipt output/allocation-explanation/openai-20261122/receipt.json
.venv-software/bin/python scripts/smoke_allocation_explanation.py --verify-receipt --receipt output/allocation-explanation/openai-20261122/contextual-receipt.json
```

## Dữ liệu và API

- Quant thu raw ensemble forecast 5 phiên, độ phân tán thành viên, confidence heuristic trước/sau điều chỉnh, P/Q thực sự truyền vào BL, features và regime từ cùng input slices. Native booster chỉ gọi một lần; lỗi thu evidence/builder không làm mất numerical result hợp lệ.
- `OptimizeResult.explanation_evidence` là optional sidecar, ngoài `result`; field absent không xuất trên legacy wire. Numerical run/outbox JSON lưu cùng receipt. Consumer tách raw sidecar trước khi kiểm numerical envelope, kể cả sidecar sai kiểu string/array/scalar.
- Portfolio migration `c9222026e001` (sau `b70211d9e301`) thêm nullable JSON `recommendation.explanation_evidence`. Không backfill, không sửa JSON kết quả cũ. Triển khai migration/readers trước producer mới.
- GET `/api/v1/recommendations/{id}/evidence` dùng cùng owner checks như recommendation. Delegated read-only tool `get_recommendation_evidence` dùng `resource_id`, kiểm owner/portfolio/conversation/job/grant expiry/revocation; không thêm quyền allocation/accept. BFF chỉ cho GET.
- Response `recommendation-evidence-v1` có recommendation/run IDs, canonical `facts_hash`, `quant`, `evidence_hash` và trạng thái `COMPLETE`, `PARTIAL`, `UNAVAILABLE`. Complete nghĩa đủ dữ kiện theo contract, không chứng nhận độ chính xác model hoặc PIT.
- Hash evidence tách khỏi hash numerical facts. Optional provenance pins được giữ đúng sự hiện diện trên wire để không rehash sidecar v1 đã phát. Kiểm lại pins/hash mỗi lần đọc; sidecar sai trả UNAVAILABLE, giữ nguyên allocation.

`history_end_date` là endpoint features/K5; `regime_end_date` và `covariance_end_date` ghi endpoint riêng. Trong nhánh USER_SELECTED hiện tại, features/K5 kết thúc trước decision session, còn covariance/regime dùng tới decision session. Không đổi các slice hoặc phương pháp này trong feature giải thích.

## Nội dung và giới hạn

Chat dựng finite claim IDs + template/fact references; OpenAI chỉ chọn/sắp xếp các claim được phép. Prompt nhận câu hỏi đã redacted, lịch sử ngắn hiện có và claim previews, không nhận quyền tự gọi tool hoặc sửa số liệu. Sai IDs/hash, thiếu chủ đề bắt buộc, bỏ hướng đối lập hoặc thay mã được hỏi bằng mã khác đều rơi về deterministic renderer.

Các câu hỏi về view, tín hiệu, RSI/features hoặc ảnh hưởng hồ sơ trong ngữ cảnh một recommendation đi vào read-only explanation, kể cả khi provider tắt/hết quota. Yêu cầu xem hồ sơ/thị trường hiện tại hoặc tạo đề xuất rõ ràng giữ routing cũ. Tool budget tăng từ6 lên7 để thêm đúng một evidence read; deadline20s và final owner/corpus recheck được giữ.

UI giữ V2.7, thêm bốn nhóm: hồ sơ, tín hiệu, bối cảnh rổ, vai trò tài sản. Mọi evidence-bearing message phải đối chiếu canonical facts và evidence API trước khi hiện cả panel lẫn saved prose; mismatch chỉ giữ allocation đã xác minh. Tin nhắn cũ không bị viết lại.

- K5 chọn đại diện theo tương quan; features quan sát được chưa phải attribution/SHAP hoặc lý do nhân quả của tỷ trọng.
- Raw ML forecast 5 phiên tách khỏi applied daily Q sau heuristic Option B. Confidence không phải xác suất tăng giá. View policy VFF relative tách khỏi ML và USER views.
- EW dùng tỷ trọng bằng nhau; MVO dùng return/covariance/constraints, không nói các chiến lược này đã áp dụng ML views.
- Regime mô tả rổ đã ghim, không phải VNINDEX/toàn thị trường hoặc nhận định thời điểm hiện tại. Drawdown là mức tại cuối cửa sổ so với đỉnh trong cửa sổ, không phải max drawdown.
- Legacy receipts chỉ dùng frozen facts/provenance; thiếu raw views/features ghi rõ NOT_RETAINED. Detailed capture hiện chỉ cho USER_SELECTED v5. Không infer model mới để bổ sung lý do cho kết quả cũ.
- `point_in_time_certified=false` giữ nguyên. SHAP, counterfactual, news/sentiment, market-wide context và training nằm ngoài phạm vi.

## Chạy offline và lexical

Từ repo root, dùng `.venv-software` đã setup:

```sh
.venv-software/bin/python -m pytest tests/software packages/portfolio-core/tests -q
.venv-software/bin/python scripts/eval_allocation_explanation.py --mode offline --output output/allocation-explanation/eval-offline.json
.venv-software/bin/python scripts/eval_knowledge.py --mode lexical --split all --output output/allocation-explanation/eval-lexical.json
npm --prefix apps/web test
npm --prefix apps/web run typecheck
```

Fixtures explanation v1 gồm24 ca synthetic và một facts/evidence fixture riêng, đều có SHA256. Không dùng fixture để tạo business SQL hoặc giả HTTP integration. Rubric tự động là topic/phrase assertions và reject hash/ID/claim sai; không coi đó là human relevance hoặc chất lượng LLM tự do. Hit@5 chỉ áp dụng retrieval, báo riêng.

## Real smoke, provider và restart

```sh
# Preflight không ghi business data hoặc gọi provider.
.venv-software/bin/python scripts/smoke_allocation_explanation.py --run --provider template --dry-run --receipt output/allocation-explanation/new-chat-receipt.json
# Với runtime test đã xác minh LLM/embeddings tắt:
.venv-software/bin/python scripts/smoke_allocation_explanation.py --run --provider template --worker-container allocation-explanation-template-worker --receipt output/allocation-explanation/new-chat-receipt.json
# Sau restart API/workers/Web: đọc CHÍNH receipt trên, không gửi luồng thay thế.
.venv-software/bin/python scripts/smoke_allocation_explanation.py --verify-receipt --receipt output/allocation-explanation/new-chat-receipt.json
```

Template CLI không tự tắt LLM trên server. Worker đang bật provider sẽ fail preflight. Nghiệm thu có thể dùng worker tạm cùng image/environment/DB thật với `CHAT_LLM_ENABLED=0`, `CHAT_QUERY_EMBEDDINGS_ENABLED=0`; kiểm không có Chat jobs khác trước khi tạm dừng worker chính, tránh tranh cùng queue, rồi khôi phục nguyên config. Không reset quotas, đổi grant cũ, xóa test records hoặc đổi volumes. Smoke tạo portfolio/conversation TEST riêng, đi qua explicit confirmation và hỏi tiếp bằng ngôn ngữ tự nhiên; không accept target. Mặc định là MVO DEMO. Native BL_ML dùng --strategy BL_ML --source-portfolio-id để đọc candidates/answers đã xác nhận từ portfolio cùng owner và tạo một portfolio TEST mới; không sửa portfolio nguồn hoặc train model.

Paid dry-run cần approval thực sự và cap cụ thể:

```sh
.venv-software/bin/python scripts/smoke_allocation_explanation.py --run --provider openai --approval-id APPROVED_ID --max-cost-usd 1.00 --dry-run --receipt output/allocation-explanation/new-openai-receipt.json
```

`APPROVED_ID` là placeholder, không phải quyền chi tiêu. Chỉ bỏ dry-run sau khi approval/budget hiện hành đã được đối chiếu. Script chặn nếu cap không khớp runtime, thiếu key/model/approval, embeddings bật, hoặc reservation/quota vượt giới hạn. Upper bound8calls × USD0.0017 = USD0.0136; đó là reservation/estimate theo adapter hiện có, không phải hóa đơn hoặc giá provider mới xác minh. Không đổi Auto Recharge. Paid gate chỉ PASS khi tất cả explanation turns có verified claim plan và usage thành công; reservation/timeout/template không được tính là paid success.

`eval_allocation_explanation.py --mode live|verify` reuse smoke/receipt thực; không gửi synthetic facts vào business API và không gọi live smoke là24synthetic cases đã chạy qua provider.

## Evidence nghiệm thu 22/11/2026

Artifacts nằm trong ignored `output/allocation-explanation/`, không đưa vào Git:

- Baseline: Python/core911passed,10skipped; web162passed, TypeScript đạt; đọc UI thật trên recommendation hiện có. Giữ warning Starlette/anyio deprecation riêng.
- Real Quant→Portfolio MVO synthetic DEMO: recommendation `76081cdc-9002-464f-bca2-56da1d80b32e`, sidecar PARTIAL, receipt `backend-receipt.json`. Chỉ append DEMO bundle mới; giữ artifacts/catalog history cũ.
- Real Chat template: recommendation `fc4d87d6-c6d4-496f-aaac-c736a8abeeae`, receipt `chat-receipt.json`, explicit confirmation + five follow-ups,0provider calls; worker chính được khôi phục. Các kiểm tra sau fix/restart/browser được ghi ở verification cuối, không suy ra từ lượt smoke này.
- Offline explanation:24/24 assertions; topic/phrase relevance21/21 so với3/21 renderer cũ;3ca reject hash/resource/claim tách khỏi denominator relevance. Human review cần đọc output; không phải benchmark model.
- Lexical real API: dev8/8, heldout14/16 Hit@5 (87,5%), không tăng so với baseline.0embedding/dialogue calls trong lexical eval.
- Paid dry-run blocked: runtime budget1USD khác cap0,50USD đã duyệt trong cuộc trò chuyện; upper reservation0,0136USD, ledger estimate hiện có0,006038500USD. Không tăng ngân sách hoặc gọi OpenAI.
- Native BL_ML **PASS** sau khi kiểm đúng portfolio-scoped readiness: model70716105-ef74-4203-bfa6-9657f756e0b6, epoch16/11; recommendationd022809e-8c99-466b-9f9b-94a15b9e7284, evidenceCOMPLETE.5MLviews đều dương,0policyviews; features5equities, K5 active7assets,6positive weights. Features/K5 đến16/11, covariance/regime đến17/11. Receipt `native-bl-ml-receipt.json`,0provider calls, không accept target. Kết luận blocker từ universe-level readiness lúc đầu không áp dụng cho scoped portfolio; không refresh market/train/publish để đạt gate. Hybrid paid embeddings NOT RUN.

Final: full Python/core **960 passed, 10 skipped**, một warning deprecation. Sau full suite, bổ sung một regression future-tail cho evidence và chạy lại nhóm liên quan **17 passed** (có overlap, không cộng vào 960). Web168passed, TypeScript/Ruff và production builds đạt. Browser thật sau restart đạt tại CSS1440×1000,390×844,375×844: native views/features,2citations knowledge-vi-v1, cùng evidence hash, không overflow/runtime errors; Enter mở features/source/audit, suggestion chỉ điền draft. Không gửi message khi kiểm browser. Viewport override đã reset; login phiên riêng không đổi tài khoản Chrome hiện có.

Restart9services đã đổi; verify đúng cả native d022, Chat MVO fc4d, backend MVO7608 và original v5 f1a6 receipts đạt. Facts/evidence/messages/citations/claims/usage giữ nguyên, không gửi luồng thay thế. Preservation các row/artifacts/accounts/volumes/catalog history cũ đạt;154tin nhắn cũ và dev config cũng nguyên vẹn. Chi tiết tại ignored `post-restart-verification.json`, `original-v5-verification.log`, `preservation-final.log`, `runtime-preservation.json` và `browser-verification.json`. Chưa kiểm screen reader/thiết bị vật lý hoặc paid OpenAI/hybrid.

## Lệnh native đã dùng

```sh
.venv-software/bin/python scripts/smoke_allocation_explanation.py --run --provider template --strategy BL_ML --source-portfolio-id 404b2043-5967-4988-b8de-1c030ba3b879 --worker-container allocation-explanation-template-worker --receipt output/allocation-explanation/native-bl-ml-receipt.json
.venv-software/bin/python scripts/smoke_allocation_explanation.py --verify-receipt --receipt output/allocation-explanation/native-bl-ml-receipt.json
.venv-software/bin/python scripts/smoke_chat_input_refresh.py --verify-receipt --receipt output/bl-ml-epoch-20261116/chat-flow-receipt.json
```

Source portfolio ID là fixture của checkout hiện tại; với cài đặt khác phải dùng portfolio thuộc owner và có scoped readiness READY, không thay bằng số liệu giả. Chạy lại --run cần receipt path mới; verify luôn giữ path cũ.


## Gate và checklist đề nghị cập nhật

Chưa sửa Google Sheet. Các mục sau là đề nghị để người dùng duyệt:

| Mục | Trạng thái thực | Bằng chứng / giới hạn |
| --- | --- | --- |
| Sidecar, migration, owner/delegated read API | PASS | Real PostgreSQL + Quant/Portfolio; sai owner/admin 404, anonymous 401 |
| Native BL_ML evidence + Chat template | PASS | Model v5 cũ; receipt d022; COMPLETE; 0 provider calls |
| MVO partial + legacy compatibility | PASS | Receipts 7608/fc4d, old hash/wire regressions |
| Real EW | NOT RUN | EW/no-ML có unit coverage; chưa có real receipt riêng |
| Offline tiếng Việt | PASS theo rubric tự động | 24/24; topic/phrase 21/21 so với baseline 3/21; không phải human quality score |
| Lexical retrieval | Đã chạy, chưa đạt mục tiêu 90% heldout | Hit@5 14/16 = 87,5%, không cải thiện trong feature này |
| UI + browser | PASS trong viewport đã kiểm | 1440/390/375 CSS px, keyboard disclosures; screen reader/thiết bị thật NOT RUN |
| Restart/preservation | PASS | Verify chính 4 receipts, 154 tin nhắn cũ và runtime flags giữ nguyên |
| OpenAI trả phí / hybrid embeddings | OpenAI PARTIAL; hybrid NOT RUN | Sau approval giữ cap1USD: 8/11 plans accepted, 3 fallback; xem phần OpenAI thật phía trên |
| PIT certification / hiệu quả đầu tư | Không thay đổi, chưa chứng nhận | Giữ point_in_time_certified=false; không suy từ explanation tests |

Report máy đọc: ignored `output/allocation-explanation/verification.json`. Logs và ảnh không được stage. Không commit/push/merge trong đợt triển khai này.
