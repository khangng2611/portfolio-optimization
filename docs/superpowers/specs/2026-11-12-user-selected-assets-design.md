# Danh mục do user chọn mã — thiết kế để review

Ngày: 12/11/2026, Asia/Ho_Chi_Minh. Trạng thái: **đã được user duyệt và triển khai Task0–16 ngày12/11/2026**.

## Bổ sung được user duyệt ngày 18/11/2026: policy NAV live

Snapshot selected mới dùng `user-selection-live-nav-v2`. NAV VFF đã được Market
thu thập, kiểm tra identity/giá/source hash và quality PASS được dùng cho tính
toán live sau khi snapshot được xác minh. Không thêm buffer 5 phiên cho nhánh
này; tuổi vẫn tính từ ngày NAV đến ngày sử dụng tại Việt Nam, tối đa 7 ngày.
Chỉ lấy NAV có ngày định giá không vượt phiên hoàn tất mới nhất (18:00).

Đường NAV cho thống kê live được căn theo ngày định giá; mọi revision đầu vào
phải đã được thu thập trước thời điểm sử dụng. Snapshot verification time và
first-seen thật vẫn được giữ; không coi `createdAt` của provider là thời điểm
công bố đã xác minh. History tải hôm nay không chứng nhận tính khả dụng ở quá
khứ, `historical_publication_verified=false` vẫn giữ nguyên.

Version đi theo snapshot hash, bundle provenance và selection context trong
command; worker từ chối policy không khớp panel đã pin. Snapshot/bundle/result
cũ không bị sửa. `user-selection-data-v1` và baseline schema 2 tiếp tục giữ
buffer 5 phiên. Những đoạn mô tả buffer cho custom bên dưới là quyết định v1
ngày 12/11, được bổ sung này thay thế đối với snapshot live mới.

## Phần user đã xác nhận

- Tick một mã nghĩa là cho phép hệ thống cân nhắc; không bắt buộc có tỷ trọng dương.
- Catalog gồm các tài sản thực sự được stack hỗ trợ; K5 nằm trong job tối ưu, không yêu cầu user chọn K5 khi tạo danh mục.
- Freshness giữ **7 ngày lịch**. Giữ dữ liệu, tài khoản, volume, model, snapshot, job và đề xuất hiện có.
- User đã đồng ý hai mặc định và ủy quyền triển khai/kiểm chứng Task0–16; báo cáo thực tế trong `docs/software/PHASE1_LOCAL_SERVING.md`.

Các lựa chọn bên dưới đã được duyệt; phiên hoàn tất mới nhất và policy custom mixed yêu cầu VFF giữ nguyên khi triển khai.

## Ba khái niệm riêng

1. **Catalog hỗ trợ:** 30 cổ phiếu trong registry Phase 1, GOLD SJC và VFF — quỹ trái phiếu. Không gọi VFF là trái phiếu riêng lẻ; loại DEMO và mã chưa được xác minh khỏi catalog thực.
2. **Candidate set của portfolio:** danh sách user tick, được chuẩn hóa theo thứ tự catalog. Lưu bền vững và có revision; mọi tài sản ngoài danh sách này không được nhận trọng số.
3. **Active set của job:** BL_ML giữ tất cả cổ phiếu nếu số cổ phiếu <=5; nếu >5, worker chạy K-Medoids K=5 trên chính tập cổ phiếu candidate. GOLD/VFF được giữ trong active set chỉ khi user chọn. Optimizer có thể tiếp tục cho trọng số 0 trong active set.

EW/MVO dùng toàn bộ candidate set. Không áp K5 ngầm lên hai phương pháp này; khi so sánh phải ghi rõ active set khác nhau. BL trong giao diện hiện tại là `BL_ML`; không thêm một strategy BL mới trong MVP.

Ví dụ: 8 cổ phiếu + GOLD + VFF -> active tối đa 7; 3 cổ phiếu + VFF -> active 4; GOLD + VFF -> EW/MVO có thể khả dụng, BL_ML không khả dụng nếu không có view ML hợp lệ.

## Kích thước và policy rủi ro

