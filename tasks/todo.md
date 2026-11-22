# Công việc tích hợp Phase 1 đầy đủ

## Kế hoạch sản phẩm 22/11/2026 — một đề xuất của hệ thống

Các bước chi tiết và tiêu chí bật nằm trong [kế hoạch HYBRID](../docs/superpowers/plans/2026-11-22-system-allocation-hybrid.md).

- [x] Khóa công thức, fixture và chạy đối chiếu Phase 1 trên lịch sử đã ghim.
- [x] Tính hai nhánh trong một job Quant, ghim policy và kiểm tra công thức ở Portfolio.
- [x] Chuyển Web và Chat sang một luồng tạo đề xuất và lý do readiness chung.
- [x] Hiển thị EW/MVO làm đối chứng chỉ đọc, giữ lịch sử và dữ liệu cũ.
- [x] Kiểm chứng broker/browser trước và sau đổi hồ sơ và qua recreate các service ứng dụng.
- [ ] Mở luồng HYBRID thường trực sau khi bảng hệ số đạt cổng định lượng trên tập đánh giá độc lập. Pilot 22/11 giữ `paused` vì Tăng trưởng vượt ngưỡng biến động.

**Checklist active từ 12/11/2026:** Task0–16 trong mục "Kế hoạch tiếp nối"
ở cuối tệp, theo [plan mới](../docs/superpowers/plans/2026-11-12-user-selected-assets.md).
Các checkbox đợt full baseline bên dưới được giữ nguyên để ghi nhận những
nghiệm thu đã đạt và còn blocked; không tự xóa hoặc đánh dấu hoàn thành.

Thiết kế và bằng chứng nguồn ở [plan.md](plan.md). Đây là danh sách triển khai
đề xuất. Mỗi bước được hoàn thành bằng kiểm thử và kiểm tra luồng tương ứng.

- [x] Audit nguồn ngày 11/11/2026. Đã tải phản hồi, đối chiếu NAV, GOLD và thời gian.

## 1. Adapter GOLD và VFF

Phụ thuộc audit. Phạm vi dự kiến 4–5 tệp trong market_service gồm adapter mới,
refresh_provider.py, refresh.py, refresh_api.py và test nguồn.

- [x] Chuẩn hóa GOLD SJC bán ra TPHCM về VND/lượng, giữ carry và identity nguồn.
- [x] VFF resolve rõ product ID 21, giữ NAV gốc, navDate, metadata và ngày báo cáo.
- [x] Lưu raw/hash/request/received_at. Lỗi, duplicate conflict, sai đơn vị hoặc
  identity phải được cách ly trước khi ghi revision.

Kiểm chứng bằng fixtures raw của audit và test mới
`tests/software/test_phase1_full_sources.py`. Kiểm tra live read-only có pacing,
timeout và giới hạn kích thước. Refresh vẫn cần bao phủ đủ 30 cổ phiếu dù
schedule hiện giới hạn 20 mã, qua batch có common snapshot và kiểm tra đủ bộ.

## 2. Snapshot và panel availability hỗn hợp

Phụ thuộc 1. Phạm vi snapshots.py, models.py, migration Market mới,
snapshot_inputs.py và test mixed panel.

- [x] Snapshot version mới giữ observation bất đồng bộ và provenance mỗi ô panel.
- [x] Join theo thông tin đủ điều kiện, đúng lag GOLD/VFF, không backfill.
- [x] Tách first-seen thực tế khỏi policy time lịch sử. Kiểm tra tuổi dữ liệu
  nguồn và observation đủ điều kiện, trả lỗi stale cụ thể theo ngưỡng hiện hành.

Kiểm chứng `test_phase1_full_panel.py` bằng ledger baseline, ngày 11/11 có
VFF đủ điều kiện 03/11 cách 8 ngày, metadata đến muộn, carry, holiday và revision.
Checkpoint gồm nguồn thật + snapshot hash + quality PASS cho đủ 32 tài sản.

## 3. Selection K5 và lịch phiên

Phụ thuộc 2. Phạm vi module selection thuần mới trong portfolio-core,
ML worker, models/migration ML cho epoch và test selector.

- [x] Chọn đúng năm mã, thứ tự và tie-break trên cùng fixture với frozen source.
- [x] Reselect 20 phiên, refit 10 phiên, checkpoint 5 phiên, giữ mốc khởi tạo
  và threshold đủ dữ liệu như replay baseline.
