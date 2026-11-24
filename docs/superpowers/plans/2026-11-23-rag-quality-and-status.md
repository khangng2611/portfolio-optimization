# Kế hoạch cải thiện Chat và RAG tiếng Việt cho nhà đầu tư

**Ngày rà soát** 23/11/2026 · **Trạng thái** Đã hiện thực bản ứng viên và chạy đối chứng trên Compose `portfolio-auth-demo`. **Chưa đạt điều kiện phát hành.** Kết quả theo từng nguồn, tập khóa và chế độ chạy nằm trong [báo cáo eval](../../software/RAG_QUALITY_EVAL_2026_11_23.md). [Runbook Chromium](../../software/RAG_STATUS_BROWSER_2026_11_23.md) ghi riêng các lượt dùng backend thật và phép đối chiếu receipt sau restart.

Các vòng tiếp nối đã đóng băng từng phiên bản ứng viên và kiểm trên tập mới. Xem [kiểm định V5](../../software/RAG_QUALITY_V5_2026_11_23.md) và [ngân sách, token và receipt OpenAI](../../software/RAG_OPENAI_QUALITY_2026_11_23.md).

**Mục tiêu** Người dùng biết họ có thể làm gì khi một yêu cầu bị chặn, hỏi tiếp được lý do và nhận giải thích có căn cứ. Khi hỏi kiến thức, Chat nhận ra câu hỏi tiếng Việt, tìm đúng đoạn tài liệu và chỉ đưa ra kết luận mà đoạn đó hỗ trợ.

**Kiến trúc và phạm vi** Tái dùng Chat worker Python, Portfolio/Market, Knowledge API, PostgreSQL với full-text search và pgvector, giao diện Web và cơ chế lưu bằng chứng hiện tại. Trạng thái nghiệp vụ, số liệu đề xuất và kiến thức chung có ba nguồn có thẩm quyền khác nhau. Giữ freshness 7 ngày, buffer VFF 5 phiên, reviewer model thủ công, chính sách phát hành HYBRID và phạm vi quyền theo chủ sở hữu. Ngày có dữ liệu, thời điểm dữ liệu khả dụng và thời điểm người dùng hỏi là ba mốc riêng biệt. Giữ nguyên tài khoản, volume, hội thoại, đề xuất và các bằng chứng đã ghim.

Khi triển khai theo từng hạng mục, dùng quy trình `superpowers:executing-plans` hoặc `superpowers:subagent-driven-development`. Tài liệu nền gồm [hợp đồng RAG](../../software/KNOWLEDGE_RAG.md) và [cách giải thích đề xuất](../../software/ALLOCATION_EXPLANATION.md).

## 1. Kết quả rà soát

