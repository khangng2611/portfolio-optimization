---
target: "Review design hiện tại Portfolio Optimization: thân thiện lần đầu, cân đối component, tham khảo thị trường, tránh template chung"
total_score: 24
max_score: 40
na_heuristics:
p0_count: 0
p1_count: 2
target_identity: "file:/Users/nguyenkhang/Documents/MASTER/Thesis/portfolio-optimization/apps/web/src/app/home.tsx"
target_fingerprint: "sha256:46d2869dd3f553d482147e187c9fc44e5aa3ab40b44620b5b2c213085a40bba7"
target_path: /Users/nguyenkhang/Documents/MASTER/Thesis/portfolio-optimization/apps/web/src/app/home.tsx
timestamp: 2026-11-06T14-54-46Z
slug: apps-web-src-app-home-tsx
closed: true
---
Method: dual-agent (A: /root/design_assessment_a · B: /root/design_assessment_b)

**Kết luận:** UI đã có đặc trưng của sản phẩm phân bổ danh mục, nhưng trải nghiệm cho người mới còn thiếu dẫn dắt. Cần ưu tiên điểm bắt đầu, chất lượng câu trả lời rủi ro và khả năng hiểu lựa chọn trước khi polish thêm spacing.

Phạm vi: Figma trong file đã cung cấp, bản production localhost:3000, các màn nhà đầu tư từ tạo danh mục → tạo/xem đề xuất → so sánh → hồ sơ/hội thoại. Đối chiếu spec phần 11–12 và implementation status. Hai đánh giá độc lập dùng dữ liệu mô phỏng, không tạo danh mục, gửi job, accept hoặc gọi LLM thật. Đây là heuristic review, chưa phải usability test với người dùng thực.

**Đánh giá tính đặc thù**

Không nên gọi toàn bộ UI hiện tại là một template dashboard. Wizard ba bước, bảng quản lý, danh sách chọn, review phân bổ kèm vùng quyết định, bảng chênh lệch và chat có ngữ cảnh đã phục vụ các công việc khác nhau. Những phần tạo cảm giác chưa được thiết kế kỹ là bề rộng thiếu nhất quán, lời nhắc nghiệp vụ lặp lại và ngôn ngữ hệ thống chiếm chỗ của giải thích cho nhà đầu tư.

**Điểm sức khỏe thiết kế: 24/40 — mức chấp nhận được, còn cải thiện đáng kể cho người mới.** Mỗi tiêu chí chấm 0–4; đây là nhận định chuyên môn, không phải tỷ lệ hoàn thành tác vụ.

| Tiêu chí Nielsen | Điểm | Nhận xét chính |
|---|---:|---|
| Trạng thái hệ thống | 3 | Rõ bước, điều kiện dữ liệu và trạng thái đề xuất |
| Ngôn ngữ gần thực tế | 2 | Policy, mức ngại rủi ro và mã bộ tài sản còn khó hiểu |
| Chủ động và quay lại | 3 | Có sửa/quay lại; tạo và chấp nhận tách riêng |
| Nhất quán | 3 | Hệ thị giác ổn; tên màn và tiếng Anh/Việt còn lệch |
| Ngăn ngừa sai sót | 2 | Câu trả lời rủi ro chọn sẵn làm yếu bước xác nhận |
| Nhận biết thay vì nhớ | 2 | Hồ sơ thiếu phần giải thích/câu trả lời đã ghi nhận |
| Hiệu quả thao tác | 2 | Có tìm/lọc; chọn danh mục trong chat còn qua select phân trang |
| Tối giản và phân cấp | 3 | Ít trang trí; màn rộng còn tách xa nội dung liên quan |
| Phục hồi lỗi | 2 | Có retry/conflict; trạng thái tài khoản mới chưa dẫn đúng bước |
| Trợ giúp theo ngữ cảnh | 2 | Giải thích ranh giới hệ thống tốt hơn giải thích lựa chọn đầu tư |
| **Tổng** | **24/40** | Không phát hiện P0 trong các tình huống đã quan sát |

**Điểm nên giữ**

- Phân biệt vốn kế hoạch, tỷ trọng mục tiêu và tài sản thực tế; không dựng KPI/hiệu suất chưa có dữ liệu.
- Phân bổ và chênh lệch tài sản là trọng tâm; cảnh báo khác cơ sở đầu vào rõ, tạo đề xuất và chấp nhận mục tiêu là hai quyết định.
- Be Vietnam Pro, xanh/kem, disclosure metadata và consent LLM mặc định tắt tạo nền tảng nhất quán.

**Năm vấn đề ưu tiên**

**1. [P1] Tài khoản mới chưa có bước bắt đầu ngay tại màn đầu.**
Đã tái hiện: Tổng quan của tài khoản không có danh mục vẫn yêu cầu “Chọn danh mục”, hiển thị ô tìm kiếm, nhắc tạo kế hoạch nhưng chỉ đưa link “Quản lý danh mục”. Người mới phải suy ra đường vòng để tạo đối tượng mà màn này yêu cầu chọn.
Sửa: zero-state không có danh mục và không có bộ lọc phải có CTA “Tạo danh mục đầu tiên”, giải thích ngắn ba bước đánh giá → xác nhận → tạo. Giữ riêng trạng thái tìm kiếm không có kết quả.
Bằng chứng: [trạng thái tài khoản mới](/Users/nguyenkhang/Documents/MASTER/Thesis/portfolio-optimization/output/playwright/design-review-20261106/a/fresh-empty-overview-1440.png).
Hướng xử lý: $impeccable onboard.