- Cho tạo/lưu candidate set từ **1 đến 32 mã** hợp lệ; không bắt buộc dữ liệu đang READY để lưu lựa chọn. Không thêm một state machine draft riêng: khả năng gửi tối ưu là trạng thái tính từ readiness.
- Không gửi optimize nếu có ít hơn 2 tài sản. Điều kiện cần `n_active * max_position_weight >= 1`; còn phải kiểm tra khả thi theo nhóm. Với cap 50%, hai tài sản chỉ có nghiệm 50/50 nếu các giới hạn khác cũng cho phép.
- Mặc định an toàn cho portfolio custom: `custom-mixed-risk-v1`, giữ cap vị thế <=0,50; floor phòng thủ >=0,15; non-defensive <=0,70; risk aversion hiệu lực là max(profile, 1,5 normal/stress hoặc 5 crisis).
- VFF là tài sản defensive của policy này; GOLD vẫn non-defensive. Với ngân sách 100%, VFF phải đạt ít nhất 30%. Khi thiếu VFF hoặc sức chứa nhóm phòng thủ không đủ, cho lưu portfolio nhưng chặn optimize bằng `DEFENSIVE_ASSET_REQUIRED` hoặc `CONSTRAINTS_INFEASIBLE`.
- Không tự thêm VFF/cash, không đổi profile, không bỏ floor/cap và không coi GOLD là phòng thủ để tìm nghiệm. Danh mục chỉ cổ phiếu cần một mandate được duyệt riêng; **không nằm trong MVP này**.
- Policy mới được gắn bằng version trong selection/risk revision, không suy ra chỉ từ tên universe hay việc user có bỏ tick VFF hay không. Policy/constraint của portfolio cũ không được đổi.

Đây là điểm quan trọng cần review: tick cổ phiếu thuần vẫn lưu được, nhưng mặc định mixed nghiêm ngặt sẽ chưa cho tối ưu khi thiếu phòng thủ. Kế hoạch không tự suy diễn rằng user đã đồng ý nới policy.

## Freshness và thời gian

- Tuổi bằng `local_decision_date - observation_date` ở Asia/Ho_Chi_Minh; <=7 là hợp lệ, >7 bị chặn. Ngày NAV không được thay bằng ngày tải để làm mới tuổi.
- Kiểm tra cả source quality, observation đủ điều kiện và first-seen/ingestion <= thời điểm sử dụng. Không đổi clock, backdate publication hoặc gia hạn bundle vượt dữ liệu hợp lệ.
- Giữ nguyên nhánh baseline hiện có: checkpoint 5 phiên, buffer VFF 5 phiên, GOLD ngày kế tiếp, lịch reselect/refit và manifest 1–4.
- Đề xuất cho nhánh custom `user-selection-data-v1`: quyết định tại **phiên VNINDEX hoàn tất mới nhất**, cutoff 18:00; không khóa vào checkpoint 5 phiên của replay. Buffer VFF vẫn **5 phiên quan sát** và metadata muộn hơn; GOLD vẫn ngày kế tiếp. Không chuyển sang policy first-seen-only trong đợt này.
- Dùng policy lịch sử đã khai báo cho warm-up; không gán first-seen lùi về quá khứ. Giữ `historical_publication_verified=false` và provenance theo ô.
- K5 chạy theo từng job trên history đã ghim, loại giá phiên quyết định khỏi selection/features. Covariance/Option B dùng 20 returns kết thúc tại phiên quyết định như hợp đồng Phase 1.
- Regime custom dùng toàn bộ candidate set, không dùng tài sản ngoài candidate để tránh VFF không được chọn chặn một job khác. Giữ công thức 20/120/60, nhưng gắn version `candidate-regime-v1`; đây là phương pháp sản phẩm mới, không tuyên bố tái lập hiệu suất baseline full-32.
- Freshness áp lên **mọi candidate được dùng cho selection/tính toán** và calendar cần thiết. Không loại ngầm candidate stale trước khi chọn K5. Tài sản không được chọn và không là dependency không chặn job.
- Publication/catalog không đảm bảo READY hàng ngày: VFF được chọn vẫn có thể stale hợp lệ do buffer. Positive gate chỉ đạt khi nguồn thật và observation đủ điều kiện cùng thỏa 7 ngày.

## Catalog không phụ thuộc publication còn hạn

Catalog luôn có đầy đủ mã hỗ trợ, ngay cả khi chưa có snapshot/model hoặc tất cả bundle hết hạn. Mỗi mã có loại, đơn vị, tên hiển thị, ngày observation/source đủ điều kiện, trạng thái quality/freshness và coverage ML; lỗi dependency có trạng thái `UNKNOWN`, không biến thành danh sách rỗng.