- [x] Persist selection/epoch/hash. Retry và hai worker đồng thời trả cùng
  selection cho cùng snapshot, cutoff và policy.

Kiểm chứng `packages/portfolio-core/tests/test_phase1_full.py`, đối chiếu distance matrix,
selection cost, input endpoint và con trỏ trước/sau restart. Có fixture K5
thay đổi giữa hai lần fit, dự báo trên phần giao modelled assets và active equities.

## 4. Core tối ưu active subset

Phụ thuộc 3. Phạm vi allocator.py, contract numerical của Quant,
workflow Quant và hai test core.

- [x] Validate active assets là subset gồm đúng K5 + GOLD + VFF trong full order 32.
- [x] Tính covariance repair, prior và posterior trên submatrix bảy tài sản,
  prior equal-weight 1/7, map trọng số về 32 với inactive bằng 0.
- [x] Tái sử dụng constraint engine, kiểm tra threshold 1% và khả thi sau xử lý.

Kiểm chứng golden fixtures với frozen ranking_sub_optimize, gồm covariance
gần suy biến do NAV carry, sai thứ tự và cap bất khả thi. Chạy
`.venv-software/bin/python -m pytest packages/portfolio-core/tests -q`.

## 5. Fit và xuất ensemble v4

Phụ thuộc 2, 3. Phạm vi module manifest v4 mới, ml.py, model_worker.py,
script fit/export mới và test parity.

- [x] Mỗi mã K5 có 5 UBJ, seeds 42–46, scaler riêng, tám feature và best_iteration.
- [x] Giữ endpoint train_end=t−5 exclusive, label end không vượt cutoff,
  purge trước validation, ghi actual fit time và input/source/booster hashes.
- [x] Tách modelled assets 5, active assets 7 và output order 32. Kiểm tra
  feature, từng booster, confidence và Option B trên cùng fixtures.

Kiểm chứng `test_phase1_full_training.py`, tolerance feature 1e-10 và forecast
native khớp float32 với wrapper tham chiếu trên cùng runtime.

## 6. Queue và reviewer

Phụ thuộc 5. Phạm vi contracts.py, worker.py, main.py của ML,
import_phase1.py và test registry v4.

- [x] Enqueue fit theo selection/fit epoch, giữ lease và idempotency hiện hành.
- [x] CANDIDATE chỉ thành APPROVED qua review có reason, If-Match và Idempotency-Key.
- [x] Artifact sẵn sàng sau review, v4 resolver kiểm tra đủ native hashes và pins.

Kiểm chứng API/worker bằng `test_model_operations.py` và test v4, gồm candidate
tampered, concurrent import/fit, quyết định lặp, recovery và các model schema cũ.

## 7. Publication, inference và regime

Phụ thuộc 4, 6. Phạm vi snapshot_publisher.py, publication_worker.py,
ml.py, module policy/regime thuần mới và test serving v4.

- [x] Cùng hàm compatibility được dùng tại publisher và worker cho snapshot,
  selection, model, order, timing, freshness và epoch.
- [x] Tái tạo Option B, dampener và defensive views theo full-panel regime,
  đặt P đúng cột. Thiếu view hợp lệ trả lỗi theo hợp đồng BL_ML hiện hành.
- [x] Chặn model chưa duyệt, sai hash và cặp selection/fit epoch lệch schedule.
  Cho phép model của epoch fit trước trên phần giao K5 đúng như source,
  đến hạn fit mới thì kiểm tra artifact đã duyệt của epoch mới.

Kiểm chứng `test_phase1_full_training.py` bằng normal/stress/crisis và giữ
fixtures v1/v2/v3. Checkpoint là full bundle đủ dữ liệu và kiểm tra numerical parity.

## 8. Portfolio và risk policy

Phụ thuộc 4, 7. Phạm vi policy.py, workflow.py, api.py, shared contracts
và test full portfolio.

- [x] Ghim full order, active assets, selection/model/panel hashes và epoch vào job.
- [x] Pin effective constraints. Đề xuất dùng VFF defensive, floor 0,15,
  non-defensive cap 0,70 gồm GOLD, position cap 0,50, risk aversion lấy mức
  chặt hơn giữa investor và baseline regime.
- [x] Consumer xác minh inactive weights bằng 0 và đủ constraints trước khi lưu.

