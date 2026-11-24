# Kiểm định tiến cứu V4 cho Chat tiếng Việt

**Chưa đạt điều kiện phát hành.** Trên 40 ca V4 mới khóa, worker hiện trả đúng nguồn 33/40 và trích đúng claim 8/14 câu kiến thức có đáp án. Mục tiêu tương ứng là ít nhất 38/40 và 13/14. Reviewer độc lập chấm 7/14 câu kiến thức hoàn chỉnh.

Vòng này giữ nguyên kết quả V3. Nhóm triển khai được dùng V3 để phát triển sau khi người giữ bộ đánh giá đã khóa V4. V4 có 40 kịch bản mới, SHA-256 `29877078d894cc6a42b6cb8120b4613144c4c34a310e635001e7ed25ce988c6d`. Tất cả lời hỏi cuối đều khác V2 và V3. Câu hỏi gồm lối nói đời thường, câu ngắn, câu không dấu và câu kỹ thuật cụ thể. Có 10 ca trạng thái, 5 đề xuất cũ, 3 ca cần hỏi lại, 2 yêu cầu chuẩn bị phân bổ, 1 câu giá thị trường, 14 câu kiến thức có đáp án và 5 câu thiếu căn cứ. Các ca trạng thái và tham chiếu dùng lượt trước, thay đổi chủ/danh mục và trạng thái đã ghim khi cần. [Báo cáo V3](RAG_QUALITY_V3_2026_11_23.md) · [Fixture](../../tests/fixtures/knowledge)

## Giao thức

- Chạy lại B2 và ứng viên V3 đã đóng băng trên V4 ở ba chế độ offline, lexical HTTP và hội thoại worker không dùng provider. Lặp 3 lần mỗi bộ và mỗi chế độ. Đóng băng ứng viên tiếp theo rồi đo trên đúng V4. V2/V3 đã mở dùng để kiểm hồi quy.
- Tiếp tục dùng cùng corpus công khai đã duyệt trong fixture, cùng UUID chunk và cùng mốc `2026-11-23T16:00:00Z`. Ca có cutoff lịch sử dùng `2000-01-01T00:00:00Z`. Các backend thuộc chủ sở hữu và trạng thái thay đổi được cung cấp qua fixture. Nội dung trả lời cuối được đối chiếu với API retrieval, citation được chọn và các facts ghim của đề xuất. Mỗi arm có SHA của package Python đã dùng.
- Khóa trước phép đo độ trễ ghép cặp V3 → V4. Hai ranker dùng chung PostgreSQL cô lập và corpus active. Mỗi wave dùng 38 truy vấn kiến thức V3/V4, lặp bốn vòng, đảo thứ tự A/B ở từng truy vấn. Có ba wave, 456 quan sát mỗi arm, trong đó 453 quan sát warm. Báo p50/p95, Server-Timing và p95 theo wave. Không khởi động lại PostgreSQL hoặc xóa cache.
- Receipt kỹ thuật chỉ chứa mã ca, nguồn, ID claim, counters hoặc thời gian. Gói chấm ngữ nghĩa tách riêng, chỉ dùng hội thoại và facts tổng hợp, được tạo sau khi ứng viên đã khóa. Mẫu kiểm tra có provider và hạn mức chi phí do người phụ trách riêng thực hiện. Các mẫu số theo chế độ cần được ghi riêng.

## Kết quả khóa trên V4

Các SHA của package Chat B2, V3 và V4 lần lượt là `50c5e201264a9593b757022fccd560e85e42a043b66bdda26e9782dfaccda3aa`, `147c2d3b9a37e138000dd9a91e194129a8dac95356130cdd50e3efe4283ca820` và `775166e14deb9a1448251920fff3c3548395473a3561110c97668bb0aac1ed2e`. Ranker V4 mang phiên bản `knowledge-retrieval-v5`, SHA của `retrieval.py` là `878698a4a3fe91918958f9115283356754f8910c97bd9da7f4e871e3b9b1d672`. Corpus SHA-256 `83759093ce950cc5f2a781eddf91049d181408fbdd69016bc931562c57d3d094`. Các chỉ số chất lượng sau lặp lại như nhau trong cả ba lượt.

