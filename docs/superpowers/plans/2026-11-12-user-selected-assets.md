# User-selected assets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cho user lưu tập tài sản được phép cân nhắc; chọn K5 trong job BL_ML; giữ freshness7ngày và toàn bộ dữ liệu/lịch sử hiện có.

**Architecture:** Tách catalog, candidate revision và active job set. Market cung cấp snapshot có coverage từng mã; Quant dùng prepared panel chung và model asset-wise v5, preflight theo candidate nhưng chỉ chạy K5 trong worker. Consumer kiểm tra selection proof và lưu result immutable; nhánh legacy giữ nguyên.

**Tech Stack:** Python/Pydantic/SQLAlchemy/Alembic, PostgreSQL, RabbitMQ, NumPy/CVXPY/XGBoost native UBJ, Next.js/React/TypeScript, Vitest/Playwright, Compose `portfolio-auth-demo`; không thêm framework/dependency mới.

**Spec:** [2026-11-12-user-selected-assets-design.md](../specs/2026-11-12-user-selected-assets-design.md). User đã duyệt hai mặc định và Task0–16; đã triển khai/kiểm chứng local ngày12/11/2026. Bằng chứng và IDs xem docs/software/PHASE1_LOCAL_SERVING.md và acceptance.json của đợt user-selected-local.

## Global Constraints

- Candidate1–32 mã trong catalog thực; optimize tối thiểu2 và phải khả thi; cap<=0,50, floor defensive>=0,15, cap non-defensive<=0,70 cho policy custom mặc định. VFF defensive, GOLD non-defensive; không tự thêm VFF/cash/nới risk.
- BL_ML: equity_count<=5 dùng tất cả; >5 chọn đúng5 trên equity candidate; GOLD/VFF chỉ có khi user chọn. EW/MVO dùng toàn candidate. Tick không bắt buộc trọng số dương.
- Freshness đúng7 ngày lịch trên observation đủ điều kiện, kiểm tra lại ở worker theo actual local date; VFF5 observed-session buffer, GOLDnext-day giữ nguyên. Nhánh custom dùng latest completed session; legacy checkpoint5 không đổi.
- Không dùng dữ liệu chưa ingested/known, không backdate first-seen/publication, không loại candidate stale ngầm, không fallback EW ngầm. Model phải APPROVED/artifact_ready và native hashes hợp lệ.
- Model v5 target150UBJ khi30equity đủ dữ liệu; coverage thiếu phải công bố và chỉ chặn portfolio cần mã thiếu. Không train trong optimize request.
- Schema snapshot1–2, model1–4 và bundle1 vẫn đọc/execute như cũ. Source snapshot3/model5/bundle2 chỉ cho nhánh custom. Không retrofit portfolio/proposal cũ.
- Migration additive; optional field vắng mặt không đổi legacy canonical hashes. Owner isolation, If-Match, idempotency, outbox/inbox và deadline/fence được giữ.
- Không reset Auth/accounts, volume, source/model artifacts hoặc workspace dirty. Chỉ build bằng Dockerfile Compose chuẩn; không vá layer container. Không commit thay đổi có sẵn của user.
- Feature gate server `USER_SELECTED_ASSETS_ENABLED=false` mặc định; reader/worker rollout trước producer. Capacity và backup phải đạt Task0 trước runtime mutations.

## Review Focus

1. VFF thiếu/stale ngoài candidate không làm mất catalog hay chặn job không cần nó — test ở2/3/4/10.
2. Candidate set không có nghĩa positive-weight set; dữ liệu thiếu không được ngụy trang là K5 loại mã — test ở6/12/14.
3. Một/two-asset và thiếu defensive có thể vô nghiệm dù có model — test ở6/7/14.
4. Selection/profile thay đổi trong lúc job chạy hoặc redelivery sau deploy không được đổi pin/hash/history — test ở1/5/11/13/16.
5. Asset coverage/model epoch/native path hoặc available_at không khớp không được thành BL_ML READY/SUCCEEDED — test ở4/8/9/10/12/16.

## Hợp đồng chung phải khóa ở Task1

