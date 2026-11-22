# Allocation Explanation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Không commit/push/merge; giữ mọi thay đổi chưa commit của người dùng.

**Goal:** Giải thích views, bối cảnh rổ tài sản, vai trò từng mã và liên hệ hồ sơ bằng evidence từ chính lần tính allocation.

**Architecture:** Quant phát sidecar evidence độc lập numerical result; Portfolio kiểm và lưu bất biến, cung cấp owner-scoped read API. Chat dùng finite claims/templates từ evidence và citations hiện có; UI tiếp tục bố cục V2.7. Không đổi thuật toán, input/result/facts hash hoặc accept semantics.

**Tech Stack:** Python/Pydantic/FastAPI/SQLAlchemy/Alembic, PostgreSQL/RabbitMQ, native XGBoost/portfolio-core hiện tại, OpenAI structured adapter hiện có, Next.js/React/TypeScript/Vitest/Playwright. Không thêm dependency/service/vector store.

**Spec:** [2026-11-22-allocation-explanation-design.md](../specs/2026-11-22-allocation-explanation-design.md).

**Trạng thái:** Người dùng đã duyệt triển khai ngày22/11/2026. Đã triển khai và nghiệm thu offline, MVO/native BL_ML, template Chat, browser và persistence. OpenAI đã chạy sau approval giữ cap1USD: PARTIAL8/11 plans accepted; hybrid và real EW receipt riêng NOT RUN. Không đánh dấu các gate chưa đạt là hoàn tất. Kết quả thực tại `docs/software/ALLOCATION_EXPLANATION.md` và `IMPLEMENTATION_STATUS.md`.

## Global Constraints

- Giữ thuật toán, trọng số, numerical diagnostics, canonical recommendation JSON/hash, confirmation và accept hiện tại.
- Không train lại, sửa research, lấy tin tức mới, thêm agent tự do hoặc tự tạo allocation từ câu hỏi giải thích.
- Không reset/stash/clean, không chạm `extensions_C_v1/`, secrets, old data/volumes, model hoặc receipts cũ; không sửa Google Sheet. Evidence/log/screenshot/cache nằm ngoài Git.
- Backend/API/evidence → real backend gate → Chat/UI; frontend không đi trước integration thật. TDD cho logic/security mới.
- Consumer-compatible contracts/migration triển khai trước producer sidecar. Field absent bị bỏ khỏi wire để giữ legacy payload.
- Không backfill raw views/features cho receipt cũ. Không đổi `point_in_time_certified=false`.
- Provider dùng dev config và quota/reservation hiện tại. Budget trong tài liệu không tự tạo quyền chi tiêu; không đổi Auto Recharge. Hoàn tất offline và deterministic fallback trước paid acceptance.

## Review Focus

1. Người dùng đã đổi hồ sơ/vốn/basket: giải thích vẫn dùng phiên bản của recommendation cũ — test ở E2/E3.
2. View dương nhưng weight0, view policy relative và confidence heuristic: không dựng quan hệ nhân quả/probability — test ở E1/E3.
3. Snapshot/model/corpus mới hoặc evidence thiếu: không lấp bằng latest, không sửa facts hash/receipt — test ở E2/E5.
4. Owner/grant/cross-conversation/injection: không lộ evidence hoặc phát sinh allocation/accept — test ở E2/E3.
5. Provider lỗi/quota và UI mobile có nội dung dài: vẫn đủ nội dung có nguồn, không overflow hoặc kẹt bàn phím — test ở E3/E4.

## Khảo sát trước khi triển khai — E0

**Files đọc:** `apps/web/AGENTS.md`, `docs/TECHNICAL_SPECIFICATION_PHASE_2.md`, `docs/software/IMPLEMENTATION_STATUS.md`, `POINT_IN_TIME_AUDIT.md`, `CHAT_LLM_PLAN.md`, `KNOWLEDGE_RAG.md`, `ASSET_SELECTION_UI.md`, handoff V2.4/V2.5 và `docs/superpowers/plans/2026-11-22-figma-v27-frontend.md`.

- [x] Chụp status/diff và hash các source/receipt liên quan vào ignored output; tái khảo sát vì source hiện tại đã có V2.7/asset metadata chưa commit. Không chỉ đọc HEAD.
- [x] Chạy baseline Python/core + web/TypeScript. Đọc real stack/browser trên receipt hiện có; ghi rõ stack auth đang chạy, không mặc nhận Keycloak từ tài liệu cũ. Không dùng HTTP mock làm integration proof.
- [x] Ghim baseline receipt/facts/hash/weights/targets, model manifest và usage ledger; không in credentials. Lỗi liên quan phải có regression trước khi sửa. Blocker freshness/model không cho phép tự train/refresh dữ liệu cũ.
- [x] Giữ chuỗi overlay/ports/user-selection/dev provider config đang dùng. Lập danh sách gate NOT RUN nếu dependency chưa sẵn sàng; tiếp tục phần offline độc lập.

