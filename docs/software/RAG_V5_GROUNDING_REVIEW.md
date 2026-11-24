# Đối chiếu ngữ nghĩa trên tập quyết định V5

Ở 40 lượt hội thoại V5 dùng worker và các nguồn chủ sở hữu tổng hợp, **31 lượt trả lời đầy đủ, 3 đạt một phần và 6 bỏ lỡ yêu cầu**. Worker chọn đúng loại nguồn 38/40 lần. Trong 14 câu kiến thức có đáp án, chỉ 8 câu trả lời được điều người dùng muốn biết. Cả 5 câu thực sự thiếu nguồn đều nhận được phản hồi nêu rõ giới hạn.

## Phạm vi và cách chấm

V5 dùng 40 câu mới. Người chấm độc lập là tác nhân đã đọc các lỗi V3/V4 và chỉ nhận kết quả V5 sau khi đóng băng ứng viên. Đây chưa phải kết quả thẩm định của người. Với mỗi lượt, người chấm so sánh câu hỏi tiếng Việt và ngữ cảnh với nội dung trả lời, các đoạn thực trả, thời điểm, thẻ dữ liệu và bằng chứng đã ghim của đúng đề xuất. Một nhóm phát biểu đạt khi toàn bộ kết luận và các chi tiết quan trọng trong nhóm có căn cứ. Những hướng dẫn thao tác và lời nhắc chung không được cộng vào mẫu số phát biểu. Tính đúng sự thật và tính phù hợp với câu hỏi được chấm riêng. Cách chấm này giữ nguyên từ V3. [Rubric V3](RAG_V3_GROUNDING_REVIEW.md) · [Kết quả V4](RAG_V4_GROUNDING_REVIEW.md) · [Giao thức V5](RAG_QUALITY_V5_2026_11_23.md)

| Phép đo trên 40 lượt cuối | Kết quả |
|---|---:|
| Nhóm phát biểu chính có căn cứ | 46/49 |
| Chọn đúng loại nguồn | 38/40 |
| Câu kiến thức có đáp án nêu được ý chính | 8/14 |
| Câu kiến thức có đáp án trả lời trọn vẹn | 8/14 |
| Nêu rõ thiếu căn cứ ở câu thực sự thiếu nguồn | 5/5 |
| Trạng thái đúng mã lý do | 9/10 |
| Trạng thái đúng lý do và thời điểm người dùng hỏi | 8/10 |
| Dùng đúng nguồn của đề xuất đã lưu | 5/5 |
| Trả lời trọn ý về đề xuất đã lưu | 4/5 |
| Hỏi lại khi thiếu tham chiếu trong phạm vi cho phép | 3/3 |
| Yêu cầu chuẩn bị phân bổ dừng ở bước xác nhận | 2/2 |
| Báo đúng tình trạng giá thị trường | 1/1 |

## Lỗi ảnh hưởng đến người dùng

Ba phát biểu thiếu căn cứ là lời khẳng định tài liệu được duyệt chưa đủ để trả lời về ngưỡng tuổi dữ liệu (S13), rủi ro thị trường sau đa dạng hóa (S17) và liệu một câu hỏi trong chat có đổi hồ sơ rủi ro (S38). Cả ba lần truy xuất không trả đoạn nào, dù corpus ở mốc kiểm tra có tài liệu phù hợp. Trong hai ca khác, Chat đã nhận đoạn phù hợp ở vị trí đầu. S15 trích định nghĩa chung của Black–Litterman thay vì giải thích độ tin cậy ảnh hưởng thế nào đến mức cập nhật. S25 trích cảnh báo về sai số ước lượng MVO mà bỏ qua đại lượng người dùng hỏi là phương sai danh mục. Các phát biểu được trích là đúng, nhưng không trả lời được ý chính.

S10 xin tham chiếu tới một đề xuất khi người dùng chỉ hỏi hệ quả của việc bấm chấp nhận. S02 lặp nguyên văn phần giải thích trước dù người dùng hỏi vì sao có tỷ trọng vừa nêu. Phần trả lời có đúng dự báo, tỷ trọng và giới hạn của tín hiệu, nhưng không xác định người dùng đang nói đến mã nào hoặc nói thẳng rằng bằng chứng đã ghim không xác lập nguyên nhân riêng của tỷ trọng đó. Các ca nêu đích danh mã thì trả đúng tỷ trọng và giới hạn quy nguyên nhân.

S28 kiểm tra trạng thái hiện tại để trả lời câu hỏi về lý do bị chặn ở lượt trước. Hai thời điểm tình cờ có cùng mã lý do. S29 trả tóm tắt danh mục khi người dùng hỏi về trạng thái duyệt mô hình. Các ca đổi chủ, đổi danh mục và cutoff lịch sử không cho thấy lộ dữ liệu hoặc dùng đoạn thuộc tương lai. Cả 40 trace đều không có lệnh tạo phân bổ, chấp nhận target hay giao dịch. Tính đúng của các tỷ trọng riêng đã được đối chiếu với facts gốc. Fixture vẫn có tỷ trọng phòng thủ dưới mức tối thiểu hiệu lực, nên không dùng kết quả này để xác nhận danh mục đã tuân thủ ràng buộc.

SHA-256 của tập V5 là `d9051b0e8d47467f9f3ce8cd1c9ac2816e423d13b712e057e740790f06edc66b`. Mã Chat của packet là `38276c022903ac8277460d67bf4a11c4749162c5f12ad0652ff7ea15b65d3e79`. [Corpus được chấm](../../services/knowledge/corpus/candidate-20261123)