- `SelectionRevision`: `revision_id`, `portfolio_id`, `portfolio_version`, `candidate_asset_ids` (canonical catalog order), `candidate_hash`, `selection_policy_id='user-k5-v1'`, `risk_policy_id='custom-mixed-risk-v1'`, `created_at`. `candidate_hash` hash của ordered IDs + catalog version; không chứa actor/time.
- `SelectionContext` optional trong `OptimizeCommand`: `revision_id`, `candidate_asset_ids`, `candidate_hash`, `selection_policy_id`, `data_policy_id='user-selection-data-v1'`, `regime_policy_id='candidate-regime-v1'`, `regime`, `regime_input_hash`, `decision_at`, `decision_session`, `valid_until`. `command.constraints` vẫn là effective constraints; `decision_context.requested_constraints` giữ profile gốc. Selection TTL=min(base resource TTL, cuối ngày local của observation đủ điều kiện +7 ngày, lấy min trên candidates); không sửa immutable base pin. Job deadline không vượt selection TTL.
- Shared `ReadyInput.asset_ids` là resource catalog order, **không thay nó bằng candidate** vì `ArtifactCatalog.load()` đang kiểm tra immutable pin equality. Custom result order lấy từ `SelectionContext.candidate_asset_ids`; legacy vẫn lấy `inputs.asset_ids`.
- `SelectionProof`: `input_hash`, `candidate_hash`, `snapshot_hash`, `panel_hash`, `selection_policy_id`, `applied_selection` (equity-k5-v1 hoặc all-candidates-v1), `decision_session`, `selection_price_end_date`, `active_asset_ids`, `selected_equity_ids`, `rejected_equity_ids`, `selection_hash`, `effective_constraints_hash`. `selection_hash` hash policy/candidate/panel cut và kết quả; loại job UUID, owner, wall-clock khỏi hash này để cùng pin cho cùng selection. `input_hash` riêng vẫn ràng proof vào command. Không chỉ tự hash output do worker khai báo.
- `SelectionReadiness`: `readiness_kind='user-selection-v1'`, `portfolio_version`, `revision_id`, `candidate_hash`, `can_submit`, per-strategy `can_submit/reason_code`, per-asset observations/availability/quality, `regime/regime_input_hash`, `selection_valid_until`, `inputs: ReadyInput|null`. Không trả K5 trước job. `can_submit` không cam kết sẽ có valid views hoặc optimizer SUCCEEDED; legacy response không có readiness_kind và dùng parser cũ.
- `AssetCatalogItem`: `asset_id`, `kind`, `display_name`, `unit`, `currency`, `catalog_version`, `data_status`, nullable `latest_observation_date/eligible_observation_date/available_at/age_days/checked_at`, `ml_status` và nullable approved model/hash. Data status UNKNOWN/MISSING/QUARANTINED/FRESH/STALE; ML status UNKNOWN/NOT_COVERED/REVIEW_PENDING/COVERED. Timestamp/coverage chỉ hiện khi có bằng chứng. Catalog GET envelope có `catalog_version`, `selection_enabled`, `assets`; helper supported_assets trả assets tĩnh.
- Reason codes: `INSUFFICIENT_ASSETS`, `RISK_PROFILE_REQUIRED`, `DEFENSIVE_ASSET_REQUIRED`, `CONSTRAINTS_INFEASIBLE`, `ASSET_DATA_MISSING`, `ASSET_DATA_STALE`, `VFF_STALE`, `GOLD_STALE`, `HISTORY_INSUFFICIENT`, `MODEL_REVIEW_PENDING`, `MODEL_COVERAGE_MISSING`, `MODEL_EPOCH_MISMATCH`, `NO_VALID_ML_VIEWS`, `INPUT_INVALID`. Không trả filesystem/secret trong human API.
- API mới: `GET /api/v1/assets/catalog`; `GET/POST /api/v1/portfolios/{id}/asset-selections` (POST revision cần If-Match + Idempotency-Key); onboarding thêm `asset_ids` mutually exclusive với legacy `universe_id`. GET portfolio thêm nullable selection metadata. Custom recommend cần If-Match, legacy request không đổi.
- Quant internal: `GET /internal/v1/assets/catalog`, `POST /internal/v1/inputs/selection-ready`, `POST /internal/v1/inputs/verify-selection` (portfolio service scope `quant:resolve`, không human token trực tiếp). Verify-selection nhận exact base pin/context/proof và recompute deterministic selection từ resource, trả valid/invalid không raw data. Human custom readiness trả union versioned; legacy response shape giữ tương thích.
- Pure helpers: `canonical_candidates(ids)->list[str]`, `check_candidate_feasibility(ids,constraints,strategy)->None|reason`, `select_candidate_equities(prices,ordered_equity_ids,k=5)->list[str]`, `selection_proof(panel,candidates,active,policy)->SelectionProof`, `prepare_selection(resource,candidates,strategy,now)->SelectionReadiness`, `resolve_selection(resource,context,strategy,now)->numerical+SelectionProof+inference`.

## Lộ trình và phụ thuộc

| Chặng | Tasks | Checkpoint |
| --- | --- | --- |
| A. Catalog và lựa chọn lưu được |0–3,5–6,14| Catalog vẫn hiện khi stale; owner tạo/sửa candidate; legacy còn nguyên |
| B. Dữ liệu, model và pipeline |4,7–12| Prepared source theo asset; bundle v5 duyệt; K5 chỉ trong worker; fail-closed |
| C. Kết quả và rollout |13,15–16| Consumer/pins/history, browser thật, broker, restart, preservation receipts |

Không bật UI gửi custom job trước Task13. Có thể review riêng chặng A nhưng không gọi đó là BL_ML custom hoàn thành.

### Task0: Chụp trạng thái và chuẩn bị bảo toàn

**Files:** Read `infra/local/compose.yaml`, `docs/software/PHASE1_LOCAL_SERVING.md`, `scripts/local_auth.py`; create `scripts/verify_user_selection_preservation.py`; outputs token-free tại `.generated/user-selection/`.

**Interfaces:** `capture(directory)->receipt`, `verify(receipt)->None`; receipt lưu model/snapshot/proposal/accepted-target hashes, account fixture hash, volume identities và representative old command hashes, không lưu token/password.