**2. [P1] Bảng hỏi rủi ro đang biến mặc định thành câu trả lời.**
Đã tái hiện: ba nhóm có sẵn lựa chọn; không chạm radio vẫn đi tới màn review đầy đủ. Việc người dùng xác nhận cuối cùng chưa chứng minh họ đã chủ động trả lời từng câu, tạo rủi ro ghi nhận giả định của UI thành khả năng chấp nhận rủi ro của họ.
Sửa: bắt đầu ba nhóm ở trạng thái chưa trả lời, yêu cầu chọn chủ động, báo thiếu tại từng nhóm và giữ đáp án khi quay lại. Giữ nguyên câu hỏi, mapping, cách chấm và xác nhận backend; không thêm chức năng bỏ qua.
Bằng chứng: [review khi chưa chọn lại đáp án](/Users/nguyenkhang/Documents/MASTER/Thesis/portfolio-optimization/output/playwright/design-review-20261106/a/risk-review-untouched-1440.png), [risk-wizard.tsx](/Users/nguyenkhang/Documents/MASTER/Thesis/portfolio-optimization/apps/web/src/components/risk-wizard.tsx:7).
Hướng xử lý: $impeccable harden.

**3. [P2] Có mô tả phương pháp nhưng chưa giúp người mới hiểu lựa chọn.**
Đã quan sát: thẻ EW/MVO/BL+ML nói về quy trình và điều kiện; hồ sơ chủ yếu có nhãn “Cân bằng”, Policy ID, mức ngại rủi ro và giới hạn. Chưa đủ để hiểu phương pháp dựa vào gì, nhãn hồ sơ có ý nghĩa gì. Tác động đến bỏ cuộc cần kiểm chứng bằng user test.
Sửa: tên dễ hiểu trước, mã phương pháp sau; thêm “Cách hoạt động / Giới hạn” ngắn và đúng định nghĩa. Đưa thông tin rủi ro/đáp án đã lưu ra lớp đọc được khi API thực sự trả về; legacy thiếu dữ liệu phải nói rõ. Metadata kỹ thuật giữ trong disclosure. Tên/diễn giải tài sản và facts thị trường chỉ dùng khi có nguồn canonical.
Hướng xử lý: $impeccable clarify.

**4. [P2] Màn rộng và mobile chưa có cùng quy tắc tổ chức theo tác vụ.**
Đã quan sát: ở 2560px, form wizard nằm trái nhưng action dock dùng lane khác; vùng chọn phương pháp và thẻ phân bổ chat kéo quá rộng. B đo lane tổng quan 2304px, quản lý 1600px, bộ chọn 864px. Khác chiều rộng tự nó không phải lỗi; vị trí đọc và thao tác bị tách rời mới là vấn đề. Mobile review dài 3279px trong fixture, gồm phân bổ, cơ sở, diagnostics và lịch sử; CTA vẫn thấy được, cuộn không bị khóa.
Sửa: căn dock theo form; giới hạn phần đọc/thẻ kết quả trong chat; để bảng quản lý rộng; tách/disclose lịch sử và nội dung nguồn đúng ngữ cảnh. Không kéo giãn mọi box để lấp chỗ trống.
Bằng chứng: [wizard màn rộng](/Users/nguyenkhang/Documents/MASTER/Thesis/portfolio-optimization/output/playwright/design-review-20261106/a/create-2560.png), [chat màn rộng](/Users/nguyenkhang/Documents/MASTER/Thesis/portfolio-optimization/output/playwright/design-review-20261106/a/chat-2560.png).
Hướng xử lý: $impeccable layout, sau đó $impeccable polish.

**5. [P2] Tổng quan chưa phân biệt “chưa chấp nhận” và “chưa có đề xuất”.**
Đã tái hiện: cùng fixture có hai đề xuất, Tổng quan vẫn mời “Tạo đề xuất đầu tiên”. Điều này dẫn người quay lại về tính mới thay vì xem lại kết quả sẵn có.
Sửa: dùng proposal_count để hiển thị “Xem các đề xuất” khi đã có; tạo mới là hành động thứ cấp. Không lấy số lượng đề xuất làm KPI, không suy ra tất cả đề xuất đều còn hiệu lực hoặc chưa từng được chấp nhận.
Bằng chứng: [PortfolioOverview](/Users/nguyenkhang/Documents/MASTER/Thesis/portfolio-optimization/apps/web/src/components/portfolio-workspace.tsx:35).
Hướng xử lý: $impeccable clarify.

**Tải nhận thức và cảm giác sử dụng**