| Phép đo | B2 | V3 | V4 |
|---|---:|---:|---:|
| Nguồn theo lời hỏi cuối, offline | 21/40 | 28/40 | 27/40 |
| Nguồn trên phản hồi cuối của worker | 27/40 | 34/40 | 33/40 |
| Mã trạng thái và nguồn thời gian đúng | 8/10 | 9/10 | 9/10 |
| Đúng đề xuất và hash facts đã ghim | 4/5 | 4/5 | 4/5 |
| Đúng claim trong top 5 của API | 8/14 | 10/14 | 11/14 |
| MRR@5 | 0,339 | 0,714 | 0,786 |
| Đúng nguồn và tìm trúng claim trong worker | 6/14 | 10/14 | 10/14 |
| Citation cuối có claim đúng | 0/14 | 1/14 | 8/14 |
| Tin nhắn trích nguyên văn claim đúng | 0/14 | 1/14 | 8/14 |
| Từ chối có căn cứ với thẻ MISSING | 3/5 | 4/5 | 4/5 |
| Hành động phù hợp, kể cả thẻ xác nhận | 40/40 | 40/40 | 40/40 |

Trên ứng viên V4, số phản hồi đúng nguồn theo nhóm là trạng thái 9/10, hành động 1/2, đề xuất đã lưu 4/5, hỏi lại 3/3, thị trường 1/1, kiến thức 15/19. N06 về trạng thái, N12 về proposal, N19 là yêu cầu tạo và N23, N24, N35, N37 về kiến thức đi nhầm nguồn. N19 từng được B2 và V3 phân giải đúng. Toàn bộ 5 ca thiếu bằng chứng nhận 0 đoạn khi gọi trực tiếp HTTP, nhưng N37 nhận trợ giúp chung khi đi qua worker. Không có lần ghi allocation, báo READY sai, đọc proposal ngoài quyền hoặc gọi provider trong nhánh này.

N23, N32, N35 trượt top 5 trực tiếp. Với N28 và N34, API đã trả claim cần thiết và worker nhận ra câu kiến thức, nhưng citation cuối bỏ mất ý cần trả lời. N28 không có đoạn nào được chọn, N34 chọn một claim khác cùng về MVO. Theo dõi từng dòng bằng `comparison-from-b2-v4.json` và `comparison-from-v3-v4.json`, gồm nguồn, danh sách claim đã trả về và danh sách claim đã dùng.

Đối với bộ đã biết, V4 giữ V2 đúng nguồn 40/40, trích đúng 12/12 và từ chối 5/5. Trên V3 đã dùng để phát triển, V4 đạt 38/40 nguồn, 14/14 trích đúng và 5/5 từ chối. Hai ca hỏi lại trạng thái V01 và V02 rơi vào hỏi làm rõ. Receipt theo ca là `comparison-known-v2.json` và `comparison-known-v3.json`. Các kết quả này phục vụ hồi quy.

## Chấm độc lập trên phản hồi cuối

Một agent độc lập đọc 40 câu trả lời V4 và căn cứ trong packet synthetic. Có **37/39 nhóm phát biểu chính được hỗ trợ** (94,9%, dưới ngưỡng 95%). Reviewer chấm 29/40 ca đầy đủ ý, 2/40 một phần và 9/40 bỏ lỡ. Trên 14 câu kiến thức trả lời được, 8/14 truyền đạt ý chính đã khóa và 7/14 trả đủ nội dung người hỏi yêu cầu. Bốn trong năm câu thiếu căn cứ được từ chối đúng. Điểm trên do reviewer tự động chấm và chưa qua đối chiếu của hai người. Receipt `private/candidate-independent-grades.json` ghim đúng hash gói câu trả lời.

## Thời gian

P95 warm HTTP trên cùng dữ liệu tăng **1,23%** (V3 13,410 ms → V4 13,575 ms), trong giới hạn 20%. Có 453 phép đo warm/arm. P50 lần lượt là 7,122 và 7,325 ms. Theo Server-Timing, p50/p95 là 4,948/9,453 ms và 5,112/9,968 ms. Ba đợt warm cho p95 11,626 → 12,467 ms, 13,722 → 14,902 ms và 14,560 → 13,457 ms. Với 3 lần gọi đầu, p50/p95 HTTP là 10,330/33,324 ms và 9,967/10,101 ms. Thời gian worker fixture trên tập V4 gộp 117 lượt warm là B2 35,96/475,58 ms, V3 29,94/83,45 ms và V4 28,70/105,56 ms. Các lần chạy worker không ghép cặp theo thời điểm nên độ trễ giữa chúng chịu ảnh hưởng tải nền.

