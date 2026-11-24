# Kiểm định V5 trên 40 ca tiếng Việt chưa dùng để phát triển

**Chưa đạt điều kiện phát hành.** Worker chọn đúng nguồn 38/40 ca (95%), tăng từ 28/40 ở B2. Tuy nhiên, chỉ 8/10 ca trạng thái dùng đúng nguồn thời gian. HTTP tìm đúng claim ở 11/14 câu có đáp án và worker chỉ dẫn đúng claim đã khóa ở 7/14 câu. Chính sách không gửi lệnh ghi ngoài dự kiến đạt 40/40 trên fixture.

## Điều kiện kiểm định

V5 là bộ giữ lại mới sau khi kết quả V4 đã công bố. SHA-256 là `d9051b0e8d47467f9f3ce8cd1c9ac2816e423d13b712e057e740790f06edc66b`. Người giữ bộ câu hỏi dùng cùng mẫu số với V3/V4 gồm 10 trạng thái, 5 đề xuất đã lưu, 3 hỏi lại, 2 chuẩn bị đề xuất, 1 báo giá, 14 câu kiến thức có đáp án và 5 câu thiếu căn cứ. Mỗi lời hỏi cuối khác các bộ trước. ID được gán sau khi xáo thứ tự, để vị trí không biểu thị loại câu hỏi. Nhóm sửa Chat và truy xuất chỉ dùng những bộ đã công bố. [Báo cáo V3](RAG_QUALITY_V3_2026_11_23.md) · [Báo cáo V4](RAG_QUALITY_V4_2026_11_23.md)

Bộ đánh giá là mẫu tổng hợp do cùng người giữ fixture xây dựng trên phạm vi tài liệu đã duyệt. Mỗi ca có cùng trọng số. Tính đúng trên các câu hỏi ở đây không ước lượng tần suất gặp các tình huống trong lưu lượng người dùng thực.

Giữ nguyên corpus `83759093ce950cc5f2a781eddf91049d181408fbdd69016bc931562c57d3d094` và UUID của từng đoạn bằng cách chạy các ranker trên cùng PostgreSQL fixture. Cutoff là `2026-11-23T16:00:00Z`, trừ ca lịch sử. Offline kiểm intent của lời cuối. Chế độ lexical gọi HTTP. Chế độ conversation thực hiện toàn bộ lượt của mỗi kịch bản qua Chat API và worker, sử dụng Knowledge HTTP cùng owner services fixture, khóa provider tắt. Chỉ có gói riêng của reviewer chứa nội dung hội thoại tổng hợp và tài liệu. Telemetry chỉ lưu mã ca, loại nguồn, trạng thái, danh sách claim và thời gian. Việc chấm số ý chính được hỗ trợ tách riêng với việc xác nhận ID và hash trích dẫn.

Giao thức latency đã đăng ký trước khi mở kết quả V5. Hai ranker V4/V5 nhận từng cặp cùng câu hỏi, luân phiên thứ tự gửi, 3 wave × 4 chu kỳ × 38 câu kiến thức V4/V5 (456 quan sát mỗi arm). Phân tách 3 quan sát đầu tiên ở client mới khỏi 453 quan sát warm. P95 dùng nearest-rank. Máy dùng chung và server cache đã được làm ấm.

## Kết quả trên bộ quyết định V5

Tất cả cột trong bảng dùng cùng 40 ca V5. SHA-256 của package Chat V5 là `38276c022903ac8277460d67bf4a11c4749162c5f12ad0652ff7ea15b65d3e79`. SHA của `retrieval.py` là `fae163437121ef03e4377cc5b9c820b90032c8cbcdf5a5414e58c3c821d7ceba` (knowledge-retrieval-v6). Đã kiểm đủ 63 receipt của ma trận: mỗi chế độ và phiên bản có 3 lượt lặp, cùng kết quả chất lượng. Cả bốn bản được chụp ở Git HEAD `ca0043b4a95c8d1fae0a5ec0f373377d307e00fb`, có các thay đổi workspace được ghi nhận riêng theo SHA nội dung.