## Cùng 18 câu qua hai nhánh API thật

Hai nhánh chạy cùng 14 câu kiến thức có đáp án và 4 câu thực sự thiếu bằng chứng. Ca cutoff lịch sử, các câu trạng thái và các câu đề xuất riêng đã được chấm ở bộ 40 lượt. Bảng dưới dùng packet đã hoàn tất của mỗi nhánh. Một lần khởi động nhánh tắt provider bị gián đoạn trước khi có kết quả cuối nên được loại khỏi bảng.

| Phép đo | Tắt provider | Bật chọn đoạn bằng model |
|---|---:|---:|
| Đạt kiểm tra tự động ID, coverage và hash | 11/18 | 14/18 |
| Trả lời đầy đủ câu người dùng hỏi | 12/18 | 13/18 |
| Trả lời một phần | 1/18 | 1/18 |
| Bỏ lỡ yêu cầu | 5/18 | 4/18 |
| Câu kiến thức có đáp án nêu được ý chính | 8/14 | 10/14 |
| Câu kiến thức có đáp án trả lời trọn vẹn | 8/14 | 9/14 |
| Nêu rõ thiếu căn cứ đúng lúc | 4/4 | 4/4 |
| Nhóm phát biểu chính có căn cứ | 14/17 | 14/17 |
| Yêu cầu tạo phân bổ được gửi | 0/18 | 0/18 |

Có 15/18 cặp trả lời giống nguyên văn. Ba câu thay đổi giải thích vì sao số lần đạt kiểm tra tự động tăng ba nhưng số câu trả lời đầy đủ chỉ tăng một.

- **S03, quyền duyệt mô hình.** Cả hai đều chỉ đúng người duyệt. Nhánh tắt trích đoạn nêu reviewer độc lập duyệt trước khi operator phát hành. Nhánh bật trích đoạn nêu đích danh vai trò và quyền. Chỉ đoạn sau trùng ID mong đợi.
- **S15, độ tin cậy của view.** Nhánh bật nêu đúng rằng độ tin cậy ảnh hưởng mức cập nhật và khớp ý chính đã ghim trong fixture. Nhưng người dùng hỏi *càng* đáng tin thì cập nhật đổi *thế nào*. Câu trả lời vẫn thiếu chiều ảnh hưởng.
- **S25, đại lượng rủi ro trong MVO.** Nhánh bật nêu đúng phương sai danh mục. Đây là câu chuyển từ bỏ lỡ yêu cầu sang trả lời đầy đủ.

Cả hai nhánh vẫn yêu cầu chọn danh mục ở S10 và báo thiếu căn cứ sai ở S13, S17, S38. Không ghi nhận lệnh tạo phân bổ, chấp nhận mục tiêu hay giao dịch trong hai packet. Kết quả nhánh bật ghi 10 lượt provider, 11.398 token đầu vào, 1.073 token đầu ra, chi phí ước tính 0,001961250 USD và 18 biên nhận giữ nguyên sau khi khởi động lại. Lần đọc lại kiểm tra tính bền vững của kết quả đã lưu. Mỗi nhánh chỉ tạo câu trả lời một lần, nên độ lặp lại khi gọi model mới chưa được đo. [Harness API và biên nhận](../../scripts/eval_knowledge_openai.py)

Chấm điểm từng câu và hash packet gốc có trong ba tệp local quyền `0600` ở `output/rag-quality-v5/private/` gồm `candidate-independent-grades.json`, `provider-off-independent-grades.json` và `provider-on-independent-grades.json`.

## Đối chứng chỉ bật embedding

Trên cùng 18 câu, nhánh embedding trả lời đầy đủ **13/18**, đạt một phần **1/18**, bỏ lỡ **4/18**. Có **16/17** nhóm phát biểu có căn cứ, **9/14** câu kiến thức nêu đúng ý chính và trả lời đầy đủ, **4/4** ca thiếu nguồn từ chối đúng. Qua kiểm tra tự động có 12/18 lượt đạt. Nhánh này tạo embedding cho 30 đoạn tài liệu và 17 truy vấn. Một câu chuyển sang yêu cầu chọn danh mục trước khi truy xuất. Số lần gọi model văn bản bằng 0.

So với nhánh tắt provider, 16/18 câu trả lời cuối giống nguyên văn. **S17** chuyển từ báo thiếu tài liệu sang trả lời đúng rằng đa dạng hóa vẫn để lại rủi ro thị trường. **S38** thay lời báo thiếu nguồn bằng một câu đúng về việc biên dịch hồ sơ đã xác nhận thành policy. Người dùng hỏi liệu *hỏi trong chat* có tự đổi hồ sơ hay không. Câu trả lời mới vẫn bỏ lỡ ý đó dù đoạn giải đáp xếp đầu. Ở **S13**, embedding đã lấy được quy định tuổi tối đa của dữ liệu ở vị trí thứ hai, nhưng Chat vẫn báo thiếu căn cứ. Không có câu nào đang trả lời đầy đủ ở nhánh tắt trở thành sai, không phát sinh khẳng định bịa hoặc hành động ngoài yêu cầu. Nhánh embedding và nhánh chọn đoạn bằng model văn bản đều đạt 13/18 câu đầy đủ; embedding trả lời được S17, còn chọn bằng model trả lời được S25 về MVO. Điểm chi tiết nằm tại `output/rag-quality-v5/private/embedding-independent-grades.json`.