- [ ] Kiểm tra disk/Docker/Compose bằng `df -h .`, `docker system df`, `docker compose --env-file infra/local/.generated/.env -f infra/local/compose.yaml -p portfolio-auth-demo config --quiet`; không in expanded config. Tính thêm chỗ cho DB backup+image; không build/backup khi dưới floor5GiB. Chỉ reclaim scoped unused cache, không volume/image đang dùng.
- [ ] Viết `test_preservation_receipt_detects_hash_change`: receipt phát hiện thay đổi response/hash; chạy test fail trước rồi viết helper nhỏ dùng Auth hiện có. Chụp `.generated` account hash và artifact hashes trước mọi mutation.
- [ ] Backup DB liên quan và metadata/artifacts theo allowlist ngoài active files, xác nhận backup đọc được; không đổi credentials, không reset/migrate ngầm. Ghi checksum và rollback reader-compatible.
- [ ] Verify receipt read-only, ghi stack actual status. Không tạo lại proposal cũ để thay kiểm tra persistence.

**Dependencies:** None. **Done:** Có receipt/backup hợp lệ và đủ chỗ; dữ liệu cũ chưa đổi.

### Task1: Wire contracts và hash tương thích

**Files:** Create `packages/contracts/src/portfolio_contracts/selection.py`; modify `packages/contracts/src/portfolio_contracts/__init__.py`; test `tests/software/test_selection_contracts.py`; schema export ở16.

**Interfaces:** Các type/reason/API fields ở Hợp đồng chung. Thêm nullable `selection_context`; không thay version/core behavior của payload legacy.

- [ ] Viết `test_legacy_command_hash_is_unchanged` và `test_candidate_hash_is_canonical`: absent optional field cho command/request cũ cho đúng byte/canonical hash đã capture ở0; selected permutation chuẩn hóa về cùng IDs/hash; unknown/duplicate/demo/cross-order hash bị từ chối rõ.
- [ ] Run `.venv-software/bin/python -m pytest tests/software/test_selection_contracts.py -q`, xác nhận RED.
- [ ] Implement strict types và branch hash chỉ có field khi custom; không đổi `None` thành field mới trong legacy hash. Input hash bao gồm revision, candidate, regime và policy pins.
- [ ] Run focused test + `tests/software/test_workflow.py`; chỉ qua khi legacy queued payload vẫn parse/verify được.

**Dependencies:**0. **Done:** Producers/consumers có một hợp đồng, chưa emit event mới.

### Task2: Catalog thực độc lập readiness

**Files:** Create `packages/portfolio-core/src/portfolio_core/assets.py`, `services/quant-serving/src/quant_service/asset_catalog.py`; modify Quant `main.py`; test `tests/software/test_asset_catalog.py`.

**Interfaces:** `supported_assets()->list[AssetCatalogItem]`; registry version ghim32mã/canonical order, kinds/unit/provider identity, VFF quỹ trái phiếu, GOLD SJC. Internal GET trả catalog kể cả thiếu/hết hạn resource.

- [ ] Viết `test_catalog_survives_missing_expired_and_stale_bundles`: đủ32mã real, không DEMO; bundle expired/missing/VFFstale vẫn có catalog; không chứng nhận freshness từ registry tĩnh và không lộ path/secret.
- [ ] Run focused RED; implement static supported registry khớp frozen seed và enrich status chỉ từ nguồn đã xác minh. Dependency lỗi trả trạng thái UNKNOWN, không trả danh sách rỗng giả.
- [ ] Run focused GREEN + legacy `test_p0_readiness.py`; legacy `/inputs/universes` semantics không bị sửa.

**Dependencies:**1. **Done:** Catalog dùng được mà không có valid proposal bundle.

### Task3: Refresh theo nguồn cần dùng và snapshot coverage riêng

**Files:** Create Market `selected_refresh.py`, `selected_snapshots.py`; reuse `phase1_sources.py`, `refresh_provider.py`, `quality.py`; modify `api.py` cho snapshot family3; test `tests/software/test_selected_sources.py`.

**Interfaces:** `refresh_selected(asset_ids,cutoff,store)->per_asset_receipts`; `build_selected_snapshot(session,asset_ids,calendar,as_of)->snapshot_v3`. Source metadata artifact được hash và pin trong QualityReport/RegisteredDataset spec hiện có, không cần Market DB migration.

- [ ] Viết `test_vff_failure_does_not_abort_stock_refresh`: VFF HTTP lỗi/quarantined nhưng FPT cập nhật được; metadata VFF product21/provider time và GOLD carry khớp adapter; sai source/hash không ghi revision. Test finite37equity gaps như baseline; gap mới không được fill giả.
- [ ] Run focused RED; triển khai CLI/operator với canonical registry, bounded requests, common cutoff, quality per-asset transaction và immutable raw/metadata refs. Giữ nguyên full refresh32atomic cũ.
- [ ] Snapshot3 ghi từng asset AVAILABLE/MISSING/QUARANTINED, revision IDs/observation hashes/metadata refs và calendar; missing asset không được biểu diễn là observation hợp lệ. Không dùng READY overall để khẳng định mọi asset fresh.
- [ ] Run focused GREEN + Market/refresh regression. Kiểm tra DATE bind trên PostgreSQL thật trước rollout, không chỉ SQLite.

**Dependencies:**1–2. **Done:** Nguồn không được chọn không tạo single point of failure cho dữ liệu khác.

### Task4: Prepared panel custom và availability theo candidate

**Files:** Create Quant `selection_panel.py`; modify `snapshot_publisher.py` để emit resource bundle2; test `tests/software/test_selection_panel.py`.

**Interfaces:** `build_selection_resource(directory,snapshot,observations)->ArtifactRef`; `load_selection_resource(directory,ref)->SelectionPanel`; `panel.project(candidate_ids,now)->CandidateInputs` (prices/returns/features/availability/regime+hash). Không có K5 ở project/preflight.

