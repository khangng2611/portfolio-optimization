# Đối chiếu nội dung trả lời trên bộ v3

Ứng viên trả lời đúng ý kiến thức chính ở **1/14** câu có đáp án. Câu duy nhất đó còn báo thiếu căn cứ cho một phần mà người dùng không hỏi. B2 trả lời đúng ý chính ở **0/14**. Đây là kết quả của một tác nhân đánh giá độc lập đọc tiếng Việt và đối chiếu bằng chứng trên 40 lượt cuối tổng hợp đã khóa. Chưa có người chấm hoặc kiểm chứng trên hội thoại khách hàng.

| Phép đo trên một lượt chạy hội thoại | B2 | Ứng viên |
|---|---:|---:|
| Đúng loại nguồn theo kịch bản, kể cả trường hợp phản hồi sai thời điểm | 26/40 | 33/40 |
| Nêu được ý chính của câu kiến thức có đáp án | 0/14 | 1/14 |
| Nói rõ thiếu căn cứ ở những câu thực sự thiếu nguồn | 4/5 | 4/5 |
| Đúng mã trạng thái | 10/10 | 10/10 |
| Dùng đúng thời điểm để trả lời câu trạng thái | 9/10 | 9/10 |
| Trả về đúng loại nguồn đề xuất đã lưu | 2/5 | 4/5 |

## Cách chấm

Từng lượt được đọc cùng câu hỏi, ngữ cảnh, phạm vi danh mục, nội dung người dùng thấy, thẻ dữ liệu và các đoạn công khai thực trả. Đối với đề xuất, người chấm đối chiếu thêm dữ kiện gốc và bằng chứng của đúng lần tính. Mỗi kết luận chính mang thông tin được tính một lần. Các con số cùng mô tả một kết luận trong một đoạn, chẳng hạn dự báo của một mã cùng kỳ hạn và tỷ trọng của mã đó, là một nhóm. Cả nhóm chỉ đạt khi tất cả các phần quan trọng có căn cứ. Khẳng định thiếu nguồn và khẳng định thẻ có nguồn cũng được chấm. Câu hướng dẫn thao tác và lời nhắc chung về khả năng của ứng dụng được chấm theo ý định của lượt, không cộng vào mẫu số phát biểu.

- **33/47 nhóm phát biểu của ứng viên có căn cứ.** Có 10 tuyên bố thiếu nguồn cho câu có đáp án, 1 thông báo thiếu căn cứ cho phần còn lại không tồn tại, 1 lời giới thiệu nguồn thiếu trong thẻ thị trường và 2 nhóm cảnh báo đề xuất nêu tình trạng chứng nhận dữ liệu chưa được xác lập trong gói bằng chứng cụ thể. Sai nguồn thời gian được tính riêng khi chấm ý định. Tỷ lệ này phụ thuộc cách nhóm câu và không phải tỷ lệ chính xác trên mọi câu trả lời.
- **19/40 lượt hoàn thành yêu cầu, 4/40 đạt một phần, 17/40 bỏ lỡ.** Đạt một phần khi trả đúng một nội dung nhưng dùng sai phạm vi thời gian, thiếu câu trả lời theo mã tài sản, hoặc thêm cảnh báo sai về một phần câu hỏi. Với câu kiến thức, tiêu chí toàn bộ câu trả lời đúng và đủ đạt **0/14**.
- **4/5 lượt thiếu nguồn đã từ chối đúng cách**. Lượt còn lại mở danh sách chức năng. Cả năm tránh tự đưa ra công thức hay kiến thức thiếu bằng chứng. Cả hai yêu cầu chuẩn bị phân bổ nhận thẻ xác nhận. Trong 40 lượt không ghi nhận lệnh tạo phân bổ.

## Những chỗ nguồn và nội dung khác nhau