Kiểm chứng `test_phase1_full_portfolio.py`, gồm risk revision trong khi job chạy,
retry cùng request, owner isolation và lịch sử proposal trước khi K5 thay đổi.

## 9. Browser và BFF

Phụ thuộc 8. Phạm vi risk-wizard.tsx, allocation-view.tsx,
model-operations.tsx, p1-types.ts và test browser mới.

- [x] Hiển thị universe đầy đủ, K5 hiện hành, GOLD/VFF, ngày dữ liệu và availability.
- [x] Reviewer thấy selection, label boundaries, modelled assets và fit epoch.
- [x] Investor xem effective constraints và gửi BL_ML với EW dự phòng bỏ chọn.

Kiểm chứng test Web liên quan, typecheck, production build và browser thật.
Hiển thị rõ tài sản ngoài K5 có tỷ trọng 0 và nguyên nhân nếu full universe bị stale.

## 10. Nghiệm thu nguồn thật và persistence

Phụ thuộc 1–9. Phạm vi browser test full mới, smoke receipt và tài liệu vận hành.

- [x] Nguồn thật đủ 32 tài sản, snapshot READY/PASS, ML queue SUCCEEDED,
  25 UBJ, reviewer APPROVED/artifact_ready và publication SUCCEEDED trên browser.
- [x] Browser báo VFF_STALE theo ngưỡng 7 ngày; BL_ML bị khóa với cả hai trạng
  thái EW dự phòng. API trực tiếp trả 409; PostgreSQL xác nhận không có full job.
- [x] Restart PostgreSQL/RabbitMQ/Redis/Auth và API/worker; kiểm tra lại cùng
  model, snapshot, publication, selection/epoch, full portfolio stale và đề xuất cũ.
- [ ] Positive BL_ML full qua RabbitMQ SUCCEEDED với EW dự phòng bỏ chọn,
  tổng 100%, 25 inactive bằng 0 và đúng mọi giới hạn: bị chặn bởi VFF stale.
- [ ] Mở lại chính đề xuất full thành công sau restart: chưa có đề xuất full
  để kiểm tra, phụ thuộc dòng positive ở trên. Không dùng đề xuất ba mã cũ thay thế.

Chạy các bộ Python/software và core, Web test/typecheck/build, browser gate full,
đối chiếu outbox/inbox cùng input hash và verify receipt sau restart.

## Các quyết định còn cần chốt trước rollout hàng ngày

- [x] Giữ freshness 7 ngày theo yêu cầu; readiness bị chặn khi observation
  đủ điều kiện quá hạn. Không nới policy theo lịch quỹ trong đợt này.
- [x] Triển khai cách kết hợp risk profile investor với risk layer baseline như
  đề xuất ở bước 8, và thông tin xác nhận policy mới trên browser.

Bằng chứng offline: Python/software+core 682 passed, 5 opt-in PostgreSQL tests
skipped; Web 140 passed, typecheck và canonical production build đạt. Các test
v4 đối chiếu chính xác 25 dự báo float32/best_iteration với wrapper đóng băng.
Nguồn thật: snapshot `19f49fac-c911-41e2-9fae-7c8e1e59bf62`, 54.197 observations,
32 PASS reports và 41 raw source hashes đã kiểm tra trên PostgreSQL.

Nghiệm thu positive BL_ML full vẫn cần observation VFF đủ mới theo cùng policy.
Không đánh dấu bước 10 hoàn thành chỉ vì publication/model/snapshot đã lưu.
Chi tiết vận hành và receipt xem `docs/software/PHASE1_LOCAL_SERVING.md`.

## Kế hoạch tiếp nối 12/11/2026 — tập tài sản user cho phép cân nhắc

Thiết kế và quyết định đề xuất:
[spec](../docs/superpowers/specs/2026-11-12-user-selected-assets-design.md).
Các bước, file, interface, test RED/GREEN và tiêu chí nghiệm thu:
[plan](../docs/superpowers/plans/2026-11-12-user-selected-assets.md).

Giữ nguyên các mục full BL_ML còn blocked ở trên. Không dùng thiết kế mới
để chứng nhận retrospectively rằng đợt cũ đã có positive proposal.