- [ ] Viết `test_selected_projection_checks_only_required_assets` và `test_age_seven_passes_eight_fails`: full32vs selected projections, latest completed session trước/sau18:00, weekend/holiday, VFF5buffer/late metadata, GOLDnext-day, age7pass/age8fail, first-seen thực, old lateNAV không đè mới; unselected VFF missing không chặn stock projection.
- [ ] Run RED; tạo numeric NPZ+JSON manifest có checksum, `allow_pickle=False`, không object dtype, tối đa10.000rows x32assets và32MiB uncompressed; kiểm tra zip metadata trước giải nén. Missing cells có validity mask; selected invalid/nonfinite/history thiếu bị chặn.
- [ ] Giữ expanding EMA start14/01/2020 cho equity model, price unit nghìn VND trong feature; snapshot/source convention hashes đầy đủ. Regime tính candidate returns20/120/60 version mới, covariance/OptionB20returns; không tạo dependency VFF ngoài candidate.
- [ ] Run GREEN + `test_phase1_full_panel.py`, `test_snapshot_inputs.py`, `test_phase1_serving.py`; fixtures baseline cũ không thay.

**Dependencies:**1–3. **Done:** Có immutable input cho worker chọn K5, không cần network/crawl khi execute.

### Task5: Selection revisions không sửa lịch sử

**Files:** Modify Portfolio `models.py`; create migration `services/portfolio/migrations/versions/b70211d9e301_asset_selection_revisions.py` (`revision=b70211d9e301`, current `down_revision=a410c7e9d201`; verify head trước execution, không tạo Alembic branch ngầm), `selection.py`; test `tests/software/test_selection_revisions.py`.

**Interfaces:** Table append-only `PortfolioAssetSelection` có unique(portfolio_id,portfolio_version), actor/idempotency/body_hash; Portfolio thêm nullable `asset_selection_revision_id`. NULL là legacy; custom universe marker `USER_SELECTED` không thay IDs cũ.

- [ ] Viết `test_selection_migration_preserves_existing_rows_and_hashes`: upgrade DB có old portfolios/targets/jobs: giữ row count, result JSON và canonical hashes; không fabricated revision cho legacy. Test owner isolation, duplicate edit, race version và revision pointer đúng portfolio.
- [ ] Run RED; implement additive table/nullable pointer và `create_selection_revision(session,portfolio,ids,key,expected_version)`. Snapshot old candidate metadata vào mỗi job; không cập nhật result lịch sử.
- [ ] Run GREEN + migration upgrade PostgreSQL/restart; không chạy downgrade destructive trên stack hiện tại.

**Dependencies:**0–1. **Done:** Lưu và sửa candidate bền vững, đọc legacy không đổi.

### Task6: Portfolio CRUD và feasibility theo policy

**Files:** Modify Portfolio `api.py`, `policy.py`, `selection.py`, `runtime.py`; test `tests/software/test_selected_portfolio.py`.

**Interfaces:** onboarding hỗ trợ asset_ids mutually exclusive universe_id; selection history/edit theo Hợp đồng chung. Thêm Portfolio `GET /api/v1/assets/catalog` và runtime proxy đến internal Quant catalog từ Task2. `check_candidate_feasibility(ids,constraints,strategy)` trả reason riêng cho count/group feasibility; new portfolio dùng policy version custom, legacy policy giữ nguyên.

- [ ] Viết `test_one_asset_selection_can_be_saved_but_not_optimized` và `test_missing_defensive_does_not_relax_policy`: lưu1asset, stale asset được lưu; reject0/unknown/duplicate IDs; cap0,5 hai assets chỉ50/50 nếu khả thi; thiếu VFF block optimize nhưng không block lưu; GOLD không defensive; không tự thêm asset/cash hoặc nới profile. Crafted direct POST/PATCH không bypass server policy; custom portfolio chưa có assessment hợp lệ chỉ lưu, optimize RISK_PROFILE_REQUIRED.
- [ ] Run RED; implement canonical IDs và server-owned risk policy. BL feasibility dùng min(equity_count,5)+selected alternatives, EW/MVO dùng toàn candidate. Không cần chạy selector để biết số lượng.
- [ ] Giữ floor0,15/cap nondef0,70 -> defensive>=0,30; kiểm tra aggregate defensive capacity. Không tạo stock-only mandate trong task này.
- [ ] Run GREEN + onboarding/reassessment/ownership regression; GET legacy giữ response cũ, metadata mới vắng mặt phải nullable/optional tương thích.

**Dependencies:**1,2,5. **Done:** User lưu được lựa chọn; thông báo policy rõ trước gửi job.

### Task7: K5 trên tập biến thiên và active allocation

**Files:** Create core `selection.py`; modify `allocator.py` và wrapper nội bộ `phase1_full.py` chỉ nếu cần chia sẻ helper; tests `packages/portfolio-core/tests/test_user_selection.py`, legacy `test_phase1_full.py`.

**Interfaces:** `select_candidate_equities(prices,ordered_equity_ids,k=5)->list[str]`, `selection_proof(...)`; numerical field `active_policy_version='user-selection-active-v1'` opt-in generic candidate subset. Không có field này -> validator full32/active7 cũ.