Ở chín câu có đáp án, dịch vụ đã trả về đoạn văn trực tiếp giải quyết yêu cầu nhưng bộ chọn loại toàn bộ. Các ví dụ gồm V22 về prior và views, V26 về hiệp phương sai, V32 về mốc tính tuổi dữ liệu. Ở một câu khác, truy xuất không tìm được đoạn phù hợp dù tài liệu được duyệt có giải đáp. Trong V27, chi phí và trượt giá cùng là điều kiện của một phép so sánh. Việc tách ở từ “và” khiến câu trả lời trích dẫn đúng nhưng báo thiếu phần còn lại. [Bộ chọn và trình kết xuất](../../services/chat/src/chat_service/knowledge.py)

V01 hỏi lý do ở lượt trước nhưng hệ thống kiểm tra lại trạng thái hiện tại. Hai trạng thái tình cờ trùng nhau trong fixture. V30 hỏi ý nghĩa của việc chấp nhận mục tiêu và nhận thẻ xác nhận tạo phân bổ. Cả hai hiện tượng cũng có trong B2. Hai trường hợp yêu cầu giải thích một mã trong đề xuất cũ nhận đúng loại thẻ, nhưng phần trả lời không nêu tỷ trọng đã lưu của mã hoặc nói rõ thiếu bằng chứng cho nguyên nhân riêng của mã. [Router](../../services/chat/src/chat_service/workflow.py) · [Phân loại câu trạng thái](../../services/chat/src/chat_service/allocation_status.py)

Fixture đề xuất có điểm mâu thuẫn. Tài sản phòng thủ duy nhất có tỷ trọng thấp hơn mức tối thiểu hiệu lực suy ra từ giới hạn ngoài nhóm phòng thủ. Có thể kiểm tra rằng câu trả lời trích đúng số liệu đã ghim. Fixture này không đủ để chứng minh danh mục tuân thủ ràng buộc hoặc quy trách nhiệm cho bộ tối ưu.

## Kiểm tra mã và giới hạn

So sánh bản chụp B2 với ứng viên đã khóa cho thấy các sửa đổi nằm ở router, truy vết ngữ cảnh, bộ chọn đoạn và xếp hạng lexical. Truy vết giới hạn theo chủ và hội thoại, cắt lịch sử tại lần chuyển danh mục. Truy vấn lexical và vector dùng cùng tập đoạn công khai, corpus đang hoạt động và thời điểm khả dụng. Chat kiểm tra lại hash corpus và quyền đọc ở Portfolio trước khi hoàn tất câu trả lời kiến thức. Các ca chuyển chủ, chuyển danh mục và cutoff lịch sử trong packet không hiển thị dữ liệu ngoài phạm vi. Đây là đối chiếu mã và fixture, chưa bao quát mọi điều kiện cạnh tranh hay lỗi dịch vụ. [Ngữ cảnh](../../services/chat/src/chat_service/llm.py) · [Truy xuất](../../services/knowledge/src/knowledge_service/retrieval.py)

Harness trả phí yêu cầu mã phê duyệt riêng, giữ biên nhận tạo độc quyền, dùng tối đa 10 lượt văn bản, tắt embedding và đặt ngân sách 0,04 USD. Mỗi lượt giữ chỗ 0,0017 USD, tối đa 0,017 USD cho 10 lượt. Ledger ghi giữ chỗ trước HTTP và khóa giao dịch PostgreSQL. Kiểm tra này chỉ đối chiếu mã cục bộ. Các phép đo trên đều dùng gói ứng viên lexical, bộ chọn tất định. [Harness](../../scripts/eval_knowledge_openai.py) · [Giới hạn yêu cầu](../../services/chat/src/chat_service/openai_provider.py)

Hash mã Chat của packet ứng viên là `147c2d3b9a37e138000dd9a91e194129a8dac95356130cdd50e3efe4283ca820`. Điểm từng câu và lý do chi tiết nằm trong tệp local quyền `0600`, tại `output/rag-quality-v3/private/candidate-independent-grades.json`. [Thiết kế và tập kiểm định](RAG_QUALITY_V3_2026_11_23.md)