Theo checklist Impeccable, 2/8 tiêu chí còn yếu: trọng tâm bị chia giữa tạo mới và lịch sử/so sánh; hồ sơ buộc người dùng nhớ lại ý nghĩa/đáp án. Mức tải cấu trúc vừa. Không coi 42 dòng dữ liệu hoặc một select nhiều lựa chọn là bằng chứng quá tải một cách máy móc.

Hành trình hiện tại: mở đầu yên tĩnh → vướng trạng thái tài khoản mới → wizard tạo cảm giác có hướng dẫn nhưng mặc định gây hiểu nhầm → băn khoăn trước phương pháp → review phân bổ rõ và đáng tin hơn. Cần cải thiện đoạn trước quyết định, giữ điểm mạnh ở review.

- **Jordan, lần đầu:** dễ lạc tại zero-state và đọc thông số hệ thống như lời tư vấn.
- **Alex, dùng lặp lại:** được lợi từ bảng/so sánh; thiếu lối đi thẳng tới đề xuất đã có và thẻ chat quá rộng làm khó quét.
- **Casey, mobile:** composer/action cố định hữu ích; nội dung dài và helper nhỏ cần kiểm tra trên máy thật. Chưa kết luận lỗi bàn phím ảo hay screen reader.

**Bài học từ thị trường**

| Nguồn chính thức | Điều nên học và áp dụng |
|---|---|
| [Wealthfront](https://www.wealthfront.com/investing) | Nội dung công khai dẫn từ tình huống/mục tiêu và vài câu hỏi; dùng để cải thiện onboarding, không sao chép tính năng giao dịch tự động |
| [Portfolio Lab](https://www.portfoliolab.app/tools/portfolio-optimizer) | Tách cấu hình, constraints, mục tiêu và kết quả; tên dễ hiểu đi kèm tên phương pháp |
| [Portfolio Visualizer](https://www.portfoliovisualizer.com/optimize-portfolio) | Phân biệt dữ liệu đầu vào, mục tiêu và constraints tùy chọn; không đưa form chuyên gia dài vào onboarding |
| [Diversiview](https://diversiview.online/blog/the-new-diversiview-dashboard/) | Liên kết hồ sơ rủi ro, kết quả gần nhất và lịch sử; bài dashboard 2024 là tham khảo lịch sử |
| [Koyfin](https://www.koyfin.com/features/portfolio-tools/) | Nhóm dữ liệu và summary rows để đọc bảng nhanh; chỉ áp dụng cho dữ liệu MVP thực có |
| [TCWealth](https://www.tcbs.com.vn/ca-nhan/san-pham/tcwealth/) | Ngôn ngữ mục tiêu tài chính và khẩu vị rủi ro; lần lấy nội dung chủ yếu thấy giới thiệu/navigation, chưa xác minh hành trình trong tài khoản |
| [Composer](https://www.composer.trade/learn/creating-and-editing-algorithmic-trading-strategies-with-composer) | Liên hệ cấu hình với kết quả và giữ bản gốc khi thử thay đổi; không bổ sung strategy builder/backtest/giao dịch vào MVP |

Các nguồn được đọc ngày 06/11/2026 ở phần công khai; chưa walkthrough sản phẩm sau đăng nhập. Các đề xuất áp dụng là suy luận thiết kế từ nguồn, không phải bằng chứng về hiệu quả usability của đối thủ.

**Design system và Figma**

Giữ font, màu xanh, light mode và các control hiện tại. Vì form, dock và nội dung đang dùng giới hạn bề rộng khác nhau, nên bổ sung quy ước layout theo tác vụ: wizard/form, phân tích/ra quyết định, bảng vận hành và hội thoại. Đây là lý do cho thay đổi quy ước layout; không đề xuất thay hệ màu/font.

Figma đã có bố cục riêng và V2.2 đã phân biệt quản lý/chọn danh mục. Tuy nhiên các frame V2 cũ và runtime hiện tại còn lệch ở shell, composer cố định, typography và pagination. Cần chỉ rõ frame hiện hành cho từng tác vụ trước vòng triển khai tiếp, giữ các phiên bản trước để đối chiếu.

Những điểm nhỏ: thống nhất “Xem lại” thay “Review”; đổi tên “Hồ sơ & cài đặt” theo đúng chức năng hiện có; hai nút mở A/B nên ngang vai trò khi không có cơ sở ưu tiên; đặt tên khác nhau cho nguồn của đề xuất và hướng dẫn toàn hệ thống. Ô vốn có thể thêm giá trị VND định dạng để dễ kiểm tra.

**Giới hạn và thứ tự triển khai**

Chưa xác minh screen reader, bàn phím ảo, zoom trình duyệt và usability với người thật; chưa đánh giá sâu màn data operator/model reviewer. Không đánh giá hiệu quả thuật toán hoặc chất lượng lời giải thích LLM thật từ fixture.

Ưu tiên xử lý P1 trước, sau đó giải thích theo ngữ cảnh, quy tắc layout và trạng thái đề xuất; kết thúc bằng polish và review lại. Không bổ sung NAV, Sharpe, expected return, hiệu suất thực tế, broker import, tự giao dịch hoặc model promotion từ chat khi chưa có nghiệp vụ/dữ liệu tương ứng.
