# Kế hoạch tích hợp K5 động, GOLD và VFF vào stack local

Bản ứng viên Chat ngày 23/11/2026 đã có phản hồi trạng thái, truy xuất và kiểm định tiếng Việt. Cổng phát hành còn mở vì độ đúng nguồn và căn cứ trên tập khóa chưa đạt. Các vòng tiếp theo đối chiếu riêng từng câu, đoạn được tìm, câu trả lời và lượt gọi OpenAI. [Bộ kiểm định tiến cứu cuối](../docs/software/RAG_QUALITY_V5_2026_11_23.md) · [Kiểm tra OpenAI thật](../docs/software/RAG_OPENAI_QUALITY_2026_11_23.md). Xem [rà soát, baseline và các bước cải thiện RAG](../docs/superpowers/plans/2026-11-23-rag-quality-and-status.md).

**Kế hoạch sản phẩm ngày 22/11/2026:** investor nhận một đề xuất HYBRID có tỷ lệ phối theo trạng thái thị trường và hồ sơ. EW/MVO nằm trong mục so sánh thu gọn, chỉ để đọc. Xem [thiết kế và kế hoạch triển khai](../docs/superpowers/plans/2026-11-22-system-allocation-hybrid.md). Các mốc tích hợp dữ liệu bên dưới là nền tảng và lịch sử của kế hoạch mới.

**Kế hoạch active từ 12/11/2026:** triển khai danh mục user chọn candidate
assets theo tài liệu mới được dẫn ngay dưới. Phần full baseline cũ bên dưới
được giữ làm lịch sử, không phải chỉ dẫn để chạy lại toàn bộ đợt cũ.

## Kế hoạch tiếp nối ngày 12/11/2026: user chọn candidate assets

User đã chốt tick = cho phép hệ thống cân nhắc, không bắt buộc có tỷ trọng
dương. Kế hoạch mới tách catalog khỏi readiness, lưu selection revision và
chạy K5 trong job BL_ML; freshness vẫn 7 ngày và giữ nguyên dữ liệu/lịch sử.

- Thiết kế đã duyệt: [user-selected-assets-design](../docs/superpowers/specs/2026-11-12-user-selected-assets-design.md).
- Kế hoạch triển khai Task0–16: [user-selected-assets](../docs/superpowers/plans/2026-11-12-user-selected-assets.md).
- Checklist tiếp nối nằm cuối `tasks/todo.md`. Không thay các checkbox chưa
  đạt của nghiệm thu full cũ thành passed; các phần bên dưới giữ làm bằng
  chứng lịch sử. Task0–16 đã triển khai và nghiệm thu local ngày12/11/2026;
  xem báo cáo mới trong `docs/software/PHASE1_LOCAL_SERVING.md`.

Ngày kiểm tra 11/11/2026, giờ Việt Nam. Mục tiêu là phục vụ BL_ML theo
pipeline ranking_absolute của baseline
`availability-observed-contract-20261012T233110`, qua Market, ML registry,
reviewer, Quant, broker và browser trên Compose project `portfolio-auth-demo`.

## Kết quả kiểm tra nguồn thực tế

Phản hồi gốc, request, thời điểm nhận, HTTP status và SHA-256 nằm trong
[manifest audit](../outputs/step1/source-audit-20261111T230659/manifest.json).
Các phép đối chiếu và kết quả nằm trong
[analyze.py](../outputs/step1/source-audit-20261111T230659/analyze.py) và
[analysis.json](../outputs/step1/source-audit-20261111T230659/analysis.json).

Market API local hiện có DEMO_STOCK, FPT, MWG và VCB. Snapshot giá thật hiện
chứa FPT, MWG, VCB đến 09/11/2026. GOLD và VFF cần được đưa qua ingestion
và quality trước khi xuất hiện trong full snapshot. Kết quả đọc API nằm trong
[market-inventory.json](../outputs/step1/source-audit-20261111T230659/market-inventory.json).

