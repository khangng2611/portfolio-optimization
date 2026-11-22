# Cải tiến UI/UX cho người mới — audit và kế hoạch triển khai

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Giúp người mới hiểu kế hoạch, đọc phân bổ, hỏi đúng điều cần biết và quyết định lưu mục tiêu mà vẫn giữ nguyên nghiệp vụ hiện tại.

**Architecture:** Tái sử dụng dữ liệu Portfolio, evidence của Quant và thông điệp Chat đã kiểm chứng. Làm lại cách tổ chức nội dung và responsive trước; bổ sung API nhỏ cho trạng thái tạm dừng và dữ liệu biểu đồ giá ở các phần riêng. Không thay solver, policy, mô hình hoặc cơ chế xác nhận.

**Tech Stack:** Next.js 16, React 19, TypeScript, CSS hiện có; FastAPI, PostgreSQL, RabbitMQ; Vitest và Playwright hiện có. Giữ Be Vietnam Pro và các token thương hiệu hiện tại. Chưa cần thêm thư viện biểu đồ cho các thanh tỷ trọng và so sánh đơn giản.

**Spec:** Yêu cầu của người dùng ngày 22/11/2026, brief và các tiêu chí trong tài liệu này; đối chiếu [V2.7](2026-11-22-figma-v27-frontend.md), [explanation](../../software/ALLOCATION_EXPLANATION.md), [HYBRID](2026-11-22-system-allocation-hybrid.md). Đây là **đề xuất để review**, chưa phải lệnh triển khai hoặc phê duyệt thiết kế mới.

## Global Constraints

- Giữ luồng: mục tiêu + rổ tài sản → khảo sát rủi ro → xem lại/xác nhận → tạo đề xuất → xem kết quả → chủ động chấp nhận làm mục tiêu.
- Chấp nhận chỉ lưu tỷ trọng mục tiêu; vốn kế hoạch không phải số dư; lịch sử mục tiêu không phải hiệu suất đầu tư.
- Giữ hai phạm vi lưu riêng của rổ tài sản và tên/vốn kế hoạch; không ghép thành một lần lưu nếu API chưa có giao dịch nguyên tử tương ứng.
- Giữ owner checks, role checks, CSRF, If-Match, idempotency, chống chấp nhận đề xuất cũ và cơ chế phục hồi tác vụ.
- Giữ nguyên facts/evidence hash, snapshot/model/risk/selection pins, tỷ trọng và thông điệp lịch sử. Không chạy lại model để lấp dữ liệu thiếu của kết quả cũ.
- Investor có một luồng đề xuất hệ thống; EW/MVO chỉ là tham chiếu khi có dữ kiện tương ứng. Không khôi phục lựa chọn phương pháp hoặc tự chuyển sang phương án dự phòng để vượt trạng thái paused.
- Dữ liệu thiếu phải ghi rõ thiếu; không vẽ lợi nhuận, NAV, đường giá, efficient frontier hoặc rủi ro giả định từ các con số không đủ nghĩa.
- Chuẩn kiểm tra thiết kế: 375/390/768/1024/1440 CSS px; thêm zoom 200%, bàn phím, màn hình thấp và bàn phím ảo. Chạm tối thiểu 44×44 px; tương phản chữ thường tối thiểu 4,5:1; không dùng màu làm tín hiệu duy nhất.
- Đợt audit này chỉ đọc ứng dụng và mã nguồn; không sửa Figma, code, runtime, dữ liệu nghiệp vụ hoặc chính sách chi tiêu provider.

## Review Focus

1. Câu hỏi hẹp như RSI của một mã phải trả lời đúng mã/chỉ báo trước, không bắt đọc lại cả đề xuất. Kiểm ở Task 3.
2. Tin nhắn cũ, evidence thiếu/sai hash và chuyển danh mục giữa hai lượt chat không được hiển thị dữ kiện của kết quả khác. Kiểm ở Task 3 và 6.
3. Paused phải phân biệt với dữ liệu cũ, thiếu model và rổ không khả thi; người dùng không bị hướng dẫn sửa rổ để giải quyết việc tạm dừng hệ thống. Kiểm ở Task 2.
4. Rổ trống/toàn bộ mã đã chọn, mô tả dài, hai phần có thay đổi chưa lưu và xung đột phiên bản vẫn lưu đúng phạm vi. Kiểm ở Task 5.
5. Giá khác provider/revision/price type, GOLD khác đơn vị và NAV công bố trễ không được nối thành một đường giá gây hiểu sai. Kiểm ở Task 4B.

## 1. Phạm vi đã rà soát và mức độ bằng chứng

Ngày rà soát: **22/11/2026**. Đọc danh sách **20 WorkspaceView** trong `apps/web/src/lib/workspace-state.ts`, login/register, shell, các component nghiệp vụ, BFF và OpenAPI của Portfolio/Market/Quant/Chat/ML/Knowledge. Đối chiếu code mới về explanation và HYBRID, không dựa riêng vào thiết kế cũ.

Trình duyệt: mở tổng quan chưa có mục tiêu nhưng đã có đề xuất, lịch sử đề xuất, kết quả HYBRID đã lưu, so sánh hai kết quả khác đầu vào, danh sách hội thoại, hội thoại explanation có follow-up, sửa rổ/kế hoạch, hồ sơ rủi ro, màn tạo đề xuất bị chặn và bước đầu onboarding. Quan sát desktop, mobile; xác minh kích thước CSS bằng DOM. Không gửi chat, lưu, tạo job, accept, refresh hoặc train.