Chỉ trạng thái có timestamp đã kiểm chứng mới được gọi là fresh; catalog registry tĩnh không được tự chứng nhận freshness. Không lộ token, raw response hoặc filesystem path trong API investor.

Readiness theo portfolio/strategy được tính từ candidate revision và snapshot/model cụ thể. `can_submit=true` nghĩa là đủ điều kiện gửi tính toán; worker còn phải kiểm tra lại freshness, selection, views và khả thi. Không hứa SUCCEEDED trước khi worker chạy K5.

## Dữ liệu và model phục vụ tập tùy chọn

Snapshot full schema 2 đang đòi đủ 32 tài sản. Nhánh custom cần snapshot nguồn version 3 với quality/coverage riêng từng mã: một nguồn VFF lỗi không ngăn cập nhật cổ phiếu khác. Tái dùng PriceRevision, QualityReport và immutable source artifacts; không sửa full refresh atomic cũ.

Source metadata theo ngày được lưu vào immutable artifact và pin trong QualityReport của ingestion, để snapshot mới lấy lại product ID/provider record time/carry mà không cần đọc HTTP trong serving. Snapshot READY chỉ khẳng định manifest hợp lệ; trạng thái AVAILABLE/MISSING/QUARANTINED từng mã phải tách rõ.

Publisher tạo prepared bundle version 2 dùng chung, family `user-selection-market-v1`, universe resource `VN_USER_SELECTION`. Bundle giữ panel lịch sử, calendar, availability/revision ledger và optional manifest model. Candidate-specific projection diễn ra khi preflight/job; không tạo một catalog/bộ model cho từng user.

Panel dùng NPZ numeric với `allow_pickle=False`, checksum, shape và giới hạn giải nén; không pickle. Tài sản/ô chưa có dữ liệu phải có mask riêng; chỉ cho dùng selected projection có history hợp lệ. Runtime không crawl nguồn hoặc fit model.

Manifest model version 5 là bundle asset-wise cho cổ phiếu, không ghim K5 của một user:

- Tám feature, scaler từng mã, 5 seed 42–46, UBJ và best_iteration giữ như Phase 1.
- Mục tiêu 30 cổ phiếu x5 =150 UBJ khi đủ nguồn. Có thể đăng ký coverage một phần với danh sách thiếu và lý do rõ; không tuyên bố 150 booster nếu thiếu mã. Ít nhất một ensemble hoàn chỉnh mới được tạo CANDIDATE.
- Fit epoch chung theo lịch 10 phiên hiện có; train endpoint/label end/purge không đổi. Chỉ đọc equity inputs, không đòi GOLD/VFF để fit equity model.
- Model coverage không được trộn từ các manifest cũ không tương thích. Preflight yêu cầu bundle đã duyệt, đúng epoch và phủ các equity candidate của MVP; runtime chỉ infer equity active. GOLD/VFF không bị đòi booster giả.
- Lỗi data cục bộ có coverage reason; lỗi trainer/runtime/hash làm fail training thay vì bị nuốt thành missing coverage.
- Giữ training queue, lease/fence, receipt, reviewer reason/If-Match/Idempotency-Key, materialization `artifact_ready` và native hashes. Không fit theo từng yêu cầu investor.
- BL_ML custom cần ít nhất một view ML hợp lệ sau selection/threshold; sau đó mới áp dampener/defensive views. Nếu thiếu thì fail rõ, không đổi tên kết quả EW thành BL_ML.

## Persist, job và kiểm tra kết quả