| Nguồn | Độ phủ đã kiểm tra | Freshness tại 11/11/2026 | Thời điểm khả dụng |
| --- | --- | --- | --- |
| GOLD canonical của baseline | 2.343 ngày, 01/12/2019–30/04/2026 | Tệp cũ cách 195 ngày | Baseline gán observation lúc 23:00 và cho dùng từ 00:00 ngày kế tiếp |
| GiaVang.TV đang hoạt động | Tải 9 trang tháng. 61/61 giá bán của tháng 01/2020 và 04/2026 khớp baseline. Phần mở rộng 01/05–11/11/2026 có đủ 195 ngày, gồm 72 dòng carry được nhà cung cấp đánh dấu | Giá ngày 11/11 là 140.000.000 VND/lượng, cập nhật trên trang lúc 23:00 | Theo policy baseline, giá 11/11 đủ điều kiện từ 00:00 ngày 12/11. Serving còn cần đã nhận được dữ liệu |
| FMarket VFF, product ID 21 | 1.020 dòng raw từ 01/04/2013. Từ 2020 có 606 ngày NAV duy nhất, kết thúc 10/11/2026. 595/595 ngày trùng canonical khớp NAV chính xác, thêm 11 ngày, không có xung đột giá trên ngày trùng trong kỳ từ 2020 | NAV mới nhất 27.249,21 VND/CCQ, cách 1 ngày. Canonical trong repo kết thúc 01/10 và cách 41 ngày | Metadata mới nhất lúc 16:53:54.847 ngày 10/11, giờ Việt Nam. Có metadata trên 562/606 ngày và thiếu trên 44 ngày. Giờ công bố đầu tiên của toàn bộ lịch sử còn chưa được xác minh |
| Báo cáo VinaCapital | XLSX kỳ kết thúc 09/11, lập ngày 10/11, NAV cuối kỳ 27.249,21 VND/CCQ, khớp FMarket | Báo cáo ngày 10/11 đang tải được | Ngày lập báo cáo được xác minh. Tệp không cung cấp bằng chứng giờ đăng công khai đầu tiên |
| PNJ SJC tại TPHCM | Kiểm tra ba ngày 29/04, 10/11 và 11/11. Giá bán của quote cuối theo timestamp khớp archive cả ba ngày | Quote mới nhất ngày 11/11 lúc 14:41:03, giá bán 140.000.000 VND/lượng | Đây là timestamp quote trong phản hồi tải ngày 11/11. Lịch sử lần đầu xuất bản từng quote còn chưa được xác minh |

Toàn bộ 77 trang tháng cũ được giữ qua hash của canonical. Lượt audit này
tải lại hai tháng trong phần lịch sử cũ và bảy tháng mở rộng. Độ phủ lịch sử
đã tải lại cần được đọc theo phạm vi đó.

FMarket xác minh đúng danh tính VFF, loại BOND, VinaCapital và product ID 21.
Phải dùng NAV gốc VND/CCQ. Crawler fund cũ làm tròn sau khi chia 1.000,
trong khi baseline readiness dùng NAV chưa làm tròn chia 1.000. Tệp VFF
khác trong datasets cần được đối chiếu danh tính trước khi tái sử dụng.

Trang VinaCapital hiện liệt kê giao dịch thứ Ba và thứ Năm. Bản cáo bạch
tháng 08/2026 có quy định đóng sổ 14:40 ngày T−1 và công bố NAV trên website
công ty quản lý quỹ hoặc đại lý phân phối. Quy tắc nhận lệnh và thanh toán
cần được lưu riêng với thời điểm thông tin có thể dùng để tính đề xuất.

FMarket gắn NAV mới nhất với `navDate=10/11`, còn XLSX ghi kỳ định giá đến
09/11 và lập báo cáo ngày 10/11. Adapter lưu cả ngày nguồn, ngày kết thúc
kỳ định giá và ngày lập báo cáo nếu có. Panel tương thích baseline tiếp tục
dùng `navDate` theo policy đã đóng băng. Mọi phép đổi sang ngày định giá
chính thức cần một phiên bản policy và phép đối chiếu riêng.