Figma qua **figma-mcp-go**: đọc page `4:212`, có 19 section, trong đó V2.7 `210:8603`; xem ảnh explanation desktop `210:8976` và mobile `210:9155`. File [Portfolio Optimization](https://www.figma.com/design/YKRbiOAJNoVA9DaSZHc7Wc/?node-id=210-8603). Các section như “Tài sản & hiệu suất”, “Tái cân bằng”, “Research & backtest” trong Figma không tự chứng minh các chức năng đó đã có trong app.

Màn vận hành và xác thực được rà soát qua code/contracts; không thực hiện đầy đủ từng thao tác với các vai trò này. Các số test trong tài liệu cũ là bằng chứng của đợt triển khai trước, không phải test được chạy lại trong audit này.

## 2. Kết luận audit

Vấn đề chính là **thứ tự thông tin, sự lặp lại và cách bố trí vùng làm việc**, bên cạnh nội dung chuyên môn. Nền tảng đã có phần lớn dữ kiện cần thiết để cải thiện trải nghiệm đọc kết quả; các biểu đồ hiệu suất và tính năng giao dịch cần phạm vi nghiệp vụ khác.

| Ưu tiên | Phát hiện hiện tại | Hướng xử lý |
| --- | --- | --- |
| P0 | Hỏi “RSI của CTG là bao nhiêu?” vẫn dựng lại toàn bộ allocation, hồ sơ và views nhiều mã. Câu trả lời server nằm trong “Nội dung giải thích đã lưu”. | Đưa câu trả lời đã kiểm chứng lên đầu; khối kết quả đầy đủ chỉ mở khi cần. |
| P0 | Trong hội thoại mẫu có 3 câu hỏi hẹp, transcript dài khoảng **11.123 px**, vùng đọc khoảng **337 px** tại **390×843 CSS px**. Đây là một mẫu, không phải benchmark mọi cuộc chat. | Giảm nội dung lặp; tăng diện tích đọc; giữ một vùng cuộn chính cho hội thoại. |
| P0 | Desktop có sidebar ứng dụng, sidebar hội thoại, lane nội dung và khoảng trống lớn; ở mobile nhiều tầng header/context/composer/navigation tranh chiều cao. | Thiết kế shell riêng cho chat; mở danh sách/ngữ cảnh theo yêu cầu; dùng khoảng trống có mục đích. |
| P0 | HYBRID managed paused hiện trả `INPUT_UNAVAILABLE`; UI nói “Dữ liệu hoặc mô hình chưa sẵn sàng”. Người dùng không biết có thể tự xử lý hay cần chờ hệ thống. | Bổ sung lý do tạm dừng có nghĩa rõ ràng từ server, không đoán từ frontend. |
| P1 | Có thanh tỷ trọng và bảng phân bổ, nhưng thiếu tiêu đề/khu vực biểu đồ dễ nhận diện; chưa có trang chart giá cho investor. | Đặt “Phân bổ mục tiêu” thành một nhóm trực quan; thêm thanh theo mã và so sánh. Chart giá triển khai riêng. |
| P1 | Evidence còn lộ Q, confidence, Option B, regime, K5 và nhiều thống kê trước khi người mới hiểu ý nghĩa. | Ba lớp nội dung: kết luận → căn cứ liên quan → dữ liệu/phương pháp đầy đủ. |
| P1 | Bước đầu onboarding đồng thời yêu cầu mục tiêu, vốn, thời hạn và chọn tới 32 tài sản; copy cuối bước có hệ số và regime. | Chia thành nhóm công việc trong cùng bước; giải thích bằng ngôn ngữ đời thường và disclosure, giữ thứ tự nghiệp vụ. |
| P1 | Mobile asset picker vẫn xếp hai khung có vùng cuộn riêng trên một trang dài; chi tiết GOLD/VFF có mô tả rất dài. | Giữ transfer model trên desktop; mobile cho một khung hoạt động mỗi lúc, giữ số lượng hai phía và draft chung. |
| P1 | `RiskProfileView` chỉ hiện thêm giới hạn phòng thủ theo một universe ID; danh mục custom có thể chỉ nhìn thấy cap mỗi tài sản. | Hiện các giới hạn thực sự có trong constraints, không suy từ tên universe. |
| P2 | “Nhận định — Sắp có” chiếm chỗ điều hướng; auth, lịch sử và thao tác vận hành cần thống nhất trạng thái/nhãn. | Điều hướng theo khả năng hiện có; lịch sử dễ đọc hơn; giữ console theo vai trò. |

Phần đã tốt cần giữ: giải thích gắn canonical facts/evidence; cảnh báo mục tiêu khác đầu vào hiện tại; phân biệt rổ cân nhắc/tập tính toán/tài sản có tỷ trọng; chấp nhận tách khỏi chat; draft-only suggestions; disclosure metadata; bảng có sắp xếp. V2.7 đã cải thiện các phần này, không cần làm lại từ đầu.

## 3. Inventory chức năng và phương án cải tiến

| Nhóm hiện có | Surface/flow | Thiết kế đề xuất | Hệ thống hỗ trợ |
| --- | --- | --- | --- |
| Truy cập | Trang giới thiệu, đăng ký, đăng nhập, hết phiên, trở lại đích đang mở | Nói rõ app giúp phân bổ cuối ngày; ví dụ công việc; lỗi gần field; giữ đích sau login | UI trên auth/BFF hiện có; không thêm SSO/reset password trong đợt này |
| Quản lý danh mục | `portfolios`, tìm/lọc/sort/phân trang, picker theo ngữ cảnh | Tên + vốn kế hoạch + hồ sơ; primary action rõ; phân biệt chưa có danh mục với không có kết quả tìm kiếm | API danh sách đã có filter/sort; không cần dashboard tổng tài sản giả |
| Onboarding | `create`, 3 bước mục tiêu/rủi ro/xác nhận, chọn rổ | Trong bước 1 nhóm “Kế hoạch” và “Tài sản được cân nhắc”; hướng dẫn một câu; ở review dùng câu thường thay policy code | Giữ payload và explicit confirmation; không tự trả lời khảo sát hoặc tự chọn mã |
| Tổng quan | `overview`, accepted target hoặc next step, đầu vào đã đổi | Kế hoạch hiện tại → phân bổ mục tiêu/ngữ cảnh chưa có mục tiêu → bước tiếp theo → dữ liệu và giới hạn | Dashboard đã có target, proposal_count, target_matches_portfolio; trạng thái readiness phải tải đúng portfolio |
| Hồ sơ | `profile`, `risk-assessment`, preview/xác nhận và lịch sử | Hồ sơ nghĩa là gì → giới hạn áp dụng → câu trả lời cơ sở → thay đổi trước/sau → thông số mở thêm | API preview/history đã có; render theo constraints thực; không dựng hồ sơ trước xác nhận |
| Sửa kế hoạch/rổ | `edit`, transfer picker, metadata, selection history | Hai nhóm hoặc tab rõ phạm vi, từng nút lưu riêng; mobile tránh hai danh sách cuộn xếp dài | UI trước; giữ version/If-Match, lưu rổ riêng/lưu kế hoạch riêng |
| Tạo đề xuất | `proposal`, readiness, review request, async job | Checklist ngắn có việc tiếp theo; trạng thái đang làm/chờ/lỗi; lý do chặn và ai xử lý | Jobs hiện có; paused cần bổ sung reason có nghĩa rõ ràng |
| Review kết quả | `proposal` có ID, constraints, accept | Phân bổ + điều chính cần biết + lựa chọn lưu mục tiêu; căn cứ/phương pháp/nguồn mở theo nhu cầu | Dữ kiện đã có; evidence đọc theo owner; không tự tạo explanation/provider call khi mở trang |
| Lịch sử và so sánh | `history`, proposal browser, `compare` | Timeline theo ngày/trạng thái; biểu đồ Δ B−A; hiện các điểm khác đầu vào trước khi so sánh | Targets/recommendations đã có; lịch sử mục tiêu và lịch sử đề xuất vẫn là hai khái niệm |
| Hội thoại | `chat`, tạo/mở hội thoại, chọn ngữ cảnh, profile/portfolio/market/knowledge/explain/allocation, confirm, cancel/resume | Chat theo câu hỏi; kết quả được tham chiếu; nguồn gần nội dung; sidebar/context có thể đóng | SSE/jobs/delegation/evidence đã có; mức trả lời một chỉ báo cần làm nhỏ finite claims |
| Dữ liệu vận hành | `market`, `market-ingestion`, `market-quality`, `market-snapshots`, `market-publications`, `market-refresh` | Console riêng: tác vụ hiện tại → cấu hình → trạng thái → kết quả/chi tiết; bảng và filter phù hợp | Ingest/quality/snapshot/publication/schedule/job APIs hiện có; không đưa nút này vào luồng investor |
| Mô hình vận hành | `models`, `model-training`, `model-review` | Registry + serving status + evidence + quyết định review; temporal boundaries dễ đọc | Roles/training/reviews hiện có; giữ quyền người duyệt riêng |
| Kiến thức và trạng thái chung | Nguồn RAG, phương pháp, trace, lỗi quyền/kết nối/xung đột/hết hạn | Nhãn nguồn dễ hiểu, trạng thái actionable, kỹ thuật mở thêm | Không thấy knowledge administration UI riêng trong 20 view; không hứa có semantic search nếu chưa qua gate |

**Chưa có trong app investor hiện tại:** theo dõi holdings/giao dịch thực tế, NAV/P&L danh mục theo thời gian, màn backtest, efficient frontier, workflow tái cân bằng có lệnh thực thi và màn tự nhập views. Đây là khoảng cách giữa roadmap/Figma/research scripts với sản phẩm đang chạy, không chỉ là các nút UI bị ẩn.

## 4. Brief thiết kế và các mẫu tham khảo

**Người dùng chính:** nhà đầu tư Việt Nam mới làm quen với phân bổ tài sản, đọc trên điện thoại, cần hiểu bước tiếp theo và ý nghĩa kết quả. Người có chuyên môn vẫn truy cập đầy đủ nguồn/phương pháp. Operator/reviewer dùng console riêng theo vai trò.

**Hướng thiết kế:** giữ nhận diện xanh hiện có, Be Vietnam Pro, nền sáng, số liệu dễ so sánh. Mỗi surface có cấu trúc theo công việc: chat là cuộc hội thoại; rổ là nơi lựa chọn; kết quả là nơi review quyết định; console là nơi theo dõi tác vụ. Không dùng một grid card giống nhau cho tất cả.

| Tham khảo chính thức | Mẫu có thể học | Áp dụng vào app |
| --- | --- | --- |
| [Claude Artifacts](https://support.claude.com/en/articles/17153992-what-are-artifacts-and-how-do-i-use-them) | Nội dung độc lập mở cạnh hội thoại | Một kết quả đề xuất có thể mở trong vùng chi tiết, trong khi câu hỏi vẫn dễ đọc; không lặp toàn bộ kết quả ở mọi tin nhắn |
| [Perplexity](https://www.perplexity.ai/help-center/en/articles/10352895-how-does-perplexity-work) | Câu trả lời có liên kết nguồn và giữ ngữ cảnh khi hỏi tiếp | Nguồn gần claim; tiếp tục đúng recommendation; tách nguồn phương pháp khỏi số liệu của lần tính |
| [HayBuddy / Finhay](https://fhsc.com.vn/tro-ly-dau-tu-ai-haybuddy) | Tài liệu giới thiệu nhấn mạnh tra cứu tự nhiên, câu trả lời cô đọng theo nhu cầu | Starter phù hợp người mới, hỏi theo mã/chỉ báo, ngôn ngữ Việt quen thuộc |

Đây là suy luận thiết kế từ nguồn sản phẩm công khai, không phải bằng chứng đã đo usability hoặc kiểm thử chất lượng trả lời của các ứng dụng tham khảo. Không sao chép giao dịch, dữ liệu real-time hoặc nhận định thị trường tổng quát sang app cuối ngày nếu backend chưa cung cấp.

**Nguyên tắc nhóm component:** nhóm theo câu hỏi của người dùng, không nhóm theo tên service hay cứ thêm một card cho từng paragraph. Dùng heading, khoảng cách, nền/viền khi thật sự cần phân tách; mỗi nhóm có một việc chính.

| Nhóm dùng chung | Nội dung chính | Dùng ở đâu |
| --- | --- | --- |
| Ngữ cảnh kế hoạch | Tên danh mục, vốn hiện tại hoặc vốn đã ghim có nhãn khác nhau, hồ sơ, ngày dữ liệu | Overview/proposal/chat |
| Trạng thái và bước tiếp theo | Chuyện gì đang xảy ra, ảnh hưởng, ai có thể xử lý, action phù hợp | Readiness/job/error/stale/paused |
| Phân bổ mục tiêu | Chart có tên, tỷ trọng, bảng VND, số tài sản được phân bổ | Overview/proposal/detail trong chat |
| Giải thích theo câu hỏi | Kết luận, dữ kiện liên quan, ý nghĩa/giới hạn, nguồn | Chat/proposal |
| Chọn tài sản | Mã + tên + loại + tình trạng dữ liệu; mô tả mở thêm | Onboarding/edit |
| Quyết định | Một hành động chính và hậu quả của hành động | Confirm request/accept/reassess/save |
| Nguồn và kiểm chứng | Ngày dữ liệu/nguồn gần nội dung; hash, IDs, tham số ở lớp sâu | Mọi kết quả có provenance |

Ưu tiên tái tổ chức `AllocationView`, `ReadinessNotice`, `TaskActions`, `AssetPicker`, `RecommendationEvidenceView` hiện có. Chỉ tách component khi cần dùng chung hoặc để giữ ranh giới dữ liệu rõ ràng.

### Chat desktop và mobile

- Câu trả lời mặc định: **trả lời trực tiếp → dữ kiện đúng câu hỏi → giới hạn liên quan → nguồn/xem thêm**. Câu hỏi hẹp nên bắt đầu bằng 2–4 câu; độ dài là mục tiêu thiết kế, không cắt bỏ điều kiện quan trọng để đạt quota chữ.
- Ví dụ hỏi RSI: hiện giá trị RSI14 của đúng mã, ngày kết thúc dữ liệu và giải nghĩa ngắn có căn cứ. Không tự kết luận mua/bán; không mở cả 5 ML views. Nếu chưa có dữ kiện của mã thì nói rõ thiếu.
- Tin nhắn follow-up cùng recommendation chỉ mang tham chiếu kết quả; kết quả đầy đủ có một vùng đọc riêng. Tin nhắn cũ vẫn giữ dữ liệu, có thể mở lại. Nhãn “Đã tạo đề xuất” chỉ dùng ở sự kiện tạo mới, không gắn cho mọi lượt giải thích.
- Desktop dùng một danh sách hội thoại có thể đóng, một vùng đọc chính, composer ở đáy. Vùng kết quả/nguồn bên cạnh chỉ mở khi cần và khi đủ rộng; không mặc định dựng bốn cột.
- Mobile có một vùng cuộn chính cho transcript; lịch sử/ngữ cảnh/chi tiết mở bằng drawer hoặc màn chi tiết thay vì chèn thêm một khung cuộn giữa câu trả lời. Giữ tên danh mục/đề xuất ngắn luôn nhận biết được.
- Composer tự tăng chiều cao có giới hạn; Enter/Shift+Enter và phím tắt phải được chốt nhất quán, xử lý IME. Kiểm bàn phím ảo; không để composer che tin nhắn cuối hay action xác nhận. Thiết kế chế độ tập trung có thể đưa điều hướng phụ vào menu, vẫn có đường trở lại rõ ràng.
- Giữ scroll position khi đọc tin nhắn cũ; chỉ tự theo cuối khi người dùng đang gần cuối. Giữ cancel/resume và trạng thái job thật; không giả token-stream khi backend chỉ phát tiến trình.
- Không mở thêm provider call khi mở panel, chuyển tab, xem chart hoặc xem lại hội thoại. Gợi ý chỉ điền draft; gửi và xác nhận vẫn do người dùng thực hiện.

### Nội dung dễ hiểu hơn

Ba lớp: **“Bạn cần biết gì?” → “Dựa vào đâu?” → “Xem dữ liệu/phương pháp”**. Cảnh báo stale/không thể accept/thiếu dữ kiện ảnh hưởng kết luận phải hiện ngay tại chỗ, không giấu dưới disclosure.

| Hiện tại | Cách trình bày lớp đầu |
| --- | --- |
| K5, active assets, candidate universe | “Tài sản bạn cho phép cân nhắc” / “Tài sản dùng trong nhánh mô hình” / “Tài sản được phân bổ”; giải thích đây là các tập khác nhau |
| Facts hash, policy ID, Option B | “Nguồn và cách kiểm chứng” → mã và phương pháp đầy đủ bên trong |
| Confidence 0,648 | Chỉ mở điểm và định nghĩa heuristic khi cần; không đổi thành “64,8% khả năng tăng” |
| Regime/crisis | “Bối cảnh rổ tại lần tính: bình thường/căng thẳng/khủng hoảng”; không biến thành nhận định hiện tại về VNINDEX |
| Q %/ngày và raw forecast 5 phiên | Giữ khác đơn vị; lớp đầu ưu tiên tín hiệu đúng câu hỏi, lớp phương pháp giải thích phép chuyển đổi |
| Rổ custom cần VFF | “Cần có VFF trong rổ để đáp ứng quy tắc phòng thủ hiện tại”; giữ rõ GOLD thuộc nhóm ngoài phòng thủ theo policy này |

Không hạ mọi nội dung quan trọng thành tooltip. Người dùng điện thoại và bàn phím phải đọc được định nghĩa bằng nút/disclosure có nhãn.

## 5. Khả thi của chart và backend

| Chart / cải tiến | Dữ liệu hiện có | Phạm vi cần làm |
| --- | --- | --- |
| Phân bổ theo mã/loại tài sản | `asset_ids`, `weights`, `capital_vnd`; catalog có `kind` | Frontend; thanh ngang có nhãn + bảng. Mặc định hiện mã có tỷ trọng dương, vẫn mở được mã 0%. Không ép 32 lát màu vào donut |
| Chênh lệch hai đề xuất | Hai recommendation; code đã tính Δ B−A | Frontend; diverging bar theo điểm %, giữ cảnh báo khác cơ sở đầu vào; không gắn nhãn phương án thắng |
| Giới hạn phân bổ | Constraints đã ghim + weights | Frontend tính tỷ trọng nhóm từ dữ kiện đã ghim/định nghĩa policy; hiển thị “áp dụng/thực tế”, không gọi đó là điểm rủi ro tổng hợp |
| Tham chiếu HYBRID/EW/MVO | `diagnostics.hybrid` có weights, daily volatility, cửa sổ covariance ở kết quả HYBRID mới | Frontend có điều kiện; không backfill cho kết quả cũ, không so dự báo lợi nhuận khác mô hình, EW vi phạm phải được ghi rõ |
| Tín hiệu ML tại lần tính | Evidence có raw forecast, horizon, features, regime | Frontend có thể vẽ bar đúng kỳ hạn; mặc định không đưa chart kỹ thuật vào câu hỏi đơn giản. Confidence không phải xác suất, feature không phải attribution |
| Giá/NAV của từng tài sản qua thời gian | Market có `GET /api/v1/market/prices`; snapshot observations cũng tồn tại | **Cần đường đọc cho investor qua BFF và contract chuỗi giá được chọn đúng**. BFF hiện chưa có prices route; endpoint prices trả nhiều revision/provider/type, chưa phải chart-ready series |
| NAV/P&L danh mục thực tế | Chưa có holdings/trade/cash-flow ledger trong flow investor hiện tại | Feature backend mới; không suy ra từ vốn kế hoạch × weights × giá hiện tại |
| Backtest, drawdown danh mục, efficient frontier | Có code nghiên cứu; không thấy API/UI investor tương ứng | Phạm vi nghiên cứu/sản phẩm riêng, cần contract, job, dữ liệu, chi phí/benchmark và kiểm chứng theo thời gian |

**Đường giá cần chốt trước khi build:** một series xác định theo asset/provider/price_type/price_basis; lựa chọn revision và cutoff có ý nghĩa; `unit`, source, observation date, published/available time, stale, origin; ngày thiếu không coi là 0. Không nối raw và adjusted price hoặc các loại giá vàng. Không chồng GOLD/VFF/cổ phiếu khác đơn vị trên cùng trục giá; nếu chuẩn hóa index=100 phải ghi cách chuẩn hóa và không gọi là total return.

Đọc giá hiện tại và đọc snapshot đã dùng cho đề xuất là hai việc khác nhau. Chart ở màn review phải cho biết đang hiển thị loại nào. Không dùng dữ liệu cập nhật sau này để giải thích ngược số liệu của một run cũ. Kiểm response limits để không âm thầm cắt lịch sử ở 1.000/5.000 rows hoặc lấy “latest” bằng một query trả các revision cũ trước.

**Hai bổ sung backend nhỏ khác:**

1. Readiness trả reason riêng cho system paused, thay vì gộp vào thiếu dữ liệu/model. Tên enum chốt khi implement, ví dụ `SYSTEM_PAUSED`; UI có hướng dẫn phù hợp, giữ lịch sử đọc được. Không thay cờ HYBRID trong dự án UI.
2. Chat đã lưu `selected_claim_ids` và `explanation_claims` ở structured message, nhưng frontend type chưa khai báo các trường này và vẫn render một panel evidence tổng quát. Có thể dùng lại để trình bày đúng chủ đề sau khi đối chiếu dữ kiện. Với câu hỏi một chỉ báo như RSI, backend hiện có claim `features_<asset>` chứa cả bộ features: cần làm nhỏ claim/renderer và kiểm validator, không chỉ sửa CSS hoặc regex cắt câu trên frontend.

## 6. Các task theo thứ tự phụ thuộc

### Task 1 — Figma prototype cho toàn bộ hành trình chính

**Ưu tiên:** P0. **Đầu ra:** section proposal mới trong file Figma hiện tại; giữ V2.7 làm baseline, không ghi đè bản đã triển khai.

- [ ] Chốt inventory và copy ba lớp theo tài liệu này; đánh dấu màn đã có data, màn cần API, màn thuộc roadmap.
- [ ] Thiết kế trước chat câu hỏi hẹp/tổng quan/confirmation/result/nguồn, overview ba trạng thái và rổ mobile/desktop. Dùng component chung, không lặp frame rời rạc thiếu trạng thái.
- [ ] Nối prototype: bắt đầu → hiểu rổ/rủi ro → tạo đề xuất → review → xem giải thích/chart → lưu mục tiêu → đọc lịch sử. Giữ một proposal flow, hai phạm vi lưu và trạng thái paused.
- [ ] Bổ sung màn tạo/sửa danh mục, profile/reassessment, lịch sử/compare, auth và console variants theo bảng inventory.
- [ ] Kiểm mẫu ít/nhiều: 0/1/32 mã, 0% và nhiều tỷ trọng dương, tên dài, nguồn thiếu, evidence partial, legacy result, chat nhiều lượt, job chờ/lỗi/hết phiên, dữ liệu stale và hai phiên sửa xung đột.
- [ ] Review prototype mobile và desktop với nội dung thật đã ẩn danh; chốt thứ tự, độ dài câu trả lời, hành vi panel, composer và labels trước khi viết UI.

Không chốt màu/font mới từ kết quả tìm kiếm skill chung. Truy vấn design-system của UI/UX Pro Max đã trả mẫu enterprise gateway/dark mode không phù hợp mục tiêu; chỉ dùng quy tắc chart/a11y phù hợp và nhận diện hiện có.

### Task 2 — Shell, nhóm nội dung và trạng thái rõ ràng

**Ưu tiên:** P0. **Sau:** Task 1. **Files:** `apps/web/src/components/workspace-shell.tsx`, `portfolio-lifecycle.tsx`, `portfolio-workspace.tsx`, `apps/web/src/app/home.tsx`, `ui-refresh.css`, `apps/web/src/lib/workspace-state.ts`, `selection-types.ts`; phần paused ở `services/portfolio/src/portfolio_service/api.py`, các contracts và consumer Chat liên quan.

- [ ] Giảm các tầng header trùng nhau; giữ ngữ cảnh rõ theo danh mục. Investor navigation chỉ ưu tiên chức năng đã dùng được; không thêm “Biểu đồ” trước khi có surface đủ dữ liệu.
- [ ] Tách layout cho conversation, form/selection, allocation review và operator tables. Giữ một action chính theo trạng thái; không lấp khoảng trống bằng KPI chưa có nguồn.
- [ ] Bổ sung paused reason ở server/contracts và ánh xạ thành thông báo: chuyện gì, ảnh hưởng, có thể xem gì, ai xử lý. Với các reason khác, dùng deep link tới đúng rổ/hồ sơ khi người dùng tự sửa được.
- [ ] Giữ nút/lời nhắc cần xác nhận và chấp nhận; mọi trạng thái disabled có nguyên nhân nhìn thấy được.
- [ ] Kiểm `workspace-state.test.ts`, `portfolio-context.test.tsx`, `lifecycle-components.test.tsx`, `guided-ui.test.tsx`, `p1-navigation.test.ts`, `market-bff.test.ts`, `p1-bff.test.ts` khi liên quan. Thêm regression server cho paused khác data/model unavailable; chốt tên file backend theo test hybrid/readiness hiện có.

**Nghiệm thu:** Người mới xác định được danh mục đang mở, trạng thái hiện tại và hành động tiếp theo mà không phải mở chẩn đoán kỹ thuật. Paused không thể bị vượt qua bằng nút UI, Chat hoặc payload tự chọn strategy.

### Task 3 — Chat trả lời theo câu hỏi, kết quả mở riêng

**Ưu tiên:** P0. **Sau:** Task 1–2. **Files:** `chat-workspace.tsx`, `chat-workspace.css`, `recommendation-evidence.tsx`, `apps/web/src/lib/chat-types.ts`, `apps/web/src/lib/chat-scroll.ts` nếu cần theo implementation hiện tại; `services/chat/src/chat_service/explanation.py`, `workflow.py`, contracts explanation khi cần.

- [ ] Trước tiên đưa saved answer đã qua canonical/evidence guard lên đầu. Đổi panel evidence tổng quát thành phần mở thêm; không che câu trả lời dưới nhãn “Nội dung giải thích đã lưu”.
- [ ] Tiếp theo dùng structured claims đúng topic/mã để render câu trả lời và nguồn. Không dùng tự do LLM để viết lại số hoặc suy attribution; không tin text/hash từ client.
- [ ] Làm nhỏ claim cho câu hỏi một feature; giữ validator yêu cầu đúng mã/chủ đề, limitations liên quan và fallback an toàn. Duy trì đọc được các tin nhắn renderer cũ.
- [ ] Chỉ render allocation đầy đủ khi giới thiệu kết quả hoặc khi mở chi tiết; follow-up giữ tham chiếu tới đúng recommendation. Nguồn phương pháp và dữ kiện run có nhãn khác nhau.
- [ ] Áp dụng chat shell/prototype, vùng đọc đủ cao, composer và điều hướng mobile; không đưa bảng dài vào khung cuộn bên trong mỗi tin nhắn.
- [ ] Regression ở `chat-workspace.test.tsx`, `recommendation-evidence.test.tsx`, `chat-types.test.ts`, `chat-scroll.test.ts`, `chat-navigation.test.tsx`, `chat-knowledge.test.tsx`, `tests/software/test_chat_explanation_evidence.py`; thêm assertion câu hỏi RSI chỉ render chỉ báo/mã liên quan, không dump allocation/5views mặc định.
- [ ] Browser kiểm 10+ lượt, đọc tin nhắn cũ khi có cập nhật, chuyển hội thoại/danh mục, resume sau reload, sources bằng bàn phím, IME và bàn phím ảo. Kiểm payload hash mismatch/partial/unavailable và old message không có claim fields.

**Nghiệm thu:** Câu trả lời trực tiếp hiện trong lần nhìn đầu ở câu hỏi hẹp; không lặp allocation ở mọi follow-up; nguồn/kết quả đầy đủ luôn mở được. Không tăng provider calls khi chỉ xem thông tin, không thay quyết định nghiệp vụ.

### Task 4A — Chart phân bổ, chênh lệch và tổng quan

**Ưu tiên:** P1, có thể làm trước chart giá. **Sau:** Task 1–2. **Files:** `allocation-view.tsx`, `portfolio-workspace.tsx`, `portfolio-lifecycle.tsx`, `recommendation-evidence.tsx` khi liên quan, các type hiện có.

- [ ] Đặt tiêu đề chart rõ ràng; dùng thanh ngang theo mã có nhãn trực tiếp và tỷ trọng; giữ bảng VND có sắp xếp. Cân nhắc thanh tổng theo loại tài sản, lấy `kind` từ catalog và ghi “khác/chưa rõ” nếu thiếu metadata.
- [ ] Overview đưa phân bổ và next step lên trước nội dung thứ cấp. Khi chưa accepted target chỉ có next step/kết quả chờ review, không gọi proposal là tài sản đang nắm giữ.
- [ ] Compare hiện Δ theo điểm %, ưu tiên thay đổi đáng chú ý; cho mở tất cả tài sản và thông số đầu vào. Không dùng xanh/đỏ để ngụ ý phương án có lợi nhuận tốt hơn.
- [ ] Chỉ hiện chart constraints/references khi dữ kiện và đơn vị đủ; giữ nội dung EW vi phạm, cửa sổ covariance và trạng thái legacy.
- [ ] Regression ở `allocation-view.test.tsx`, `lifecycle-components.test.tsx`, `finhay-v27.test.tsx`, `selected-proposal.test.tsx`. Kiểm 0/1/nhiều tỷ trọng dương, giá trị rất nhỏ, round-off, thiếu metadata, không đổi thứ tự vector gốc hoặc hash khi sort/group.

**Nghiệm thu:** Người dùng tìm được phân bổ từ overview/review mà không cần biết thuật ngữ chart. Tên mã, tỷ trọng và bảng thay thế đọc được bằng bàn phím/screen reader; không chỉ nhận diện bằng màu lặp.

### Task 4B — Chart giá từng tài sản qua thời gian

**Ưu tiên:** P1 sau 4A, là một phần có API; không chặn cải tiến chat. **Files:** `services/market-data/src/market_service/api.py`, `snapshots.py`, contracts Market, `apps/web/src/server/bff.ts`, `apps/web/src/lib/market-types.ts`; UI chi tiết tài sản nhỏ được chốt trong Task 1.

- [ ] Chốt canonical series contract và phạm vi quyền; tái dùng resolver/snapshot policy hiện có khi đúng nghĩa, tránh tự chọn revision khác ở frontend. Chốt current series so với pinned snapshot series.
- [ ] Bổ sung BFF read-only allowlist, whitelist/range limit query và kiểm quyền. Có thể chuẩn hóa endpoint hiện tại hoặc thêm read endpoint nhỏ; không mở rộng các route operator chỉ để vẽ chart.
- [ ] Tạo asset detail có line chart, kỳ thời gian, đơn vị, nguồn/ngày dữ liệu và empty/stale/gap states. Mặc định một tài sản/một series; không thêm terminal kỹ thuật đầy đủ.
- [ ] Contract/backend tests cho nhiều revision/provider/type, unit, availability, không có dữ liệu, khoảng ngày sai, response bị giới hạn; BFF auth/query tests; chart có bảng dữ liệu thay thế.
- [ ] Browser đối chiếu điểm đầu/cuối và đơn vị với API đã ghim. Chỉ chọn thư viện chart khi yêu cầu tương tác chứng minh các primitive hiện có không đủ.

**Nghiệm thu:** Chart biểu diễn đúng một chuỗi giá được xác định, không bị gọi nhầm là hiệu suất danh mục hoặc total return.

### Task 5 — Onboarding, rổ, hồ sơ, lịch sử và console

**Ưu tiên:** P1/P2 theo inventory. **Sau:** Task 1–2. **Files:** `risk-wizard.tsx`, `risk-reassessment.tsx`, `asset-picker.tsx`, `portfolio-lifecycle.tsx`, `portfolio-workspace.tsx`, `auth-form.tsx`, `market-operations.tsx`, `data-refresh.tsx`, `model-operations.tsx`, `operation-ui.tsx`, `job-trace.tsx` khi surface cần thay đổi.

- [ ] Giữ onboarding 3 bước và review cuối, nhóm thông tin trong bước 1; thay jargon bằng câu ngắn. Không thêm preset đầu tư hoặc default câu trả lời rủi ro.
- [ ] Mobile rổ có một danh sách hoạt động theo prototype; search/filter, bulk action, số lượng và draft không mất khi đổi khung. Desktop vẫn chuyển hai phía; mô tả dài mở thêm và đọc được đầy đủ.
- [ ] Đặt nút lưu cạnh phạm vi dữ liệu, thông báo đã lưu đúng phần, hiển thị dirty state và lỗi conflict. Không âm thầm lưu phần đang chỉnh khác.
- [ ] Profile render các giới hạn thực tế và ngữ cảnh đã xác nhận; reassessment dùng so sánh trước/sau, không biến thành dự báo thua lỗ.
- [ ] Lịch sử có nhãn ngày/trạng thái/danh mục và đường trở lại kết quả; console ưu tiên tiến trình/kết quả/lỗi trước chi tiết kỹ thuật, giữ đầy đủ chứng cứ model review.
- [ ] Chạy test liên quan: `asset-picker.test.tsx`, `asset-metadata.test.ts`, `guided-ui.test.tsx`, `risk-universe.test.tsx`, `onboarding-bff.test.ts`, `lifecycle-components.test.tsx`, `control-patterns.test.tsx`, `market-types.test.ts` và các test auth/BFF khi thay form.

**Nghiệm thu:** Không mất tính năng hiện tại; dữ liệu cũ/thiếu vẫn có thể lưu rổ theo rule hiện có nhưng không được dùng để vượt readiness. User hiểu rõ “chọn mã” không bảo đảm mã nhận tỷ trọng.

### Task 6 — Kiểm chứng hành trình và đánh giá với người mới

**Sau:** từng slice tương ứng; không đợi tất cả màn xong mới kiểm.

- [ ] Mỗi slice frontend: chạy test liên quan, `npm --prefix apps/web run typecheck`; build khi sẵn sàng kiểm browser. Chạy full web suite một lần ở mốc tích hợp, không thay kết quả cũ bằng lời khẳng định chưa có evidence mới.
- [ ] Backend chỉ chạy nhóm bị ảnh hưởng và contract checks, sau đó broader suite nếu thay schema/routing/validator dùng chung. Không chạy refresh/train/paid smoke để chứng minh một thay đổi CSS.
- [ ] Dùng các browser gates lifecycle/chat/user-selection/knowledge hiện có theo README, trên stack và fixture test riêng. Các gate có tạo dữ liệu/call provider không được chạy tùy tiện trên tài khoản đang dùng.
- [ ] Kiểm cả hai vai trò operator/reviewer nếu console đã đổi; investor không nhìn thấy hoặc gọi được các mutation vận hành.
- [ ] Kiểm 375/390/768/1024/1440 CSS px đo từ DOM, zoom 200%, keyboard focus/escape/return, contrast, reduced motion, chart table fallback, viewport thấp và thiết bị/bàn phím ảo thật.
- [ ] Tổ chức usability test nhỏ với 5 người mới: (1) tạo kế hoạch, (2) phân biệt rổ và phân bổ, (3) tìm chart, (4) hỏi một mã và kiểm nguồn, (5) hiểu hậu quả chấp nhận mục tiêu. Nếu paused, thử task tính mới bằng prototype/test stack phù hợp; không giả live system sẵn sàng.
- [ ] Mục tiêu để đo sau thiết kế: ít nhất 4/5 người hoàn tất mỗi task không được chỉ đường; ít nhất 4/5 giải thích đúng “vốn kế hoạch ≠ số dư” và “accept ≠ đặt lệnh”. Ghi thời gian, số lần mở sai, đoạn phải đọc lại; đây là mục tiêu, chưa phải kết quả audit.

## 7. Thứ tự ưu tiên và quyết định còn mở

**Đợt đầu:** Task 1 → Task 2 + Task 3 → Task 4A, kiểm Task 6 theo từng phần. Đây là phần cải thiện trải nghiệm rõ nhất dựa trên dữ liệu hiện có. **Đợt tiếp:** Task 5 theo ưu tiên onboarding/rổ/profile, rồi Task 4B. Console polish không chặn chat/investor flow. Holdings/P&L/backtest/frontier là backlog khác, không gộp vào “đổi UI”.

Những điểm cần chốt bằng prototype: vị trí mở result panel trên màn rộng; hành vi lịch sử hội thoại trên mobile; có ẩn bottom nav trong chế độ chat tập trung không; cách mở chi tiết tài sản và các khoảng thời gian chart. Agent không tự thêm feature đầu tư để lấp chỗ trống.

**Rủi ro triển khai:** working tree đang có nhiều thay đổi từ các công việc khác. Trước khi triển khai phải kiểm lại trạng thái code/runtime và tiếp nối đúng bản mới; không reset, ghi đè file, migration hay cấu hình đã có. Paused của HYBRID là cổng định lượng riêng, không phải vấn đề được giải quyết bằng thiết kế.

## 8. Giới hạn của đợt rà soát

Đã đọc toàn bộ nhóm feature hiện có qua routes/components/contracts, nhưng browser chỉ đi qua các hành trình đại diện nêu ở mục 1. Chưa thực hiện mọi mutation, đăng ký mới, screen-reader audit, thiết bị vật lý, usability test với người mới hoặc đo tải. Chưa xác minh live series giá qua investor BFF vì route chưa tồn tại; kết luận chart API dựa trên code/contract. Không chạy lại test suite hoặc provider calls trong đợt lên plan; chưa sửa UI/Figma/backend.