- [ ] Viết `test_k5_uses_only_candidate_equities` tham số0/1/5/6/30equities, canonical tie order, subset không có mã ngoài candidate, anti-lookahead prices[:t], same pins same K5; K5 không chạy khi<=5. Test covariance slice trước repair, group feasibility, sum100%, inactive exact0, threshold1% vẫn khả thi.
- [ ] Run core test RED; tổng quát hóa Welford1-correlation/combinations k=min(5,n) cho branch mới, giữ wrapper30/frozen fixtures cũ. K5 chỉ chọn cổ phiếu, không chọn GOLD/VFF vào cụm.
- [ ] Core validate exact candidate/active order, strategy cardinality và groups; BL prior equal-weight trên active, map lại candidate. EW/MVO không tự bật K5.
- [ ] Run `.venv-software/bin/python -m pytest packages/portfolio-core/tests -q`; không sửa golden cũ để làm test pass.

**Dependencies:**1–2. **Done:** Pure selection/allocation dùng được cho candidate tùy chọn và legacy parity còn nguyên.

### Task8: Model asset-wise v5 và native parity

**Files:** Create Quant `asset_ensemble.py`, ML `selected_train.py`; modify Quant `ml.py`; test `tests/software/test_selected_model.py`.

**Interfaces:** Manifest5 có catalog/coverage, fit_epoch, training snapshot/equity hashes, per-asset scaler/5members/best_iteration/split/cutoff/source hashes, coverage omissions. `train_asset_candidate(directory,equity_panel,fit_epoch)->ArtifactRef` không phụ thuộc user K5/GOLD/VFF.

- [ ] Viết `test_complete_equity_coverage_exports_150_native_members` và `test_partial_coverage_is_explicit`: 30complete ->150UBJ; partialdata ->5*covered với explicit missing reasons; nonecomplete ->trainingfail; XGB/runtime/hash bug không bị nuốt. Test eightfeatures/seeds42–46, exclusive train_end=t−5/latestlabelt−6, chronological purge, actualtrained_at và native predictions đúng best_iteration so frozen wrapper.
- [ ] Run RED; tái dùng pure feature/training primitives hiện có, không copy cảtrainer v4 nếu chỉ khác outerasset loop. Coverage thiếu không được mang booster epoch cũ gắn nhãn mới.
- [ ] Native schema phân biệt model5 khỏi v4selected5; manifest không chứa selection user. Runtime chỉ đọc manifest+UBJ, views lọc active equites, confidence/OptionB daily như nguồn và phải có>=1valid MLview.
- [ ] Run GREEN + v1–v4 serving/training regressions; không thay native files/model IDs cũ.

**Dependencies:**1–4. **Done:** Offline v5 có coverage minh bạch và parity.

### Task9: Queue/reviewer/resolver cho v5

**Files:** Modify ML `contracts.py`, `queue.py`, `worker.py`, `main.py`; modify Quant `model_worker.py`; tests `test_model_operations.py` + `test_selected_model_operations.py`.

**Interfaces:** TrainingRequest thêm `model_family: Literal['phase1-asset-ensemble-v5'] | None = None`; absent/None ->old trainer dispatch/hash, loại field này khỏi serialized legacy request. Native approval/materialization nhận5, validator coverage theo manifest5; keep job/phase1-model/approved path contract.

- [ ] Viết `test_v5_family_preserves_legacy_enqueue_hash` và `test_v5_review_and_nested_resolver`: idempotent reenqueue cũ bytehash không đổi; v5sameintent cùngjob/model; lease/fence/recovery không overwritepartial stages. Review thiếu If-Match/reason/idempotency bị từ chối; CANDIDATE khôngresolve; tamperednative/hash/missingmember block.
- [ ] Run RED; thêm dispatch v5 bằng explicitfamily, không đổi schema2snapshot->v4 implicit cũ. Nâng native loops/approval canonicalcomparison và metadata `covered_asset_ids`, coverage reasons/fit epoch, ensemble count.
- [ ] Test full approved path bốn cấp qua `CredentialModelResolver`, không chỉ internalMLendpoint; malformed/othermodel/nestedpath vẫn reject.
- [ ] Run GREEN + entire modeloperations regressions; model APPROVED chỉ qua review API hiện có.

**Dependencies:**8. **Done:** Artifact v5 được duyệt và resolve theo cùng security/recovery guarantees.

### Task10: Publication resource và catalog adapter mới

**Files:** Modify Quant `publication_api.py`, `snapshot_publisher.py`, `artifacts.py`; create `selection_catalog.py`; test `tests/software/test_selection_publication.py`.

**Interfaces:** universe resource `VN_USER_SELECTION`, snapshot3, optional approvedmodel5, preparedbundle2. `SelectionCatalog.latest()->ReadyInput`, `load_resource(pin)->SelectionPanel`; base pin giữ resource asset order. No per-user publication/model creation.

- [ ] Viết `test_custom_publication_is_per_asset_and_hash_pinned`: reserved-family mismatches, approved/unapproved/hash/sourceIDs/units, dynamic coverage, idempotentpublication/catalogcrashrecovery. VFFunavailable vẫn publish catalog/perassetdiag cho stocks; không quảng cáo tất cảstrategies READY.
- [ ] Run RED; thêm family dispatch opt-in; parser legacybundle1/snapshot1–2/model1–4 unchanged. Publisher validate source/hash/timing và native hashes trước ghi; canonical SourceID contract khớp Market adapter.
- [ ] Custom không cho max_age_days!=7; TTL vẫn min24h/sourcebound, dù nguồn fresh thì expired publication vẫn cần renew có kiểm tra. Catalog có thể hiện mã khi TTL hết nhưng không cho job dùng bundle hết hạn.
- [ ] Run GREEN + publicationjobs/API/old readiness tests. Current user dropdown legacy không được âm thầm đổi lựa chọn.