- Thêm selection revision append-only và con trỏ nullable trên Portfolio; NULL nghĩa là legacy. Không backfill/migrate ngầm portfolio cũ.
- Job ghim candidate list/hash/revision, policy versions, snapshot/bundle/model hashes, requested/effective constraints và regime input hash. Chưa có K5 tại thời điểm nhận job.
- Selection context có `decision_at`, `decision_session` và `valid_until` riêng: min(TTL resource, cuối ngày local của observation được chọn +7 ngày). Không sửa base ReadyInput để tạo pin giả. Deadline tính toán không vượt mốc này; UI/accept dùng hạn của selection, không chỉ TTL24h của resource.
- Worker revalidate các pin, chạy K5 và lưu selection receipt/hash trong kết quả cùng active/rejected IDs, rồi optimize active submatrix. Map output về candidate order, mã ngoài active bằng 0; không có output cho mã ngoài candidate.
- Consumer kiểm tra input hash, candidate order, selection proof deterministic, model coverage/hash, zero inactive và constraints trước khi lưu Recommendation. Không tin một `selection_id` tùy ý do worker gửi.
- Verify proof dùng pinned resource và cut/timestamp của command, không lấy snapshot mới nhất. Việc tính kịp ngày7 không cho phép accept proposal khi observation đã sang ngày8. Cập nhật lựa chọn không tự thay accepted target; chỉ acceptance proposal mới thay mục tiêu theo luồng hiện có.
- Edit candidate dùng If-Match + Idempotency-Key và tăng Portfolio.version. Job đang chạy giữ revision cũ; không sửa job/proposal lịch sử. Accept đề xuất cũ bị chặn theo quy tắc version/expiry hiện có.
- Thêm field optional phải giữ nguyên hash serialization và idempotent replay của command/request cũ; không thêm `null` vào canonical hash legacy.

## Giao diện

Tạo danh mục: tìm/lọc theo cổ phiếu/vàng/quỹ trái phiếu, tick mã, hiện số lượng và thông báo "Hệ thống có thể phân bổ 0% vào tài sản đã chọn". Không hiển thị kết quả K5 ở đây. Mã stale vẫn nhìn thấy và có lý do; trạng thái này không chặn lưu lựa chọn.

Trước khi gửi: hiển thị candidate, policy, số active tối đa, model coverage và lý do không thể gửi. Không hứa mọi mã được tick sẽ có tỷ trọng dương. Submit có confirmation fingerprint và If-Match.

Đề xuất: hiển thị candidate, K5 thực tế, GOLD/VFF nếu được chọn, active/positive-weight khác nhau, 0% cho inactive, ngày dữ liệu và provenance. Không áp candidate hiện tại để vẽ lại đề xuất lịch sử. Chat/BFF không được bypass selection/profile/readiness.

## Bảo toàn và rollout

- Compose project `portfolio-auth-demo`; không down -v, reset realm/Auth, bootstrap lại credentials, xóa volume hoặc overwrite artifact/catalog history.
- Chỉ migration additive; rollout readers/workers hỗ trợ contract mới trước, rồi API producer/UI sau. Giữ nhánh parse/execute legacy, kể cả job đã queued trước rollout.
- Feature gate server `USER_SELECTED_ASSETS_ENABLED`, default false; chỉ bật sau test/migration/review. Khi rollback: khóa tạo custom mới, giữ reader/history và drain job mới; không hạ schema hoặc hạ worker trong khi còn custom job.
- Trước build/backup cần đủ đĩa; lượt kiểm tra đầu tiên còn khoảng 118 MiB; lần kiểm tra sau khoảng 1,1 GiB, vẫn dưới ngưỡng thực thi. Không thực hiện build hoặc backup lớn ở trạng thái này. Chỉ dọn cache đã xác định không dùng, không đụng volume/data; chốt capacity dựa trên dung lượng backup+image cần thiết, floor tối thiểu5 GiB cho đợt thực thi.
- Baseline bảo toàn đối chiếu cả response đề xuất cũ, accepted target, accounts, volume list, snapshot/model/artifact hashes; GET/login trước/sau vẫn hoạt động.

## Ngoài phạm vi

Trái phiếu riêng lẻ, cash giả lập, mã ngoài catalog32, bắt buộc giữ mã/min-weight theo mã, nới freshness, stock-only mandate mới, bỏ buffer VFF, sửa replay baseline, tái lập hiệu suất backtest, tối ưu chi phí giao dịch/lô lệnh và triển khai production.

## Hướng đã cân nhắc

- Giữ universe publication làm lựa chọn UI: ít code nhưng tiếp tục giấu catalog khi stale và không đáp ứng chọn mã.
- Tạo snapshot/model/publication riêng cho từng user: audit đơn giản nhưng nhân bản training/review và làm job chậm.
- **Đề xuất:** catalog độc lập, selection revisions, prepared source dùng chung, model asset-wise, K5 trong worker. Tái dùng hạ tầng hiện có; đổi hợp đồng sản phẩm có version và kiểm thử riêng.

Kế hoạch chi tiết: [Implementation plan](../plans/2026-11-12-user-selected-assets.md). Các positive acceptance còn blocked của đợt full cũ được giữ nguyên trong `tasks/todo.md`, không được đổi thành passed bởi thiết kế mới.