| Quan sát trên local | Ý nghĩa đối với việc ưu tiên |
|---|---|
| Ngày 23/11 lúc 21:58:44 GMT+7, Chat ghi `FAILED / SYSTEM_PAUSED`. Hai tool được gọi là `get_profile` và `get_portfolio_summary`. Có 0 lần gọi provider, không có hàng knowledge evidence, dependency ID và proposal ID đều trống. | Worker dừng trước bước tạo đề xuất. Web hiển thị tiêu đề lỗi chung và bên dưới mới hiện lý do. Sửa phản hồi nghiệp vụ và khả năng hỏi tiếp sẽ giải quyết tình huống trong ảnh. |
| Chạy riêng `intent_of`: “Tạo đề xuất phân bổ” → `allocation`, “Tại sao chưa tạo được đề xuất?” → `explain`, “Vì sao vậy?” và “Bây giờ tạo được chưa?” → `help`. | Câu hỏi về lần thử vừa rồi dễ bị hiểu thành giải thích một đề xuất đã tồn tại hoặc yêu cầu trợ giúp chung. Đây là phép thử router độc lập. |
| Corpus đang phục vụ có 12 tài liệu, trạng thái `READY`, epoch 1, ID `9aea2cf3-4f12-4c27-a9d1-6a7c2d11e1de`, hash `a8d21c647e8a514510873dce49b8414b7fc32921840c74b53a383b189e9600d4`. | Knowledge đã có tài liệu về freshness, duyệt model, rủi ro và phương pháp. Nội dung freshness trong repo nói chính sách chung. Một đoạn tĩnh không xác định được nguồn nào đang quá hạn trong danh mục đang mở. |
| Bộ v1 đóng băng gồm 20 ca phát triển và 40 ca giữ lại để đánh giá. Trên 40 ca, router khớp nhãn 30/40. Trên 16 câu kiến thức có đáp án, gọi thẳng lexical API tìm trúng ít nhất một claim được phép trong top 5 ở 14/16. Chỉ 8/16 đồng thời đúng intent và trúng claim. Hai ca yêu cầu kết quả trống đạt 2/2. | Có thể cải thiện đáng kể ngay ở bước chọn nguồn. 8/16 là phép giao hai điều kiện từ cùng các dòng kết quả, chưa chấm câu trả lời cuối hay toàn bộ hội thoại. Mẫu 2 ca còn quá nhỏ để kết luận về khả năng từ chối. |
| Ca `A21` hỏi EW có bảo đảm lợi nhuận không, tìm thấy định nghĩa EW nhưng trượt claim cần thiết. Ca `A24` hỏi “Views ML có chắc chắn đúng không?”, không trả đoạn nào. | Cần phân biệt tìm đúng chủ đề với tìm được đoạn trả lời được câu hỏi. Dùng hai ca đã biết cho hồi quy. |
| 28 lượt truy xuất lexical local, HTTP p50/p95 khoảng 15/28 ms, phía service khoảng 4/10 ms. Bốn bộ unit test liên quan đạt 72/72. | Đây là một lần đo lexical local. Chưa đo độ trễ toàn hội thoại, chất lượng embedding, hay độ đúng ngữ nghĩa của câu trả lời cuối trong đợt rà soát này. |

Truy xuất hiện tại đã lọc corpus đang active, tài liệu PUBLIC và `available_at <= as_of` trước khi xếp hạng. Có chuẩn hóa tiếng Việt, tìm từ khóa, tìm vector tùy cấu hình, gộp hạng và trả tối đa 5 đoạn. Alias theo chủ đề chỉ dùng khi truy vấn lexical ban đầu rỗng kết quả. Chat kiểm ID và hash dẫn chứng, có giới hạn độ dài, cơ chế hỏi tiếp theo chủ đề và thử viết lại truy vấn trong phạm vi thí nghiệm. Kiểm đúng ID/hash cho biết đã trích đúng phiên bản đoạn văn. Đánh giá câu trả lời có suy diễn quá nội dung đoạn đó cần một phép chấm riêng. Xem [retrieval](../../../services/knowledge/src/knowledge_service/retrieval.py), [bằng chứng Chat](../../../services/chat/src/chat_service/knowledge.py), [định tuyến và xử lý yêu cầu](../../../services/chat/src/chat_service/workflow.py) và [cách Web hiện lỗi](../../../apps/web/src/components/chat-workspace.tsx).

## 2. Hành vi cần đạt

| Lời người dùng | Căn cứ Chat phải dùng | Kết quả mong đợi |
|---|---|---|
| “Tạo đề xuất phân bổ” khi hệ thống đang tạm dừng | Quyết định cho phép tạo đề xuất tại thời điểm gửi | “Tính năng tạo đề xuất mới đang tạm dừng. Bạn vẫn có thể xem các đề xuất đã lưu.” Chỉ hiện nút mở đề xuất khi có đích mà người dùng được quyền xem. |
| “Vì sao vậy?” ngay sau lượt trên | Kết quả của đúng lượt trong cùng hội thoại và danh mục | Nói nguyên nhân đã xác nhận. Nếu chỉ có mã tạm dừng, nói hệ thống chưa cung cấp lý do chi tiết. Chỉ hiển thị mốc mở lại khi có thông báo có thẩm quyền. |
| “Bây giờ tạo được chưa?” | Đọc lại trạng thái cho phép tạo và readiness hiện tại đối với đúng rổ | Trả tình trạng cùng thời điểm kiểm tra. Câu hỏi này chỉ đọc trạng thái. Khi người dùng thực sự tạo, kiểm lại điều kiện lúc gửi/xác nhận. |
| “Tại sao dữ liệu VFF của tôi chưa dùng được?” | Readiness theo danh mục. Quy tắc trong tài liệu bổ sung phần giải thích | Chỉ nêu VFF stale nếu backend xác nhận. Hiện ngày dữ liệu và ngày khả dụng khi nguồn có cung cấp. Phân biệt buffer 5 phiên và freshness 7 ngày. |
| “Vì sao đề xuất này giữ 20% VFF?” | Bằng chứng và phiên bản hồ sơ được ghim vào đúng proposal của người dùng | Dùng tỷ trọng thực tế và căn cứ đã lưu. Nếu thiếu bằng chứng cho nguyên nhân, nói rõ phần đó. Không suy từ snapshot hiện tại. |
| “Hệ thống dùng Black–Litterman với ML như thế nào?” | Các đoạn tài liệu về phương pháp đã được duyệt | Giải thích bằng tiếng Việt và dẫn nguồn. Tên thuật toán xuất hiện khi người dùng hỏi. EW/MVO giữ vai trò đối chứng chỉ đọc. |