**Dependencies:**2–4,9. **Done:** Một shared immutable resource có thể phục vụ nhiều candidate sets.

### Task11: Selected readiness và job admission

**Files:** Create Quant `selection_ready.py`; modify Quant `main.py`, Portfolio `runtime.py`, `api.py`; tests `tests/software/test_selection_readiness.py`.

**Interfaces:** `prepare_selection(resource,candidates,strategy,now)->SelectionReadiness`; internal POST scoped route; Portfolio custom readiness union (catalog proxy đã có ở Task6). Preflight tính candidate regime/hash, không K5; API ghim effective constraints từ regime và policy.

- [ ] Viết `test_preflight_does_not_run_k5` và `test_selected_stale_vff_blocks_explicit_fallback`: catalog visible khi allstale/nomodel; selectedmissing/stale/HISTORY/modelcoverage/group reason; unselectedVFFkhôngchặn nhưng selectedVFFstale chặn cảEWfallback. Model readiness đúngepoch/approved/native; tối thiểu valid calculation inputs trước enqueue.
- [ ] Run RED; preflight projection chỉ có requiredcandidate/calendar; strictscope/owner ởBFF/Portfolio vàquant:resolve nội bộ. Optional fields serializelegacy nhưcũ.
- [ ] Customrecommend cần If-Match+Idempotency-Key; input hash ghim SelectionContext vàconstraints. Preflight response không cóselectedK5; `can_submit` là admission, NO_VALID_ML_VIEWS có thể failworker. Repeatoldkey/originalversion trảoldjob, oldkey/newversion409.
- [ ] Run GREEN + fallback/ownership/versionrace; no Job/Outbox khi preflight fail, HTTP409 với reason/data age vàmax7 public an toàn.

**Dependencies:**5–7,9–10. **Done:** Có thể nhận custom job an toàn, feature gate vẫn false.

### Task12: K5 thực thi trong Quant worker

**Files:** Create Quant `selection.py`; modify `workflow.py`, `selection_catalog.py`, `selection_ready.py`; test `tests/software/test_selection_worker.py`.

**Interfaces:** `resolve_selection(resource,context,strategy,now)` rechecks exactpin/regime/effectiveconstraints, selectsK5, infersnative, returnsnumerical/proof/inference. Legacy workflow không có SelectionContext ->path cũ.

- [ ] Viết `test_worker_selects_five_equities_inside_job` và `test_queued_selection_expires_at_day_eight`: 8equity+GOLD/VFF active7; 3equity+VFF active4; samecommand/retry cùngselection hash; candidatepermutationcanonical; noK5 beforeworker; selecteddata crosses day7->8 whilequeued failVFF_STALE, notEW. Hai job khác UUID nhưng cùng input selection pins phải có cùng selection_hash; command input_hash vẫn khác theo job.
- [ ] Run RED; load readonlyresource/model, validate timestamps/hash/order/coverage, computeK5fromcandidatehistoryexcludingdecisionclose, deriveactivecov/prior/views, attach SelectionProof beforeallocate. Không outbounddatafetch/training trongworker.
- [ ] Forcustom requirevalidMLview>=1; model/no-view/data/core failures map explicitcodes; no fallbackafterselection. EW/MVO allcandidate byexplicitstrategy; fallback chỉ pre-admission khi user đã chọn vàEW cũngpassfresh/policy.
- [ ] Cài internal verify-selection đọc pinned resource và tính lại K5/proof bằng cùng pure helper, không chạy inference/optimization hay mutate trạng thái. Test proof sai nhưng tự hash đúng vẫn bị từ chối; caller không có quant:resolve bị403.
- [ ] Run GREEN + Quantinbox/outbox/deadline/idempotence regressions; returncandidate-orderweights with exact0inactive andfull provenance.

**Dependencies:**7–11. **Done:** Broker worker chạy K5/BL_ML trên immutable input.

### Task13: Consumer proof và history không đổi

**Files:** Modify Portfolio `workflow.py`, `api.py`, `runtime.py`; test `tests/software/test_selection_result.py`.

**Interfaces:** `validate_result(result,command)` custombranch usescandidateorder andchecked SelectionProof; legacybranch staysunchanged. CustomRecommendation exposes candidate revision/active/K5/pins fromsavedresult, notcurrentPortfolio.