| Phép đo | B2 | V3 | V4 | V5 |
|---|---:|---:|---:|---:|
| Đúng nguồn theo lời cuối, offline | 22/40 | 29/40 | 31/40 | 32/40 |
| Đúng nguồn trên phản hồi cuối, worker | 28/40 | 34/40 | 35/40 | **38/40** |
| Đúng mã nghiệp vụ | 7/10 | 9/10 | 8/10 | 9/10 |
| Đúng nguồn thời gian của trạng thái | 6/10 | 8/10 | 7/10 | 8/10 |
| Đúng proposal đã ghim, hash facts khớp | 4/5 | 4/5 | 4/5 | 5/5 |
| Tìm trúng claim được phép, HTTP Hit@5 | 8/14 | 10/14 | 11/14 | 11/14 |
| HTTP MRR@5 | 0,292 | 0,595 | 0,667 | 0,667 |
| Worker vào đúng nguồn và tìm trúng claim | 5/14 | 8/14 | 9/14 | 10/14 |
| Thẻ dẫn đúng claim đã khóa | 0/14 | 0/14 | 6/14 | 7/14 |
| Tin nhắn trích nguyên văn claim đã khóa | 0/14 | 0/14 | 6/14 | 7/14 |
| Thiếu căn cứ, từ chối đúng với evidence MISSING | 5/5 | 5/5 | 5/5 | 5/5 |
| Hành động phù hợp, kể cả đề nghị xác nhận | 40/40 | 40/40 | 40/40 | 40/40 |

Theo nhóm nguồn, V5 đúng 9/10 trạng thái, 18/19 kiến thức, 5/5 proposal đã lưu, 3/3 hỏi lại, 2/2 chuẩn bị phân bổ và 1/1 hỏi giá hiện tại. Trong một lượt chạy đủ bộ, worker ghi 55 lần đọc profile, 46 lần đọc Knowledge, 11 lần đọc tóm tắt danh mục, 10 lần đọc trạng thái, 5 lần đọc proposal, 5 lần đọc evidence proposal và 1 lần đọc Market. Có 0 lần gọi provider, 0 lần tạo allocation, 0 lần đọc sai quyền fixture và 0 phản hồi READY sai. Cả 10 ca trạng thái giữ điều kiện chỉ đọc.

- **S28** hỏi nguyên nhân của lần trước. Worker đọc trạng thái hiện tại. Hai thời điểm có cùng mã tạm dừng theo fixture nên phép so khớp mã đạt, phép so nguồn thời gian trượt.
- **S29** cần đọc trạng thái nhưng nhận tóm tắt danh mục. **S10** cần tới tài liệu nhưng nhận câu hỏi làm rõ.
- **S13, S17 và S38** có claim trong corpus nhưng gọi thẳng lexical trả 0 đoạn. Với **S03, S15 và S25**, worker tìm được claim đã khóa nhưng chọn một claim khác cùng chủ đề. Các mã thay thế lần lượt là `model-approval-definition`, `bl-definition` và `mvo-estimation`. Thước đo ID trượt trong ba trường hợp này. Reviewer chấm câu trả lời thực tế để ghi nhận trường hợp một đoạn thay thế vẫn đủ nghĩa.

## Hồi quy trên các bộ đã công bố

Trong các tập đã dùng để phát triển, V5 đúng nguồn 40/40 ở mỗi bộ V2, V3 và V4. Số câu kiến thức trả đúng claim cuối lần lượt là 12/12, 14/14, 14/14. Mỗi bộ từ chối đúng 5/5 và giữ hành động đúng 40/40. Trạng thái được đọc đúng căn cứ ở 11/11 ca V2, 10/10 ca V3 và 10/10 ca V4. Những số liệu này không được gộp vào 40 ca quyết định V5. Các bảng theo ID trong `output/rag-quality-v5/comparison-known-v*.json` ghi nguồn và chuỗi claim trước/sau.

## Chấm ngữ nghĩa

Một agent độc lập đọc 40 câu trả lời và các căn cứ tương ứng. Theo rubric ở V3/V4, **46/49 nhóm phát biểu chính có căn cứ** (93,88%, mục tiêu 95%). Có 31/40 yêu cầu được trả đầy đủ, 3/40 một phần và 6/40 bỏ lỡ. Trên 14 câu kiến thức có đáp án, 8/14 trả đúng ý chính và đủ nội dung (57,1%, mục tiêu 90%). Cả 5 ca cần từ chối nhận được phản hồi phù hợp. S02 nhắc lại lời giải thích tổng quát khi người dùng hỏi về một tỷ trọng cụ thể. S15 nêu định nghĩa Black–Litterman nhưng thiếu quan hệ mà câu hỏi yêu cầu. S28 đọc sai thời điểm. Đây là phép chấm của một reviewer tự động; hai người chấm độc lập chưa xác nhận các ca mơ hồ. Receipt ghim hash packet gốc trong `private/candidate-independent-grades.json`.