## E1 — Thu evidence trong cùng numerical run

**Files:**
- Create `packages/contracts/src/portfolio_contracts/explanation.py` và `packages/contracts/schemas/optimization-explanation-v1.json`.
- Modify `packages/contracts/src/portfolio_contracts/__init__.py` (`OptimizeResult`, export).
- Modify `services/quant-serving/src/quant_service/asset_ensemble.py`, `selection.py`, `workflow.py`.
- Create `services/quant-serving/src/quant_service/explanation.py`.
- Test `tests/software/test_quant_explanation_evidence.py`, `test_selection_worker.py`, `test_selection_contracts.py`, `test_temporal_regressions.py`.

**Interfaces:**
- `infer_asset_views(..., evidence: dict | None = None) -> dict` giữ return P/Q/confidences và mặc định caller cũ. Khi có collector, điền raw member stats/features/threshold/transform ngay trong lần inference đó; không gọi booster lần hai.
- `resolve_selection(..., evidence: dict | None = None)` giữ tuple 3 phần tử hiện tại; collector lấy regime/proof/features cùng input slices.
- `build_quant_evidence(command: OptimizeCommand, run_id: str, numerical: dict, captured: dict) -> OptimizationExplanationEvidence`; không sửa `numerical` hoặc `result`.
- `OptimizeResult.explanation_evidence: dict | None = None`, serializer bỏ absent. Producer phải dựng bằng `OptimizationExplanationEvidence.model_dump(mode="json")`; consumer kiểm typed body riêng trong guarded block để invalid sidecar không chặn valid numerical envelope. Quant Run/outbox JSON sẵn có giữ sidecar, không cần Quant migration.

- [x] Viết test fail: P/Q/confidence và output allocate/hash trước/sau instrumentation giống hệt; native prediction gọi đúng một lần; asset order giữ nguyên; collector không được trộn vào `numerical` truyền allocator.
- [x] Viết test fail: inject collector/builder exception vẫn trả allocation thành công và cùng numerical result/hash, evidence unavailable; lỗi inference/allocator thật vẫn fail đúng code cũ. Đặt error boundary riêng cho instrumentation để không rơi vào broad ValueError handler của Quant execute.
- [x] Viết test fail: abs(raw)<0.001/đúng0.001, positive/negative, vol nhỏ, confidence damping; Q daily tách raw5phiên; VFF relative POLICY; không fabricate GOLD view; EW/MVO không có ML view. Test strict bounds/nonfinite/duplicate IDs/wrong units.
- [x] Regression appended future prices không thay features/views/selection/evidence/hash; actual endpoints khớp slice hiện tại. `point_in_time_certified=false` giữ nguyên. Bổ sung kiểm chứng behavior đang đúng, không sửa numerical implementation; nhóm temporal/evidence17passed.
- [x] Chạy các test mới để xác nhận RED; triển khai collector và typed builder tối thiểu; chạy lại GREEN cùng selection/temporal regressions.
- [x] Với legacy fixed-universe/full paths: đọc `artifacts.py`, `full.py::infer_full`, `ml.py::infer` trước khi chạm. E1 chỉ thu detailed raw evidence cho USER_SELECTED v5; các path khác xuất `PARTIAL` từ inputs/diagnostics đã có, không đoán cùng transform/horizon. Không báo detailed support cho path chưa implement/test.

## E2 — Portfolio lưu sidecar và cung cấp API read-only

**Files:**
- Create `services/portfolio/src/portfolio_service/explanation.py`.
- Modify `models.py`, `workflow.py`, `api.py`, `delegation.py` trong cùng service.
- Create migration `services/portfolio/migrations/versions/<new_revision>_recommendation_explanation_evidence.py` (resolve Alembic head thực tế trước khi sinh).
- Add `RecommendationEvidence` vào contract `explanation.py`; schema `recommendation-evidence-v1.json`.
- Test `tests/software/test_recommendation_evidence.py`, `test_selection_result.py`, `test_chat_authorization.py` (dùng test authorization hiện có nếu tên thay đổi).

