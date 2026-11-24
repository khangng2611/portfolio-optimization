# Chấm nội dung trả lời trên bộ V4

Ứng viên nêu được ý kiến thức chính trong **8/14** câu có đáp án. **7/14** câu trả lời trọn vẹn điều người dùng hỏi. Ví dụ, câu về trượt giá nêu đúng ảnh hưởng lên lợi nhuận sau phí. Người dùng hỏi *vì sao*, còn đoạn được dẫn chỉ liệt kê các chi phí và ảnh hưởng chung. Trên toàn bộ 40 lượt, **29 đạt, 2 đạt một phần, 9 bỏ lỡ yêu cầu**.

## Phiên bản và người chấm

Một tác nhân đọc độc lập từng câu tiếng Việt, ngữ cảnh, đoạn thực trả, thẻ dữ liệu và bằng chứng của đúng lượt. Cách nhóm và chấm từng khẳng định giữ theo V3. Người chấm đã biết các lỗi V3, sau đó nhận câu và đầu ra V4 khi ứng viên đã khóa. Nhóm triển khai đã dùng V3 để phát triển. V4 dùng câu mới, có một số chủ đề nghiệp vụ chung với các vòng trước. Đây là đánh giá của tác nhân trên dữ liệu tổng hợp. Chưa có người chấm độc lập xác nhận. [Rubric V3](RAG_V3_GROUNDING_REVIEW.md) · [Giao thức và tập V4](RAG_QUALITY_V4_2026_11_23.md)

Gói 40 lượt dùng Chat và Knowledge HTTP, nguồn chủ sở hữu theo fixture và không gọi provider. SHA-256 bộ câu là `29877078d894cc6a42b6cb8120b4613144c4c34a310e635001e7ed25ce988c6d`. SHA-256 package Chat là `775166e14deb9a1448251920fff3c3548395473a3561110c97668bb0aac1ed2e`.

| Chỉ tiêu của 40 lượt cuối | Kết quả |
|---|---:|
| Đúng loại nguồn | 33/40 |
| Nhóm phát biểu chính có căn cứ | 37/39 |
| Lượt kiến thức có đáp án nêu được ý chính | 8/14 |
| Lượt kiến thức có đáp án trả lời trọn ý | 7/14 |
| Nêu rõ thiếu nguồn ở câu thực sự thiếu căn cứ | 4/5 |
| Trạng thái đúng lý do và đúng thời điểm | 9/10 |
| Trả lời dựa trên đề xuất đã lưu | 4/5 |
| Hỏi lại đúng phạm vi sau thay đổi ngữ cảnh hoặc khi thiếu tham chiếu | 3/3 |
| Yêu cầu chuẩn bị phân bổ nhận thẻ xác nhận | 1/2 |
| Báo đúng tình trạng thiếu giá thị trường | 1/1 |

## Căn cứ và ý định người hỏi

Trong 39 nhóm phát biểu, hai câu báo thiếu nguồn trong tài liệu đã duyệt dù có tài liệu đủ căn cứ. Với N28 về backtest, đoạn trả lời được câu hỏi đã đến Chat. Với N32 về hiệu lực của dữ liệu mới đối với target đã lưu, truy xuất chỉ trả đoạn về target và việc chấp nhận đề xuất. Đoạn giải thích việc ghim kết quả đã có trong corpus nhưng không được trả. Tỷ lệ 37/39 còn tính những phát biểu đúng nhưng lạc đề. Câu hỏi về sự đánh đổi của MVO (N34) nhận lời cảnh báo có căn cứ về sai số ước lượng, dù đoạn xếp đầu nói đúng về lợi nhuận kỳ vọng và phương sai. Những menu chức năng và lời nhắc chung không có phát biểu nghiệp vụ chính để chấm.