## Độ trễ

Phép đối chứng ghép cặp đã đăng ký trước cho p95 warm HTTP tăng **4,05%**, từ 25,899 lên 26,949 ms, trong giới hạn 20%. P50 từ 7,792 lên 7,953 ms. P50/p95 Server-Timing từ 5,416/17,732 lên 5,614/17,919 ms. Theo wave, p95 là 16,653 → 17,064 ms, 27,754 → 33,995 ms và 26,152 → 31,851 ms. Hai wave sau riêng lẻ vượt +20%, còn ngưỡng đăng ký trước dùng toàn bộ 453 lượt warm của mỗi phiên bản. P50/p95 ba lần gọi đầu từ client mới là 7,702/59,660 ms ở V4 và 7,415/17,935 ms ở V5.

Thời gian cuối lượt hội thoại fixture gộp 117 quan sát warm của mỗi phiên bản có p50/p95 B2 33,66/197,21 ms, V3 35,11/160,81 ms, V4 47,39/340,29 ms và V5 37,07/136,30 ms. Ma trận này chạy các worker ở thời điểm khác nhau. Đối chứng HTTP ghép cặp ở trên được dùng để xét ngưỡng hiệu năng.

## Đối chứng với OpenAI trên 18 ca kiến thức thực thi được

Hai stack HTTP dùng đúng mã V5 đã khóa, cùng câu hỏi và cùng corpus. Mỗi ca dùng một hội thoại mới với cutoff thực. Có 14 câu kiến thức trả lời được và 4 câu thiếu nguồn. Hai mươi mốt ca ngoài phạm vi kiến thức và một câu có cutoff lịch sử được loại khỏi mẫu này. Worker chạy từng nhánh một lần. Gói OFF hoàn chỉnh là `openai-offline-complete.json`; giữ lại receipt thử lần đầu dừng do timeout để kiểm tra mà không gộp 17 ca đã chạy dở vào mẫu số.

| Chỉ số | Tắt provider | OpenAI gpt-6-luna |
|---|---:|---:|
| Đạt thước đo đã khóa | 11/18 | 14/18 |
| Câu có đáp án dẫn đúng claim | 7/14 | 10/14 |
| Câu thiếu nguồn từ chối đúng | 4/4 | 4/4 |
| Lượt gọi provider thực tế | 0 | 10 |
| Chi phí ước tính | 0 USD | 0,001961250 USD |

Mười lăm cặp có cùng từng ký tự của câu trả lời cuối và cùng ID citation. Ba ca thay đổi là S03, S15 và S25. Ở cả ba, đoạn đúng đã nằm trong kết quả truy xuất và OpenAI chọn claim đúng theo nhãn khóa. Không có ca đạt ở OFF bị trượt ở ON. Trong 4 câu có đáp án còn trượt, 3 câu không tìm được đoạn nào bằng lexical trực tiếp và 1 câu đã vào sai nhánh. Lần gọi trả phí ghi 11.398 input tokens, 1.073 output tokens và tổng dự phòng 0,0170 USD. Kiểm tra sau restart đọc lại đúng toàn bộ 18 receipt. [Đối chiếu mã bằng chứng từng ca](../../output/rag-quality-v5/paired-provider-summary.json) · [Gói QA riêng chứa hai tin nhắn cuối và citation thực tế](../../output/rag-quality-v5/private/paired-provider-answers.json)

Reviewer độc lập chấm 12/18 câu đầy đủ ý ở nhánh tắt và 13/18 ở nhánh bật. Trên 14 câu có đáp án, mức đủ ý tăng từ 8/14 lên 9/14, dù mức trùng claim khóa tăng 3 ca. Cả hai đoạn thay thế ở S03 đều nêu đúng vai trò reviewer. S15 có đúng thuật ngữ nhưng thiếu chiều tác động. S25 mới trả đủ đại lượng rủi ro người dùng hỏi. Hai nhánh đều có 14/17 nhóm phát biểu chính được hỗ trợ và 4/4 ca từ chối đúng. [Biên bản chấm độc lập](RAG_V5_GROUNDING_REVIEW.md)