## 3. Thứ tự triển khai

### P0. Đóng băng baseline và bộ tình huống

- [x] Mở rộng harness từ [eval_knowledge.py](../../../scripts/eval_knowledge.py). Giữ fixture v1 và hash hiện có. Bổ sung fixture v2 và hash mới trong [thư mục fixture](../../../tests/fixtures/knowledge). Lưu revision của code, hash corpus, cấu hình truy xuất, chế độ provider, lần chạy, độ trễ và mẫu số cho từng phép đo.
- [x] Tạo tối thiểu 60 kịch bản tiếng Việt gồm 20 kịch bản phát triển và 40 kịch bản nghiệm thu riêng, ít nhất 20 kịch bản nhiều lượt. Chia theo gia đình tình huống để biến thể có dấu, không dấu và diễn đạt lại không nằm ở hai tập khác nhau. Có nhãn nguồn đúng, mã trạng thái hoặc claim đúng, câu được phép nói, hành động được phép và điều bắt buộc phải từ chối. Người giữ tập nghiệm thu khóa đáp án trước khi chỉnh router.
- [x] Bao phủ pause toàn hệ thống, VFF stale riêng một rổ, model đang chờ duyệt, đã mở lại, đề xuất cũ, thiếu bằng chứng, mất dịch vụ, người dùng đổi danh mục và hai chủ sở hữu cùng hỏi một câu. Có ít nhất 10 ca kiến thức trả lời được và 5 ca thiếu căn cứ trong tập nghiệm thu. So sánh kết quả của phiên bản cũ/mới trên cùng điều kiện, có mã ca trượt để tái hiện.

### P1. Trả lời đúng khi nghiệp vụ tạm dừng

- [x] Tại [Chat worker](../../../services/chat/src/chat_service/workflow.py), giữ bước kiểm tra release hiện có. Trả một lượt Chat đã trả lời với kết quả nghiệp vụ có cấu trúc cho trạng thái dự kiến. Ghi mã lý do, phạm vi áp dụng và thời điểm kiểm tra từ nguồn có thẩm quyền. Chỉ thêm trường tùy chọn để lịch sử cũ đọc được. Không tạo job Quant hoặc proposal cho lượt bị chặn.
- [x] Đối chiếu [Portfolio API](../../../services/portfolio/src/portfolio_service/api.py) và [Chat tools](../../../services/chat/src/chat_service/tools.py). Dùng lại quyết định readiness của đúng rổ, kể cả khi nhiều danh mục khác trạng thái. Phân biệt khóa phát hành toàn hệ thống, đầu vào stale, thiếu duyệt và lỗi kết nối. Khi nguồn lỗi, trả “Chưa kiểm tra được trạng thái” và cho thử lại. Không tự trả READY hoặc tự suy ra lý do kiểm định mô hình.
- [x] Cập nhật [Web Chat](../../../apps/web/src/components/chat-workspace.tsx), [nhãn trạng thái Chat](../../../apps/web/src/lib/chat-types.ts) và [lý do readiness](../../../apps/web/src/lib/workspace-state.ts). Dùng cùng thông điệp trên Chat và Web. Render job cũ có `FAILED + SYSTEM_PAUSED` bằng thông điệp nghiệp vụ ngay cả khi chưa có payload mới. Lỗi kỹ thuật vẫn có trạng thái thử lại phù hợp.
- [x] Test worker, Web, gửi lại cùng khóa và hai lượt gửi đồng thời. Nghiệm thu khi đúng thông điệp, 0 proposal/job Quant, 0 lượt truy xuất Knowledge/provider cho trạng thái thuần túy. Với yêu cầu thật đã được xác nhận, luồng kiểm quyền, kiểm readiness và chống tạo lặp vẫn đi qua đường hiện tại.