Nguồn tham chiếu trực tiếp gồm
[archive GOLD](https://giavang.tv/lich-su/2026/11/),
[FMarket NAV API](https://api.fmarket.vn/res/product/get-nav-history),
[trang VFF](https://vinacapital.com/vi/investment-solutions/onshore-funds/vff/),
[báo cáo NAV](https://vinacapital.com/wp-content/uploads/2026/11/20261110_VFF_BC_Ky_Ky-so_20261109.xlsx)
và [bản cáo bạch tháng 08/2026](https://vinacapital.com/wp-content/uploads/2026/08/20260813-VFF-BCB-sua-doi-bo-sung-08.2026.pdf).

Trang HTML VinaCapital trả 403 cho request trực tiếp trong lượt probe.
Firecrawl đọc trang thành công. Hai XLSX và bản cáo bạch tải trực tiếp
đều trả 200. Chi tiết nằm trong manifest và các tệp retrieval của audit.

## Hợp đồng thời gian và freshness

1. Ghim lịch VNINDEX quan sát và cutoff 18:00 Asia/Ho_Chi_Minh. Lưu riêng
   ngày phiên định lượng, thời điểm quyết định thực tế, observation time,
   thời điểm đủ điều kiện theo policy, metadata của nhà cung cấp và
   `first_seen_at/ingested_at`.
2. Equity giữ giá adjusted KBS. GOLD giữ đúng chuỗi SJC bán ra TPHCM của
   archive và cờ carry. VFF giữ product ID 21 và NAV gốc. Các timestamp và
   quy ước đơn vị đi cùng revision và hash nguồn.
3. Panel warm-up/replay dùng đúng policy availability của baseline,
   gồm GOLD ngày kế tiếp và VFF sau năm phiên quan sát ở 18:00, hoặc sau
   timestamp metadata muộn hơn. Ghi `historical_publication_verified=false`.
   Panel phục vụ tại quyết định thực tế chỉ dùng dữ liệu đã nhận được và đã
   đủ điều kiện theo policy. Dữ liệu mới tải không được gán first-seen lùi
   về các cutoff lịch sử.
4. As-of join chọn observation mới nhất đủ điều kiện. Observation cũ đến
   muộn không thay observation mới hơn. Không backfill. Mỗi ô giữ revision,
   ngày observation gốc, policy time, source hash, carry basis và tuổi dữ liệu.
   Giá carry hợp lệ vẫn tạo lợi suất ngày bằng 0 theo baseline.
5. Phân biệt source freshness với tuổi observation được phép dùng. Lượt audit
   có NAV mới ngày 10/11, nhưng tại cutoff 18:00 ngày 11/11, policy năm phiên
   chỉ cho dùng NAV 03/11, cách 8 ngày. Ngưỡng 7 ngày tính theo ngày NAV sẽ
   chặn full universe ở mốc này.

Mặc định triển khai giữ ngưỡng hiện hành 7 ngày và thời hạn bundle hiện hành.
Nếu observation VFF đủ điều kiện vượt ngưỡng, readiness phải trả lý do cụ thể
và BL_ML bị chặn. Yêu cầu sẵn sàng hàng ngày cần quyết định riêng về policy
freshness theo lịch quỹ và độ trễ năm phiên. Mốc này là lựa chọn vận hành cần
chốt trước rollout hàng ngày, không được tự tăng tuổi tối đa để làm test đạt.
Kiểm thử acceptance phải có cả ngày đủ điều kiện trong ngưỡng và ngày vượt
ngưỡng. Snapshot chỉ được công bố sau khi kiểm tra đủ tất cả tài sản.

## Thiết kế tích hợp đề xuất

- Dùng universe mới `VN_PHASE1_FULL`. Ghim đúng danh sách 30 cổ phiếu và
  thứ tự 32 tài sản của assets_1.json trong source_snapshot baseline.
  Đây là universe nghiên cứu cố định đã khai báo.
- Snapshot hỗn hợp giữ raw revisions bất đồng bộ cho 32 tài sản, kèm phiên
  bản panel availability. Kiểm tra coverage theo từng loại tài sản. Equity
  đối chiếu lịch VNINDEX, GOLD giữ calendar/carry của archive, VFF đối chiếu
  lịch NAV và các ngoại lệ ngày nghỉ của nguồn.
- K5 dùng đúng exhaustive K-Medoids, distance 1−correlation, thứ tự xét tổ hợp
  và tie-breaking của baseline. Correlation dùng expanding history đến
  `prices.iloc[:t]`, loại giá của phiên quyết định.
- Reselect mỗi 20 phiên, refit mỗi 10 phiên, checkpoint đề xuất mỗi 5 phiên,
  covariance window 20. Bootstrap con trỏ từ replay schedule và audit đã
  đóng băng, rồi tiến theo lịch phiên. Điều kiện đủ lịch sử cho lần fit đầu
  tiên phải khớp source. Lịch và con trỏ được lưu bền vững theo universe.
- Mỗi lần fit tạo ensemble cho 5 cổ phiếu đang chọn, tương ứng 25 UBJ.
  Giữ tám feature, năm seed 42–46, scaler từng mã, purge nhãn, early stopping
  và best_iteration. Giữ train_end=t−5 với slice exclusive của baseline,
  để nhãn cuối fit dừng ở phiên index t−6.
- Epoch selection và fit được lưu riêng. Source có thể reselect trước lần
  refit tiếp theo, nên model cũ chỉ dự báo phần giao với K5 mới trong khoảng
  đó. Publisher xác minh đúng cặp epoch theo schedule và dùng các view thuộc
  phần giao, rồi áp quy tắc thiếu view hiện hành. Fixture cần có mốc đổi K5
  nằm giữa hai lần fit để giữ đúng hành vi này.
  Ví dụ audit ghi selection ngày 30/11/2020 thay GVR bằng MSN, trong khi model
  fit gần nhất ngày 23/11 vẫn gồm GVR. Bốn mã còn lại có thể phát dự báo.
- Manifest mới v4 tách candidate universe, modelled equities, active assets
  và full output asset order. Ghim selection ID/hash, snapshot/panel hash,
  lịch và epoch, cutoff kinh tế, knowledge cutoff, thời gian fit, metric,
  scaler, booster và source hash. Các schema phục vụ trước đó giữ hợp đồng cũ.
- ML worker tạo CANDIDATE. Reviewer quyết định qua API/UI hiện hành với reason,
  If-Match và Idempotency-Key. Publisher chỉ resolve artifact đã duyệt.
  Đến epoch cần model mới mà chưa có artifact đã duyệt tương thích, readiness
  trả trạng thái chờ review. Các worker phục vụ chỉ đọc manifest và UBJ.
- Bundle giữ full order 32 và `active_asset_ids` gồm K5 + GOLD + VFF.
  Views cổ phiếu được đặt đúng cột tài sản. GOLD/VFF nhận tác động từ posterior,
  constraints và defensive views theo regime. Core trích đúng submatrix bảy
  tài sản cho BL_ML trước covariance repair, prior, posterior và tối ưu, rồi map trọng
  số về 32 tài sản, với 25 cổ phiếu ngoài K5 bằng 0.
- Giữ Option B theo lợi nhuận ngày, confidence, volatility dampener và defensive
  views từ source. Regime dùng chuỗi returns và lát cắt đầy đủ như baseline,
  gồm các tài sản trong panel. Fixture phải kiểm chứng việc này.
- Policy mặc định của full universe dùng VFF là defensive. Giữ floor 0,15,
  cap non-defensive 0,70 và max position 0,50. Theo source, GOLD nằm trong nhóm
  non-defensive, nên VFF thực tế cần ít nhất 0,30 để đủ ngân sách. Risk aversion
  hiệu lực đề xuất là max của hồ sơ investor và mức baseline theo regime,
  với mức baseline 1,5 bình thường và 5,0 khi crisis. Policy và giá trị hiệu lực
  phải được pin trong job và hiển thị khi xác nhận.
- So sánh phép xử lý trọng số nhỏ dưới 1% của baseline với core, giữ tính khả
  thi sau xử lý. Quy tắc sản phẩm hiện hành vẫn chặn BL_ML nếu không có view
  hợp lệ. Research baseline có nhánh dùng empirical mean trong trường hợp
  này, nên trường hợp đó cần được ghi nhận riêng trong kiểm thử tương thích.

Thứ tự công việc và tiêu chí từng phần nằm trong [todo.md](todo.md).

## Thứ tự triển khai

| Bước | Kết quả có thể nghiệm thu | Phụ thuộc |
| --- | --- | --- |
| 1 | Adapter GOLD/VFF chuẩn hóa đúng nguồn, đơn vị và thời gian | Audit nguồn đã xong |
| 2 | Snapshot và panel availability hỗn hợp có ledger | 1 |
| 3 | Selection K5 có snapshot pin, schedule và recovery | 2 |
| 4 | Core chạy đúng bảy tài sản hoạt động và map về 32 | 3 |
| 5 | Fit/export v4 có 25 UBJ và validation đã purge | 2, 3 |
| 6 | Training queue và review v4 bền vững | 5 |
| 7 | Publication và worker kiểm tra cùng hợp đồng v4 | 4, 6 |
| 8 | Portfolio pin selection, active assets và effective risk policy | 4, 7 |
| 9 | Browser hiển thị K5, GOLD/VFF, ngày khả dụng và trạng thái readiness | 8 |
| 10 | Gate nguồn thật, broker, đối chiếu baseline và persistence | 1–9 |

## Các điểm cần xác nhận khi triển khai

- Freshness VFF theo ngưỡng 7 ngày có thể tạo khoảng chặn hợp lệ khi giữ
  buffer năm phiên. Quyết định thay policy cần được ghi và kiểm chứng bằng
  dữ liệu kỳ nghỉ, tháng có NAV bổ sung và sự cố thiếu nguồn.
- Policy kết hợp risk profile với baseline là đề xuất trong tài liệu này.
  Fixture dùng cùng effective constraints để kiểm tra numerical parity.
- Thay K5 có thể loại cổ phiếu từng có tỷ trọng mục tiêu trong danh mục cũ.
  Proposal mới hiển thị chênh lệch và giữ lịch sử target theo phiên bản.
- Reselection/refit quá hạn, reviewer chậm, lỗi hash hoặc nguồn tạm mất phải
  có readiness reason riêng. Retry đồng thời không tạo selection/model trùng.
- Nguồn lịch sử là retrospective adjusted prices/NAV và các giả định availability
  đã khai báo. Hash và ngày tải được lưu để phát hiện revision giữa các lần lấy.

## Hoàn thành nghiệm thu

Nguồn đầy đủ, panel có audit, selection và 25 booster khớp fixture đóng băng.
Các ca normal/stress/crisis kiểm tra P/Q, confidence, prior/posterior,
covariance, threshold và constraints. Broker chạy BL_ML trên dữ liệu thật,
EW dự phòng bỏ chọn, tổng trọng số 100%, 25 cổ phiếu ngoài K5 bằng 0.
Receipt ghi đúng full snapshot, selection, model, policy và bundle.
Restart stack rồi mở lại chính đề xuất đó, kiểm tra các pin, trọng số và
epoch. Lượt proposal tại ngày stale phải bị chặn với lý do đúng.


## Trạng thái triển khai trên local

Mã cho bước 1–9 đã được triển khai, dùng lại JSON snapshot/manifest và immutable
bundle hiện có thay vì thêm bảng mutable cho epoch. Task ledger nằm tại
`.superpowers/sdd/phase1-full/progress.md`. Live refresh đã commit snapshot 32
với 54.197 observations trên PostgreSQL. Freshness giữ 7 ngày; dữ liệu VFF mới
nhất ở nguồn và observation đủ điều kiện tại checkpoint được báo riêng.
Kết quả nghiệm thu, giới hạn và lệnh canonical Compose được ghi trong
`docs/software/PHASE1_LOCAL_SERVING.md` và checkbox bước 10 của `tasks/todo.md`.