## Tách ảnh hưởng của truy xuất hybrid và bộ chọn dùng model

Thử nghiệm độc lập trên cùng 18 câu API, corpus ứng viên giống hệt, PostgreSQL mới ở tmpfs, không dùng cache cũ. Nhánh hybrid chỉ dùng `text-embedding-3-small` (1.536 chiều), tắt toàn bộ model sinh/chọn văn bản. Có 30 lần embedding đoạn tài liệu (1.828 token, 0,00003656 USD) và 17 lần embedding truy vấn (508 token, 0,00001016 USD). Tổng 47 lần, 2.336 token, **0,00004672 USD**. Nhánh thực tế có 17 thẻ HYBRID và 1 lượt yêu cầu chọn danh mục trước khi truy xuất. Có 18/18 receipt còn đúng sau restart.

| Chỉ số ghép cặp qua Chat thật | Lexical, tắt model | Lexical + chọn đoạn OpenAI | Hybrid, tắt model sinh |
|---|---:|---:|---:|
| Tìm trúng claim top 5 đã đi qua router | 10/14 | 10/14 | 13/14 |
| MRR@5 qua Chat, trượt nhận 0 | 0,595 | 0,595 | 0,786 |
| Câu có đáp án đạt ID/coverage/hash | 7/14 | 10/14 | 8/14 |
| Thiếu căn cứ và từ chối đúng | 4/4 | 4/4 | 4/4 |
| Tổng số ca đạt thước đo | 11/18 | 14/18 | 12/18 |
| p50/p95 lượt API thật, ms | 899/1.595 | 2.048/4.165 | 1.166/1.446 |

Cả ba nhánh đều có 18 quan sát, nên nearest-rank p95 của mỗi nhánh là thời gian lớn nhất quan sát được. Đây là mô tả một lượt, mỗi cấu hình một môi trường riêng. Phép kiểm p95 phát hành là đối chứng lặp, ghép cặp HTTP trước đó. Hybrid tìm thêm đúng claim cho ba câu nhưng chỉ S17 chuyển từ trượt sang đạt ở câu trả lời cuối. S38 đổi nội dung và vẫn trượt. S20 và S23 có các đoạn được trả về dù câu hỏi thiếu căn cứ, worker vẫn từ chối hợp lệ. Chưa thử kết hợp hybrid với model chọn đoạn trong cùng lượt. [Bảng so sánh lexical/hybrid từng ca](../../output/rag-quality-v5/paired-hybrid-summary.json) · [Gói chấm riêng với nguyên văn tin nhắn và đoạn dẫn](../../output/rag-quality-v5/private/paired-hybrid-answers.json)

Chấm độc lập toàn bộ 18 lượt hybrid cho 13 câu đầy đủ, 1 câu một phần và 4 câu bỏ lỡ. Có 16/17 nhóm phát biểu được hỗ trợ, 9/14 câu kiến thức đầy đủ và 4/4 câu thiếu căn cứ được từ chối đúng. Ở S38, đoạn được trích đúng nội dung tài liệu nhưng không trả lời điều người dùng hỏi. S13 vẫn từ chối dù đã lấy được đoạn phù hợp. [Đối chiếu ý nghĩa thực tế ở nhánh hybrid](RAG_V5_GROUNDING_REVIEW.md)

## Tái lập

Dùng `scripts/eval_knowledge.py --version v5 --split heldout` với các chế độ `offline`, `lexical`, `conversation`. Dùng script `eval_knowledge_status.py` để nối từng dòng theo ID, kiểm SHA fixture và cutoff, rồi so sánh nguồn → claim trả từ API → claim được dẫn. Dùng `scripts/benchmark_knowledge_arms.py --suites v4 v5` cho phép đo latency ghép cặp. Các vòng cũ được giữ ở `output/rag-status-20261123/`, `output/rag-quality-v3/` và `output/rag-quality-v4/`. Receipt của vòng này nằm ở `output/rag-quality-v5/`.