### P2. Định tuyến tiếng Việt và giữ ngữ cảnh của lượt hỏi

- [ ] Trước khi định tuyến sang tạo đề xuất hoặc giải thích proposal, nhận diện câu hỏi về lần thử vừa rồi và câu hỏi về tình trạng hiện tại. Dùng bản ghi job hoặc phản hồi có cấu trúc gần nhất thuộc đúng chủ, hội thoại, danh mục và xảy ra trước câu hỏi. Hỗ trợ cả job cũ chưa tạo được tin nhắn trả lời. Nếu có nhiều tham chiếu hợp lệ, hỏi lại ngắn gọn. Với “bây giờ”, đọc lại readiness dù lượt trước đã READY.
- [x] Dùng ca phát triển để sửa cách nhận diện câu kiến thức có phủ định, từ đồng nghĩa và câu không dấu. Giữ nguyên các đường đọc giá hiện tại, đọc kết quả proposal và xác nhận hành động. Phối hợp với ngữ cảnh knowledge hiện có trong [knowledge.py](../../../services/chat/src/chat_service/knowledge.py). Câu “vì sao?” sau một đề xuất đã lưu và sau một lần tạo thất bại cần hai ca test khác nhau.
- [x] Chạy hồi quy [test_chat_contextual.py](../../../tests/software/test_chat_contextual.py), [test_chat_knowledge.py](../../../tests/software/test_chat_knowledge.py) và [test_chat_recommendation_context.py](../../../tests/software/test_chat_recommendation_context.py). Kiểm tra câu chỉ hỏi không gửi lệnh ghi, đổi danh mục xóa tham chiếu không còn hợp lệ, thiếu quyền không tiết lộ cả việc proposal có tồn tại.

### P3. Bổ sung tài liệu và chỉnh truy xuất theo loại lỗi

- [ ] Rà từng claim tại [corpus](../../../services/knowledge/corpus). Ưu tiên khoảng trống đã quan sát về giới hạn dự báo và bảo đảm lợi nhuận. Bổ sung các đoạn được duyệt về tạm dừng, dữ liệu đủ mới, độ trễ NAV VFF, quyền reviewer và cách giải thích phương pháp khi được hỏi. Mỗi đoạn có một câu hỏi cụ thể mà nó trả lời được, nguồn, phiên bản và mốc khả dụng. Chỉ đưa quy tắc ổn định vào corpus. Giữ nguyên cơ chế tạo phiên bản, kiểm nội dung, kích hoạt và rollback của operator.
- [x] Đo tuần tự trên tập phát triển với cùng câu hỏi và cutoff: lexical hiện tại → sửa nội dung/chia đoạn → sửa alias hoặc xếp hạng khi còn lỗi. Kiểm tra riêng truy vấn đã ra đúng chủ đề nhưng sai claim như A21. Chỉ xét vector hoặc rewrite khi các thay đổi rẻ hơn còn bỏ sót các họ câu hỏi cụ thể. Đo riêng số lần gọi, chi phí, latency và tác động lên câu thiếu bằng chứng. Không mở rộng ngưỡng vector/top-k hoặc bật provider toàn cục theo mặc định.
- [x] Tại [retrieval.py](../../../services/knowledge/src/knowledge_service/retrieval.py), giữ các bộ lọc PUBLIC, active corpus, `available_at`, điều kiện tương thích embedding, ngân sách và giới hạn bằng chứng. Tại Chat, kiểm từng phát biểu quan trọng có claim thực sự hỗ trợ. Nếu thiếu, trả lời phần có bằng chứng và nói rõ phần còn thiếu. Kiểm thử tài liệu bị thu hồi giữa lượt, nguồn tương lai và đoạn đúng chủ đề nhưng không trả lời được câu hỏi.