- [ ] Viết `test_consumer_recomputes_selection_proof` và `test_selection_ttl_controls_acceptance`: forgedselectionhash/subset/order/modelpin/positiveinactive/foreignasset rejected; constraints sum100%/caps/groups checked independently. Test selection/profile edited midflight, historical response unchanged, staleacceptblocked, ownerisolation. Selection TTL ngắn hơn resource TTL phải được tôn trọng; result/accept sang ngày8 không thành một đề xuất còn hạn. Accepted target cũ không tự đổi khi edit candidate.
- [ ] Run RED; `QuantResolver.verify_selection(pin,context,proof,deadline)` gọi scoped `/internal/v1/inputs/verify-selection`, timeout tối đa15s và không vượt remaining deadline (không dùng mặc định3s cho K5 nặng). Do not compare only worker-claimed output hash. Re-evaluate cut/timestamp đã ghim, không dùng latest snapshot hoặc đổi candidate; kiểm tra selection TTL tại consumer/accept. No cross-service DB reads.
- [ ] Verify API tạm unavailable: rollback transaction/Inbox và để broker retry có hạn, không lưu proposal sai hoặc ACK làm mất result. Test recovery tạo đúng một recommendation.
- [ ] Persistproposal+outbox/inbox inexistingtransactions, idempotentduplicate result; no migration result JSON/backfill oldfields. GET/accept usesproposal's ownpins andcurrentversionchecks.
- [ ] Run GREEN + target/reassessment/workflow/tracing tests andoldreceipt exactcompare.

**Dependencies:**5–6,12. **Done:** Untrusted result cannot escape userallowedset or overwritehistory.

### Task14: Catalog chọn mã và onboarding

**Files:** Create Web `src/components/asset-picker.tsx`; modify `risk-wizard.tsx`, `home.tsx`, `src/lib/portfolio-types.ts`, `src/server/bff.ts`; tests `tests/asset-picker.test.tsx`, `tests/risk-universe.test.tsx`, BFFtests.

**Interfaces:** Investor BFF catalogGET ->Portfolio, selectionGET/POST ownerprotected; mutuallyexclusive onboardingbodyassetids/universe; oldroutes stillwork. Shared TS types mirrorTask1.

- [ ] Read `apps/web/AGENTS.md` andinstalledNextdocs beforecode. Viết `test_catalog_picker_saves_candidates_without_k5`: catalogall32 withsearch/kindlabels, stalevisible/nofabricatedfresh, checkboxselection1–32, messageallows0%, noK5oncreation, noautoVFF, keyboard/a11y, requestCSRF/If-Match/idempotency guards.
- [ ] Run `cd apps/web && npm test -- tests/asset-picker.test.tsx tests/risk-universe.test.tsx` RED; implement usingexistingcomponents/designsystem, no newlibrary.
- [ ] Letuser save evenwhenreadinessfalse; confirmation showscandidate/riskpolicy withselectedassetcount. Legacyportfolio creation/load remainsavailable independently whilegateoff.
- [ ] Run GREEN + BFFunit/typecheck; featuregateAPI/UI consistent, disabledgate cannot be bypassed by craftedrequest.

**Dependencies:**2,5–6. **Done:** Empty readiness no longer erases catalog orprevents savingselection. Chặng A chỉ bật catalog/lưu lựa chọn; action gửi optimize chưa được bật cho tới khi Task13 đạt.

### Task15: Proposal, selection edit và model coverage UI

**Files:** Modify Web `portfolio-workspace.tsx`, `allocation-view.tsx`, `portfolio-lifecycle.tsx`, `model-operations.tsx`, `lib/workspace-state.ts`, `lib/p1-types.ts`; reuse typesTask14; focused tests andnew `tests/selected-proposal.test.tsx`.

**Interfaces:** proposal renderssaved candidate/proof; editPOSTincludesIf-Match/idempotency; readinesscan_submit/reasonsperstrategy; reviewer displayscoveragecount/omissions/150target/fitactualdate.

- [ ] Viết `test_proposal_renders_saved_candidates_and_zero_weights`: selectedbutzero weights label, K5onlyproposal/jobnotonboarding, activevspositive distinct, stale7daywarning noEWbypass, assetedit invalidatesconfirmation, historicalold32/3assetrows unchanged evencurrentselectiondiffers.
- [ ] Run focusedRED; implementclearplainlabels K5reason/inactive0 andsource/modelpolicyversions; nocustompositiveaction untilbackendgateon.
- [ ] Chat/assistantproposal paths continueusingPortfolioadmission; testdelegatedrequests cannotpickoutsidecandidate/bypassfreshness orrisk. Legacychatpayload withnofield remainscompatible.
- [ ] Run Websuite `npm test`, `npm run typecheck`, `npm run build`; noNextmajorupgrade/dependencychange.

**Dependencies:**9,13–14. **Done:** User understands assetchoices vscomputedallocation; history remainsfaithful.

### Task16: Contracts, rollout và nghiệm thu stack thật

**Files:** Modify `scripts/export_software_contracts.py`, generatedOpenAPI/events, `infra/local/compose.yaml` forservergateonly, `docs/software/PHASE1_LOCAL_SERVING.md`; create `apps/web/tests/browser/user-selection.e2e.ts`, `scripts/verify_user_selection_preservation.py` finalchecks. Updatebrowser safe-reporter fornewtests; scripts notnewtestclient/secrets.

**Interfaces:** Allpublic schemasexported; token-freereceipts record candidate/revision/selection/model/snapshot/policy/bundle/job/proposal/inputhash; gateoff legacy stilloperates.