## Đối chứng có và không có provider trên cùng 18 hội thoại thật

Hai stack HTTP thử nghiệm dùng cùng mã Chat V4, corpus và cùng 18 câu ở cutoff hiện tại. Mỗi nhánh chạy một lần. Mẫu gồm đủ 14 câu kiến thức có đáp án và 4 câu thiếu nguồn khả thi. Loại 21 ca ngoài phạm vi kiến thức và 1 ca cần truy vấn quá khứ. Nhánh có provider dùng OpenAI gpt-6-luna với bộ kiểm quote. Bộ so sánh nối theo ID, kiểm khớp câu hỏi và nhãn rồi so sánh chính nội dung tin nhắn và các claim thực sự được dẫn.

| Chỉ tiêu trên mẫu ghép cặp | Tắt provider | Bật provider |
|---|---:|---:|
| Phản hồi đạt nhãn tự động | 11/18 | 14/18 |
| Câu có đáp án trả đúng theo thước đo đã khóa | 8/14 | 10/14 |
| Câu thiếu nguồn từ chối đúng | 3/4 | 4/4 |
| Lượt gọi thực tế | 0 | 16 |
| Chi phí ước tính theo token | 0 USD | 0,002469875 USD |

Có 14/18 cặp giữ nguyên từng ký tự của câu trả lời và 16/18 giữ nguyên chuỗi ID claim được dẫn. N24 thêm đúng `ml-views-limit`, N34 chuyển từ `mvo-estimation` sang `mvo-definition`, N37 nhận thẻ thiếu nguồn đúng. N23 đổi từ trợ giúp sang yêu cầu bổ sung thông tin và vẫn trượt. Không có ca đạt trước đó bị trượt khi bật provider. Bốn ca còn trượt ở nhánh provider là N23, N28, N32 và N35. Tổng usage gồm 14.355 input token và 1.351 output token, số tiền dự phòng 0,0272 USD, 0 truy vấn embedding. Cần phân biệt số tiền dự phòng với chi phí ước tính.

Reviewer độc lập chấm toàn bộ câu trả lời đúng và đầy đủ ở 10/18 ca khi tắt provider và 13/18 khi bật. Trên 14 câu có đáp án, số câu truyền đạt được ý chính tăng từ 8 lên 10, số câu trả lời đầy đủ tăng từ 7 lên 9. Các ca thật sự thiếu căn cứ đạt 3/4 và 4/4. [Biên bản chấm độc lập](RAG_V4_GROUNDING_REVIEW.md)

[Bảng mã nguồn, claim trả về, claim được dẫn và kết quả từng ca](../../output/rag-quality-v4/paired-provider-summary.json) · [Gói QA riêng chứa hai câu trả lời cuối và đoạn trích thực tế](../../output/rag-quality-v4/private/paired-provider-answers.json)

## Tái lập

Thực hiện như [V3](RAG_QUALITY_V3_2026_11_23.md), dùng cùng database `rag_eval_v3_base`, endpoint 18971 cho B2, 18972 cho V3 và 18974 cho ứng viên mới. Với Chat, hai snapshot cũ nằm trong `output/rag-quality-v3/{baseline-src,candidate-src}`, bản mới ở `output/rag-quality-v4/candidate-src`. Chạy `scripts/eval_knowledge.py --version v4 --split heldout` cho từng chế độ. Báo cáo riêng cho người chấm dùng thêm `--review-output` ở chế độ `conversation`. Để đo latency ghép cặp, chạy từ gốc repo với hai service đang mở.

```sh
EVAL_KNOWLEDGE_FIXTURE_TOKEN=p3-local-read .venv-software/bin/python scripts/benchmark_knowledge_arms.py \
  --baseline-url http://127.0.0.1:18972 --candidate-url http://127.0.0.1:18974 \
  --suites v3 v4 --output output/rag-quality-v4/matched-latency.json
```