### P4. Chạy đối chứng, nghiệm thu trên Web và theo dõi

- [ ] Chạy baseline/v2 theo ma trận offline, lexical API thật, hội thoại không dùng provider và browser trên Compose. Provider/vector là một báo cáo riêng theo consent và ngân sách được duyệt. Ghi rõ chế độ chưa chạy. Đo p50/p95 theo từng luồng, tách cold/warm, chạy tối thiểu 3 lượt cùng cấu hình. Ghi số tool/provider, kết quả định tuyến, trạng thái từ chối và phản hồi sai nguồn dưới dạng mã. Không ghi prompt thô, số tiền hay thông tin danh mục vào báo cáo theo dõi.
- [ ] Trên browser mở lượt bị dừng, hỏi “vì sao?”, rồi “bây giờ tạo được chưa?”, chuyển danh mục, hỏi một câu kiến thức, mở lại một đề xuất cũ và reload. Đối chiếu timestamp, nguồn, quyền, số job và ID/hash đã ghim. Chạy nhánh READY và chuyển paused → READY bằng fixture/service test cô lập khi stack thật đang khóa. Ghi rõ kết quả nào từ fixture và kết quả nào từ backend thật. Không đổi cờ phát hành hoặc làm cũ snapshot đang dùng chỉ để test.
- [ ] Phát hành phần thông báo/định tuyến trước, corpus sau khi operator duyệt. So sánh tín hiệu trước/sau gồm tỷ lệ sai nguồn, lượt người dùng hỏi lại ngay sau khi bị chặn và tỷ lệ thiếu căn cứ. Khi hồi quy, quay về phiên bản Chat/Web tương thích hoặc kích hoạt lại corpus trước bằng cơ chế vận hành hiện hữu. Mở lại hội thoại và proposal cũ để kiểm persistence sau restart. Không xóa volume, sửa log lịch sử, tự duyệt model hay ghi đè evidence.

## Trạng thái bàn giao ngày 23/11

| Hạng mục | Kết quả |
|---|---|
| P0 | Khóa hash v2 trước khi sửa router, 20 ca phát triển và 40 ca nghiệm thu. Bộ v1 tiếp tục dùng cho hồi quy. |
| P1 | Worker trả trạng thái nghiệp vụ, thời điểm kiểm tra và mã lý do. API đã kiểm gửi đồng thời cùng khóa và quyền chủ sở hữu. Hai rổ có readiness khác nhau qua cùng đường đọc trong service test. |
| P2 | Đã hiện thực phân giải lịch sử và đọc lại readiness. Trên tập khóa, phản hồi đúng nguồn 28/40, trạng thái đúng 8/11. Cổng chất lượng còn mở. |
| P3 | Corpus ứng viên 13 tài liệu, 30 claim. Đoạn trích đã qua bộ lọc quyền, cutoff và kiểm lại corpus. Hit@5 đạt 8/12, dẫn đúng claim trong câu trả lời đạt 2/12. Một URL ghim cần được công bố để người dùng mở được. |
| P4 | Đã chạy ba lần offline, lexical, worker, HTTP Compose trên tập phù hợp và Chromium. Receipt cũ khớp sau restart. Độ trễ lexical cùng corpus vượt ngưỡng trong phép đo chốt. Chưa đo cold-start toàn stack, provider/vector thật hoặc hành vi người dùng sau rollout. |

Cổng phát hành yêu cầu lần lượt rà lỗi chọn nguồn, đo trên một tập giữ lại mới và chấm ý chính dựa trên bằng chứng. Hai người rà soát đối chiếu các ca mơ hồ. Operator kiểm nguồn tại Git revision trước khi kích hoạt corpus. Khi thử rollout, dùng cùng khoảng quan sát trước và sau, bỏ các hội thoại nghiệm thu, chỉ tổng hợp mã nguồn thực tế, tỷ lệ thiếu căn cứ và tỷ lệ hỏi tiếp sau trạng thái bị chặn. Khi có hồi quy, phục hồi image Chat/Web/Portfolio đã ghim hoặc dùng thủ tục kích hoạt lại corpus cũ trong [runbook Knowledge](../../software/KNOWLEDGE_RAG.md).