- [ ] Exportcontracts `.venv-software/bin/python scripts/export_software_contracts.py`; reviewadditivechanges. Run `.venv-software/bin/python -m pytest tests/software packages/portfolio-core/tests -q`, appropriateRuff/diffchecks, `cd apps/web && npm test && npm run typecheck && npm run build`; recordactualcounts/skips, notprior682/140 asnewproof.
- [ ] Aftercapacity/backupgate, runadditivemigration; canonicalComposebuild relevantmarket/ML/Quant/Portfolio/Web usingtheir`*-migrate` buildservices. Deploycapablereaders/workers beforeproducer; verifyhealth andlegacyreceipt beforegateon. Preservecredentials/namedvolumes andnooverlaypatch.
- [ ] Refreshselectedsources withactualclock, snapshot3, fitv5, realreviewer reason/If-Match/Idempotency-Key, artifactready, operatorpublicationresource. Recordcoverage; only claim150memberswhen30complete.
- [ ] Realbrowsercases: catalogshownwhileVFFstale; createoneasset withreadinessblock; stockonly saved butdefensivereason; 3equity+VFF and8equity+GOLD+VFF validdata cases; selectingstaleVFF blocks andunselectedstaleassetdoesnotgloballyblockeligiblemandate; GOLD+VFF EW/MVO onlywhenvalid, BLMLdisabledwithoutMLviews.
- [ ] Positivegate mustuseactualeligibledata<=7, explicitBL_ML, EWunchecked, RabbitMQjobSUCCEEDED, candidate-onlyoutput, K5correct, inactiveexact0,total100%, group/positioncapandmodel/snapshot/epoch/selectionpinscorrect. No clock/policy/data manipulation; ifnoeligibleVFFfresh caseexists, markpositiveBLOCKED withNAVdate/availability/checkpoint evidence, notpassedbysyntheticfixture.
- [ ] Midjobedit/riskchange/retry/concurrentowner/redelivery browser/APIcases; resultsticksoldrevision andnewrequestusesnewversion. Verify noforeignowner access andnoacceptoldversion/expiredproposal.
- [ ] RestartDB/broker/Auth/Redis/API/workers, waithealth; reopenexactnewproposal andexactoldproposal, compareallpins/result/target/account/volume/artifactreceipts. Anewproposal isnotpersistenceproof. Ifpositiveblocked, verifynegativegate/model/resourcepersist separatelyandkeepfullproposalpersistenceunchecked.
- [ ] Finalreviewdiff/security/prose; keepdisabledgateuntilcriteriaachieved. To rollback: gateoffnewwrites, draincustomjobs withnewworker/readers, leaveadditiveDBandhistory; noforcedowngrade/volume reset. Commitonlynewscopewhenrequested, neverstagewholeexistingdirtytree.

**Dependencies:**0–15. **Done:** Realpositive+negative+persistenceevidence, orpreciselymarkedexternaldatablocker; legacyreceiptstillmatches.

## Acceptance matrix

| Case | Expected |
| --- | --- |
| Không có publication còn hạn | Catalog 32 mã vẫn hiện; lưu lựa chọn được; optimize có lý do bị chặn |
| 1 candidate, profile hợp lệ | Lưu được; optimize trả INSUFFICIENT_ASSETS |
| 2 assets, cap0,5, nhóm khả thi | 50/50; không chạy K5 |
| Thiếu defensive dưới policy custom mixed | Lưu được; không tạo job, DEFENSIVE_ASSET_REQUIRED; không tự thêm mã |
| 8 cổ phiếu + GOLD + VFF | Worker chọn 5 cổ phiếu; active7; output10 trọng số theo candidate, 3 inactive bằng0 |
| 3 cổ phiếu + VFF | Active4, không K5, thỏa ràng buộc |
| GOLD + VFF | EW/MVO nếu fresh/khả thi; không báo BL_ML khả dụng khi thiếu view ML |
| VFF trong candidate đã8ngày | Chặn mọi strategy kể cả EW dự phòng; hiển thị ngày/tuổi/ngưỡng7 |
| VFF stale ngoài candidate | Catalog vẫn hiện; không dùng dữ liệu VFF; nếu policy cần phòng thủ thì báo lý do policy riêng |
| Model thiếu coverage ngoài candidate | Không chặn portfolio đã được phủ; không quảng cáo ML hỗ trợ mã thiếu |
| Sai hash/order/epoch/first-seen | Từ chối, không báo READY hoặc lưu proposal thành công sai |
| Sửa candidate khi job đang chạy | Pin của job/proposal gốc giữ nguyên; guard accept còn hiệu lực; job mới dùng revision mới |
| Retry/restart/broker gửi lặp | Cùng input hash/proof; đúng một proposal lưu cho mỗi job |
| Schema/event/receipt legacy | Hash gốc và result đọc được; field NULL mới không làm lệch hash |

## Review trước khi thực thi

User đã đồng ý hai mặc định trước khi triển khai: policy custom mixed vẫn cần VFF (mandate chỉ cổ phiếu ngoài MVP), và nhánh custom dùng phiên hoàn tất mới nhất thay checkpoint5 nhưng vẫn giữ buffer VFF5. Các mặc định này không bảo đảm READY liên tục với ngưỡng7ngày. Nếu muốn tối ưu danh mục chỉ cổ phiếu hoặc bỏ buffer VFF cho live, phải cập nhật spec, policy version và tests trước Task6/4; không tự đổi trong code.

Task0–16 đã thực thi; migration additive, build canonical, model review, broker/browser/persistence và bảo toàn đã đạt theo báo cáo ngày12/11/2026. Đề xuất thực thi **native, tuần tự theo dependency** để giảm xung đột trong workspace dirty; chỉ dùng nhiều agent khi user hoặc chỉ dẫn áp dụng cho phép. Checklist tổng và lịch sử nhiệm vụ cũ được giữ ở `tasks/todo.md`.