**Interfaces:**
- Một cột nullable JSON `Recommendation.explanation_evidence`, chứa sidecar/hash hoặc bounded invalid-evidence status; không sửa `Recommendation.result`/`recommendation_json`.
- `recommendation_evidence(value: Recommendation, job: Job, facts: dict) -> RecommendationEvidence`; chỉ dùng frozen recommendation/job input.
- GET `/api/v1/recommendations/{id}/evidence` và delegated tool `get_recommendation_evidence` với args `resource_id` theo `ToolArguments` hiện tại; response cùng schema/status. Tái dùng owner/grant checks hiện tại, thêm Tool allowlist và mở max tools từ5 lên6 có regression cho grant đầy đủ; không nới arbitrary tool arguments.

- [x] Viết test RED: old/new OptimizeResult round-trip; migration để old rows NULL, không backfill; bad pins/hash/nonfinite/asset order không xuất evidence sai. Numerical validation vẫn fail như trước; evidence invalid không đổi hoặc loại bỏ numerical result hợp lệ.
- [x] Viết test RED: duplicate delivery/retry giữ một sidecar và cùng hash; thay current profile/capital/selection không đổi evidence; old result trả PARTIAL/NOT_RETAINED không gọi inference. API response canonical cũ byte/hash-equivalent.
- [x] Viết test RED: human owner, wrong owner/portfolio404, expired/revoked/wrong job/conversation grant, missing read permission; service credential đơn lẻ không đọc user evidence.
- [x] Triển khai model/migration/validator/builder/API/tool; reader rollout trước producer, không để old StrictModel consumer nhận unknown field. Tích hợp transaction result/outbox/inbox hiện tại.
- [x] Focused tests, migration/transaction và real Quant→Portfolio MVO + native BL_ML đạt; không sửa SQL business results hoặc train/refresh để pass. EW/no-ML unit regressions đạt.
- [ ] Real EW receipt riêng NOT RUN; không suy từ MVO/unit coverage.
- [x] Lưu receipt thật gồm IDs, canonical facts hash, evidence hash, run/model/snapshot pins. **Backend gate phải PASS trước E4.**

## E3 — Chat chọn claims theo câu hỏi, eval tiếng Việt trước provider

**Files:**
- Create `services/chat/src/chat_service/explanation.py`.
- Modify `tools.py`, `workflow.py`, `openai_provider.py`, `provider.py`, `llm.py` trong Chat.
- Create `tests/software/test_chat_explanation_evidence.py`, `tests/fixtures/knowledge/eval-allocation-explanation-vi-v1.jsonl` + `.sha256`.
- Create `scripts/eval_allocation_explanation.py`; reuse `scripts/eval_chat_contextual.py`, `eval_knowledge.py` contracts/helpers nếu phù hợp, không đổi fixture baseline đã freeze.

**Interfaces:**
- `build_claims(facts: dict, evidence: RecommendationEvidence) -> list[ExplanationClaim]` và `render_claims(claims: list[ExplanationClaim], selected_ids: list[str]) -> str` ở Chat; template IDs hữu hạn, refs về JSON paths allowlisted, bounded text.
- Plan mới `explanation-claims-v1` trả `facts_hash`, `evidence_hash`, ordered `selected_claim_ids` tối đa8; không prose/numbers/URLs/tool calls. LLM không nhận arbitrary JSON pointer quyền đọc hoặc full profile answers.
- Chat message thêm sibling `explanation_evidence`/hash, selected claim IDs và renderer/prompt/schema versions; `facts`, `facts_hash`, Knowledge citations/corpus version giữ nguyên. Không sửa message đã lưu.
- CLI mới: `--mode offline|live|verify`, `--cases PATH`, `--output PATH`; live thêm `--dry-run`, `--approval-id`, `--max-cost-usd`, `--receipt`; verify chỉ đọc receipt/DB APIs, không gọi provider/tạo message.