- [x] Task0: Capacity, backup, receipt bảo toàn account/volume/artifact/old proposal.
- [x] Task1: Selection contracts và hash/idempotent replay legacy.
- [x] Task2: Catalog 32 mã real độc lập với readiness, VFF ghi đúng quỹ trái phiếu.
- [x] Task3: Refresh/source metadata theo asset và snapshot3 coverage riêng.
- [x] Task4: Prepared panel custom, latest completed, availability/freshness 7 ngày.
- [x] Task5: Selection revisions append-only, migration additive không backfill cũ.
- [x] Task6: Portfolio create/edit 1–32 mã, owner/version/idempotency, policy feasibility.
- [x] Task7: Generic K5 equity-only và active allocation; wrapper baseline giữ parity.
- [x] Task8: Model asset-wise v5, mục tiêu 150 UBJ, coverage thiếu minh bạch, native parity.
- [x] Task9: Queue, reviewer, approved resolver/recovery v5, không đổi model1–4.
- [x] Task10: Publication/resource bundle2 và selection catalog adapter.
- [x] Task11: Selected readiness và admission pinning, K5 chưa chạy ở bước này.
- [x] Task12: Worker chạy K5/inference/BL_ML; freshness recheck và proof deterministic.
- [x] Task13: Consumer kiểm tra proof/constraints/zero inactive và history immutable.
- [x] Task14: Asset picker/onboarding, catalog visible ngay cả khi stale.
- [x] Task15: Proposal/edit/reviewer UI, coverage và candidate/K5/positive phân biệt rõ.
- [x] Task16: Contract exports, canonical Compose, browser/broker/actualdata/restart gate.

### Checkpoint A — lưu lựa chọn độc lập dữ liệu sẵn sàng

- [x] Catalog luôn hiện mã hỗ trợ; lưu 1 asset hoặc asset stale được nhưng lý do chặn optimize rõ.
- [x] Không show K5 lúc tạo, không tự thêm VFF/cash, không sửa profile để tạo nghiệm.
- [x] Legacy GET/result/command hashes/ownership còn tương thích.

### Checkpoint B — pipeline và model tùy chọn

- [x] Nguồn ngoài candidate không làm job khác lỗi; nguồn trong candidate stale bị chặn.
- [x] Manifest v5 được duyệt thật, coverage/epoch/native hash đúng; không train trong optimize.
- [x] K5 ở worker, input lặp có cùng selection; output không có asset ngoài candidate.

### Checkpoint C — nghiệm thu và bảo toàn

- [x] Python/core/Web/typecheck/build đạt với counts thực tế; baseline fixtures không bị sửa.
- [x] Dữ liệu thật fresh<=7: BL_ML không EW, RabbitMQ SUCCEEDED, weights100%, constraints/pins đúng.
- [x] Dữ liệu thật stale: UI+API chặn kể cả EW dự phòng, VFF/date/age/max7 rõ, không nhận job.
- [x] Restart rồi mở đúng proposal mới và cũ; account/volume/model/snapshot/target receipts khớp.
- [x] Nguồn thật đủ điều kiện ngày12/11: positive và persistence VERIFIED; không đổi clock/nới policy. Snapshot11/11 thật được dùng riêng cho negative VFF_STALE.

### Mặc định đã xác nhận và thực thi

- [x] Review mặc định custom mixed vẫn cần VFF: danh mục chỉ cổ phiếu được lưu nhưng chưa optimize; mandate mới ngoài MVP.
- [x] Review nhánh custom dùng latest completed session, vẫn buffer VFF5; legacy replay checkpoint5 giữ nguyên.
- [x] User đã đồng ý hai mặc định và yêu cầu triển khai Task0–16; thực thi/kiểm chứng local đã hoàn tất, không commit thay đổi có sẵn.


Nghiệm thu 12/11/2026: Python/core766passed6opt-inskipped, DATE PostgreSQL
thật1passed, Web145passed, typecheck/canonicalbuild/Ruff/diff đạt. Browser
lifecycle, riskchange giữa QUEUED và persistence sau restart23service đạt.
16/16 command gốc giữ hash; SQL/file/account/volume/accepted-target receipt PASS.
Fresh-context review không còn Critical/Important findings.
Chi tiết IDs/lệnh/log: [báo cáo](../docs/software/PHASE1_LOCAL_SERVING.md#user-chọn-tài-sản--nghiệm-thu-ngày-12112026)
và [acceptance.json](../outputs/step1/user-selected-local-acceptance-20261112/acceptance.json).
Selection của snapshot hiện tại hết hạn00:00 ngày13/11 GMT+7 theo đúng freshness7.