Ở N12, tài liệu công khai không đủ để mô tả một đề xuất cá nhân. Câu trả lời dừng tại đó dù lượt trước đã có đề xuất đúng phạm vi. N35 hỏi liệu hỏi trong chat có tự đổi hồ sơ hay không, nhưng nhận thẻ hồ sơ. N23 nhắc đến giới hạn giao dịch của chat mà bỏ qua hệ quả cụ thể khi chấp nhận một target. Hai lượt giải thích tỷ trọng riêng của một mã đã nêu đúng tỷ trọng ghim và đúng giới hạn của bằng chứng quy nguyên nhân. Fixture vẫn chứa tỷ trọng phòng thủ thấp hơn mức tối thiểu hiệu lực theo dữ kiện cùng lượt, nên không dùng nó để kết luận đề xuất đã đáp ứng ràng buộc.

Hai lượt truy nguyên trạng thái cũ dùng lý do đã ghi. Các lượt hỏi trạng thái hiện tại thành công dùng lần kiểm tra mới. Trong số mười ca trạng thái, một câu về mô hình chờ duyệt nhận menu chức năng. Các lượt đổi chủ và đổi danh mục không lộ tham chiếu cũ. Ca cutoff lịch sử từ chối đúng. Không có yêu cầu tạo phân bổ được gửi qua tool trong 40 lượt đã chấm.

## Đối chiếu bật và tắt OpenAI trên API thật

Hai nhánh xử lý cùng 18 câu tương thích với môi trường API thật, gồm 14 câu kiến thức có đáp án và 4 câu thiếu nguồn. Các lượt trạng thái, đề xuất cá nhân, đổi ngữ cảnh và cutoff lịch sử nằm ngoài mẫu ghép cặp. Bảng dùng nội dung cuối mà người dùng nhận được.

| Chỉ tiêu | Tắt provider | Bật provider |
|---|---:|---:|
| Qua kiểm tra tự động ID, coverage và hash | 11/18 | 14/18 |
| Trả lời trọn vẹn ý định theo đối chiếu độc lập | 10/18 | 13/18 |
| Trả lời một phần | 2/18 | 1/18 |
| Bỏ lỡ yêu cầu | 6/18 | 4/18 |
| Ý chính đúng trong câu kiến thức có đáp án | 8/14 | 10/14 |
| Câu kiến thức có đáp án được trả lời trọn vẹn | 7/14 | 9/14 |
| Nói rõ thiếu căn cứ đúng lúc | 3/4 | 4/4 |
| Nhóm phát biểu chính có căn cứ | 12/14 | 14/16 |

Trong 18 cặp, 14 cặp có nội dung cuối giống hệt. Bật provider giúp trả lời đúng việc dự báo ML có thể sai (N24), hai đại lượng đánh đổi trong MVO (N34) và việc thiếu tài liệu về rho (N37). Ở N23, menu nhắc chat không tự giao dịch khi tắt provider, còn nhánh bật yêu cầu chọn danh mục. Cả hai bỏ sót việc chấp nhận đề xuất chỉ lưu mục tiêu. Ở N27, cả hai dẫn đúng đoạn nhưng thiếu giải thích cơ chế trượt giá theo yêu cầu. N28 cho thấy khác biệt giữa bằng chứng mô hình đề xuất và bằng chứng được trình bày. Model chọn đúng đoạn nói kết quả quá khứ không chứng minh lợi nhuận tương lai, quote trùng nguyên văn và kiểm tra cuối ghi `INVALID_REFERENCES`. Người dùng chỉ nhận thông báo thiếu nguồn. Trường hợp này được chấm theo câu trả lời cuối.

Receipt ghi 16 lượt provider, 14.355 token đầu vào, 1.351 token đầu ra và chi phí ước tính 0,002469875 USD. Mỗi nhánh có một lần chạy trên 18 câu. Chênh lệch trên mẫu nhỏ này chưa cho biết độ ổn định giữa các lần gọi. [Harness ghép cặp](../../scripts/eval_knowledge_openai.py)

Điểm và lý do từng câu nằm trong ba tệp quyền `0600` ở `output/rag-quality-v4/private/` gồm `candidate-independent-grades.json`, `provider-off-independent-grades.json` và `provider-on-independent-grades.json`. Mỗi tệp ghi hash của packet gốc.