- [x] Viết test RED cho 4 nhóm claims, lựa chọn theo câu hỏi/nối tiếp đúng recommendation, old/partial evidence, hết quota/timeout/invalid provider plan → deterministic fallback. Câu hỏi explanation không tạo allocation/accept hoặc paid intent không cần thiết.
- [x] Viết test RED: overview đủ4nhóm và cân bằng cả hai dấu nếu có; provider bỏ nhóm bắt buộc thì validator dùng fallback. Câu hỏi tập trung chỉ cần nhóm liên quan, không ép lặp lại toàn bộ explanation.
- [x] Viết test RED: unknown/duplicate claim, sai facts/evidence hash, injection trong question/metadata/passage, selected claim dẫn sai ref, unsupported causal/probability/tin tức claim bị chặn. Không dựa regex để chứng minh prose tự do đúng.
- [x] Triển khai read tool và finite claim builder/render; reuse invocation ledger/reservation/prompt adapter, không thêm vòng agent hoặc paid rewrite/embeddings.
- [x] Freeze tối thiểu24 ca tiếng Việt trước tinh chỉnh: 8 ca bốn chủ đề; 6 ca unit/horizon/source/zero-weight/selection-vs-optimization; 4 ca nối tiếp/đổi hồ sơ/kết quả cũ; 6 ca thiếu evidence/provider failure/authorization/injection. Fixture synthetic phải ghi rõ, không coi là real integration.
- [x] Offline chạy cùng fixtures: baseline renderer source hiện tại vs claim renderer mới; báo numerator/denominator từng nhóm. Gate: 100% numerical/unit/reference/hash match; 0 unsupported causal/probability claims; 0 unauthorized reads/mutations; 100% fallback correctness. Core complete-evidence cases phải có đủ cả4nhóm; ca hỏi tập trung phải trả đúng chủ đề. Chấm rõ rubric relevance, không lấy LLM tự chấm làm ground truth duy nhất.
- [x] Báo Hit@5/citation correctness riêng bằng knowledge eval hiện có khi có retrieval; Hit@5 không đo mức đúng của raw ML hoặc mức hay của lời giải thích. Không gộp corpus explanatory citation với run-specific evidence reference. Case không có retrieval ghi N/A, gate chưa chạy ghi NOT RUN.
- [x] Kiểm tra human-readable output cho tối thiểu một case mỗi nhóm và case xung đột positive view/zero weight; ghi nhận giới hạn template, không mở free prose để đạt điểm.

## E4 — UI bổ sung nội dung vào V2.7

**Files:**
- Modify `apps/web/src/lib/chat-types.ts`, `apps/web/src/server/bff.ts`, `apps/web/src/components/chat-workspace.tsx`, `chat-workspace.css`.
- Create `apps/web/src/components/recommendation-evidence.tsx` và `apps/web/tests/recommendation-evidence.test.tsx` để tránh nới component chat quá lớn.
- Update `apps/web/tests/chat-bff.test.ts`, `chat-workspace.test.tsx`, `chat-types.test.ts`, `tests/browser/chat.e2e.ts`.

**Interfaces:** `RecommendationEvidenceView({ evidence, facts }: { evidence: RecommendationEvidence; facts: Recommendation })`; frontend mirror contract only, không tự infer/annualize/risk-score. BFF GET endpoint mới trỏ Portfolio, không nhầm Chat explanation endpoint.

- [x] Trước UI edits, đọc live Figma mới nhất và handoff V2.7, `apps/web/AGENTS.md`/Next guide liên quan. Dùng ui-ux-pro-max và impeccable; giữ controls/tokens/layout hiện tại. Không ghi Figma hoặc thêm design system trong task này.
- [x] Viết SSR/contract test RED cho4nhóm, PARTIAL/UNAVAILABLE/legacy, same-facts nhưng evidence sai ID/hash, unknown source, long ticker/feature labels. Không render evidence chưa đối chiếu canonical API; không làm message cũ mất khả năng đọc.
- [x] Triển khai tóm tắt3–5ý và disclosure4nhóm; raw technical evidence/32zero rows chỉ ở audit. Positive/negative có chữ/dấu; không dùng màu làm nguồn ý nghĩa duy nhất. Giữ CTA và suggestions chỉ điền draft.
- [x] Verify keyboard/focus và 1440/390/375px với backend thật; canonical card/evidence/message cùng ID, nguồn mở đúng passage/run pin. Giữ layout khi nguồn thiếu hoặc provider template. Review lại bằng impeccable trên rendered output.
- [x] Chạy `npm --prefix apps/web test`, `npm --prefix apps/web run typecheck`, production build theo runtime hiện có. Browser fixture tests là frontend verification, phải tách real-stack result.

## E5 — Real acceptance, restart cùng receipt, runbook

**Files:**
- Create `scripts/smoke_allocation_explanation.py`; reuse auth/request/receipt helpers từ smoke Chat hiện tại.
- Modify `docs/software/SETUP_AND_API_TESTING.md`, `IMPLEMENTATION_STATUS.md`, `CHAT_LLM_PLAN.md`; thêm contract usage vào runbook, không đổi các kết quả audit cũ.

**Interfaces:** smoke `--run --receipt PATH [--provider template|openai] [--approval-id ID --max-cost-usd CAP --dry-run]`; `--verify-receipt --receipt PATH` không có mutation/provider I/O. E3 eval giữ interface riêng cho fixture metrics; smoke kiểm owner/API/persistence.