## 4. Tiêu chí nghiệm thu đề xuất

| Chỉ số trên tập khóa | Điều kiện đạt trước khi phát hành |
|---|---|
| Phân đúng nguồn (trạng thái, hành động, tài liệu, proposal, hỏi lại) | ≥95% tổng số kịch bản. Báo cả tử số/mẫu số từng nhóm. Tất cả ca pause/stale, sai chủ và câu hỏi chỉ đọc phải đúng. |
| Tìm đúng claim | Hit@5 ≥90% trên câu kiến thức có đáp án. Ghi MRR@5 theo hạng đầu tiên của claim hợp lệ, bằng 0 khi trượt. Chấm cả chuỗi router + retrieval trên cùng câu và yêu cầu ≥90% đúng cả hai. |
| Trả lời được và có căn cứ | Người rà soát đối chiếu từng phát biểu chính với facts/đoạn trích. ≥95% phát biểu được hỗ trợ và ≥90% câu có đáp án được trả đúng, đầy đủ ý chính. Hai người chấm các ca bất đồng hoặc mơ hồ. 100% ca thiếu căn cứ không bịa lý do, ngày mở lại, giá hay tỷ trọng. |
| Tính đúng trạng thái và bảo toàn dữ liệu | 0 báo READY sai, lộ tài nguyên ngoài quyền, gọi ghi từ câu chỉ hỏi hoặc tạo job Quant khi paused. Web và Chat đồng nhất cùng đầu vào. Đề xuất và hội thoại cũ mở lại đúng ID, tỷ trọng và tham chiếu. |
| Thời gian và chi phí | 0 lượt provider cho câu trạng thái thuần túy. Đề xuất ngưỡng p95 lexical không tăng quá 20% so baseline đo lại cùng máy/corpus, đồng thời vẫn trong timeout hiện hành. Báo p95 đầu-cuối và chi phí theo chế độ. Chỉ cân nhắc rollout vector/rewrite sau khi đo được lợi ích và nằm trong ngân sách. |

Năm ca chặn phát hành cần xem thủ công gồm trạng thái hiện tại bị nhầm với lịch sử, sai chủ/danh mục, câu hỏi tạo nhầm job, tài liệu đúng chủ đề nhưng kết luận không có căn cứ và proposal cũ bị giải thích bằng dữ liệu mới. Tập v1 đã được phân tích nên tiếp tục dùng để phát hiện hồi quy. Kết luận cải thiện dựa trên tập v2 khóa riêng, công bố cả các ca trượt và phạm vi chưa kiểm chứng.

## 5. Lệnh tái lập baseline hiện tại

Chạy từ gốc repo. Lệnh lexical cần Knowledge API và local auth của Compose đang chạy. Hai báo cáo tạm nằm ngoài dữ liệu ứng dụng.

```sh
audit_dir=$(mktemp -d)
.venv-software/bin/python scripts/eval_knowledge.py --mode offline --output "$audit_dir/offline.json"
.venv-software/bin/python scripts/eval_knowledge.py --mode lexical --output "$audit_dir/lexical.json"
.venv-software/bin/python -m pytest -q tests/software/test_chat_knowledge.py tests/software/test_knowledge.py tests/software/test_chat_contextual.py tests/software/test_concise_explanation.py
```

Bước Web khi triển khai dùng [test trạng thái lượt Chat](../../../apps/web/tests/chat-turn-status.test.tsx), [test dẫn chứng](../../../apps/web/tests/chat-knowledge.test.tsx) và [luồng browser Chat](../../../apps/web/tests/browser/chat.e2e.ts). Lưu receipt từng chế độ riêng và các ID kiểm thử vào thư mục output mới. Hoàn tất kế hoạch khi P1–P4 đạt các điều kiện tương ứng trên bộ dữ liệu P0 và người vận hành có thể tái lập kết quả.