- [x] Đối chiếu budget approval thực sự và ledger hiện hành trước paid run. Dry-run in số calls/token upper bounds/pricing config/version/reservation total và chi phí còn lại; thiếu giá/cap hoặc tổng vượt remaining budget thì không gọi. Không reset counter/đổi budget để chạy acceptance.
- [x] Chạy offline provider inject rồi real HTTP/PostgreSQL/Portfolio/Quant template + native ML; không gọi đó là paid-provider acceptance.
- [ ] OpenAI gate chưa PASS: người dùng đã duyệt giữ cap1USD, chạy11calls thật,8plans accepted/3fallback. Hybrid NOT RUN. Giữ nguyên budget/counters; report22/11 trong ALLOCATION_EXPLANATION.md.
- [x] `--provider template` chỉ là yêu cầu kiểm tra, không tự chọn provider phía server: preflight worker config phải xác minh developer LLM disabled/adapter không thể gọi provider. Nếu worker đang bật OpenAI thì fail preflight/NOT RUN, không âm thầm đổi config đang dùng. Dùng runtime test đã cấu hình đúng khi có; assert zero provider I/O và không tăng reservations/usage trong template receipt. OpenAI mode phải preflight theo chiều ngược lại.
- [x] Trên tài khoản/portfolio test riêng, tạo đề xuất có confirmation thật, hỏi4nhóm và câu nối tiếp; trace kiểm không có allocation/accept ngoài luồng xác nhận. Không accept target chỉ để kiểm explanation.
- [x] Receipt ghim recommendation/run/input/facts/evidence/corpus/claim/message hashes, profile version, model/snapshot IDs, usage reservations/tokens/cost estimate. Đọc lại receipt trước restart làm baseline; không lấy recommendation latest.
- [x] Restart các API/workers đã thay đổi theo service config hiện tại, giữ volumes/env/ports. Verify **chính receipt đó** qua APIs, cùng message text/claims/citations/hash/usage; không gửi message mới, không infer lại, không tăng provider usage. Old receipts cũng giữ facts/message/target hashes.
- [x] Chạy regression suite phù hợp, self-review diff gồm migration rollout, grant boundaries, finite claims, old hash compatibility; sửa findings trong phạm vi bằng regression.
- [x] Bàn giao bảng riêng: offline logic; lexical retrieval; hybrid paid embedding; real native BL_ML; template Chat; OpenAI; browser; persistence; eval/usage. Mỗi gate PASS/FAIL/NOT RUN với command/receipt và giới hạn. Không đánh dấu hybrid/PIT/historical validation đạt từ explanation test.
- [x] Cập nhật docs với kết quả thực, checklist Google Sheet đề nghị để người dùng duyệt riêng. Không commit/push/merge hoặc sửa Sheet.

## Lệnh kiểm tra dự kiến sau triển khai

Các file/flags mới bên dưới là deliverable của plan, **chưa tồn tại/chưa chạy trong lượt lập plan**:

```sh
.venv-software/bin/python -m pytest tests/software/test_quant_explanation_evidence.py tests/software/test_recommendation_evidence.py tests/software/test_chat_explanation_evidence.py -q
.venv-software/bin/python scripts/eval_allocation_explanation.py --mode offline --cases tests/fixtures/knowledge/eval-allocation-explanation-vi-v1.jsonl --output output/allocation-explanation/eval-offline.json
.venv-software/bin/python scripts/smoke_allocation_explanation.py --run --provider template --receipt output/allocation-explanation/receipt.json
# Sau restart: chỉ đọc lại cùng receipt.
.venv-software/bin/python scripts/smoke_allocation_explanation.py --verify-receipt --receipt output/allocation-explanation/receipt.json
npm --prefix apps/web test
npm --prefix apps/web run typecheck
```

Paid dry-run cần approval/cap cụ thể đang được duyệt; không điền một con số mặc định vào lệnh. Chỉ bỏ `--dry-run` khi preflight xác nhận quyền và remaining budget.

## Những việc cố ý để sau

SHAP/counterfactual, attribution solver, market-wide VNINDEX context, news/sentiment, dữ liệu cơ bản để giải thích dự báo, model training, đổi numerical policy và backfill dự báo lịch sử. Detailed raw evidence cho legacy fixed/full model paths là phần mở rộng riêng; MVP trả PARTIAL trung thực. Chỉ mở rộng khi có nhu cầu và evidence owner tương ứng.

## Review tài liệu

Đã self-review và builder review độc lập trên source liên quan. Đã sửa ba điểm: tách lỗi evidence khỏi numerical workflow cả hai phía, tái dùng delegated `resource_id`, và bắt buộc kiểm worker config/zero usage cho template acceptance. Đây là review plan, không phải kết quả test hoặc integration.
