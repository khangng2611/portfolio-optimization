# Kiểm định trên 40 kịch bản tiếng Việt v3

**Chưa đạt điều kiện phát hành.** Trên 40 tình huống mới khóa trước khi sửa mã, ứng viên trả đúng nguồn 33/40 so với 26/40 của B2 (mục tiêu tối thiểu 38/40). Với 14 câu có đáp án, 10/14 vừa vào đúng nhánh vừa tìm trúng claim trong top 5. Chỉ 1/14 đưa claim đúng vào câu trả lời cuối. Bộ v2 dùng để phát triển đạt 40/40 đúng nguồn và 12/12 câu có đáp án trích đúng claim.

## Bộ câu hỏi và các nguồn đo

Bộ v2 đã dùng để chẩn đoán các lỗi còn lại của vòng trước. Bộ v3 gồm 40 kịch bản tiếng Việt mới, trong đó có 14 câu kiến thức có đáp án, 5 câu thiếu bằng chứng, 10 câu trạng thái, 5 câu liên quan đến đề xuất đã lưu, 3 ca cần hỏi lại, 2 yêu cầu chuẩn bị phân bổ và 1 câu giá thị trường. Có câu không dấu, câu ngắn phụ thuộc lượt trước, đổi danh mục, đổi chủ, thay đổi trạng thái và một cutoff lịch sử. Mỗi kịch bản ghim nguồn đúng, điều được phép nói, điều phải từ chối và hành động được phép. Các câu cuối và tên gia đình tình huống v3 khác tập phát triển và nghiệm thu v2. Các chủ đề nghiệp vụ có giao nhau để hai vòng đo so sánh được.

Người giữ fixture chụp mã B2, viết và khóa v3 trước khi nhóm triển khai sửa router, truy xuất hoặc lựa chọn dẫn chứng. Người triển khai dùng v1/v2 và các kiểm thử cũ. V3 chỉ được mở kết quả sau khi ứng viên được khóa. SHA-256 của bộ v3 là `1c66aec20a5f605e5b789d2555b70e351f333b2cf9b2aaaf25015faa4ecca400`. Hash của bộ giữ lại v2 là `8ebd77f8926e47123aaf2ba774a3d5c22d01b6dab0a1d34c72f018ae2894056a`. [Fixture đánh giá](../../tests/fixtures/knowledge)

Mỗi nhánh chạy trên cùng câu hỏi, cùng cutoff `2026-11-23T16:00:00Z`, cùng PostgreSQL cô lập, cùng corpus và cùng ID chunk. Ca lịch sử dùng `2000-01-01T00:00:00Z`. Corpus có SHA-256 `83759093ce950cc5f2a781eddf91049d181408fbdd69016bc931562c57d3d094`. Hai tiến trình Knowledge HTTP phục vụ hai phiên bản ranker và dùng chung con trỏ active ở database thử nghiệm. Auth của hai endpoint dùng danh tính nội bộ fixture. Corpus v1 của Compose chưa được kích hoạt sang ứng viên.

Mỗi bộ 40 câu chạy 3 lần ở từng chế độ. Offline chỉ nhìn lời hỏi cuối. Lexical thực gọi HTTP trên câu kiến thức. Hội thoại gọi Chat API, queue và worker thật với SQLite tạm, dùng fixture cho Portfolio, Market và các nhánh không khả thi trên demo. Các lượt trước được thực hiện qua API trước khi chấm lượt cuối. Tool Knowledge gọi HTTP thật, ghi lại ID claim theo thứ tự trả về và ID claim được dẫn sau khi kiểm lại corpus. Mức trùng nguyên văn trong tin nhắn là một chỉ báo tự động. Đánh giá ngữ nghĩa cần đối chiếu câu hỏi, bằng chứng và nội dung trả lời theo từng phát biểu.

Kết quả từng dòng không chứa prompt, thông tin danh mục hoặc số tiền. Gói chấm riêng chứa câu hỏi, câu trả lời, thẻ dữ liệu, nội dung đoạn tài liệu, hash và kỳ vọng của kịch bản tổng hợp. Gói đó được lưu riêng với quyền `0600` trong thư mục local `output/rag-quality-v3/private/`. [Harness](../../scripts/eval_knowledge.py)

## Đối chứng trên hai bộ 40 ca

B2 có SHA-256 package Chat `50c5e201264a9593b757022fccd560e85e42a043b66bdda26e9782dfaccda3aa`, ứng viên `147c2d3b9a37e138000dd9a91e194129a8dac95356130cdd50e3efe4283ca820`. Hai SHA-256 của `knowledge_service/retrieval.py` là `5d59b7ca2836ba82e88fa290700292a14ce582fc9cc8e4287f1ffaff3186b5eb` và `50835b8e0a838799e069931b7edcf971ff4f6dbeb066d0c1e40115061dc83683`. Git HEAD là `ca0043b4a95c8d1fae0a5ec0f373377d307e00fb`. Ba lần lặp cùng phiên bản, bộ câu hỏi và chế độ có cùng tử số và mẫu số.

| Chỉ tiêu | V2 đã biết, B2 → ứng viên | V3 khóa trước, B2 → ứng viên |
|---|---:|---:|
| Đúng nguồn từ lời hỏi cuối, offline | 25 → 36/40 | 22 → 30/40 |
| Đúng nguồn ở phản hồi cuối, worker | 28 → 40/40 | 26 → 33/40 |
| Đúng trạng thái nghiệp vụ | 8 → 11/11 | 10 → 10/10 |
| Đúng nguồn thời gian của trạng thái | 8 → 11/11 | 9 → 9/10 |
| Claim đúng trong top 5, HTTP trực tiếp | 8 → 12/12 | 10 → 11/14 |
| MRR@5 của HTTP trực tiếp | 0,479 → 0,917 | 0,500 → 0,786 |
| Worker đúng nguồn và tìm trúng claim | 6 → 12/12 | 6 → 10/14 |
| Claim đúng trong dẫn chứng cuối | 2 → 12/12 | 0 → 1/14 |
| Tin nhắn trích nguyên văn claim đúng | 2 → 12/12 | 0 → 1/14 |
| Thiếu căn cứ được trả thẻ MISSING hợp lệ | 5 → 5/5 | 4 → 4/5 |
| Đọc đúng proposal và đúng hash facts | 3 → 5/5 | 2 → 4/5 |
| Hành động phù hợp, kể cả đề nghị xác nhận | 40 → 40/40 | 39 → 39/40 |

MRR tính nghịch đảo hạng đầu tiên có claim thuộc đáp án, trượt nhận 0. Năm truy vấn V3 thiếu bằng chứng đều trả 0 đoạn khi gọi thẳng API ở cả hai nhánh. Worker trả lời trợ giúp chung ở V37, nên số ca từ chối có căn cứ là 4/5. Cả hai nhánh có 0 lần gọi provider, chi phí 0 USD, 0 lệnh tạo allocation, 0 lần đọc proposal ngoài quyền fixture và 0 lần báo READY sai. Kết quả Paid/Compose có môi trường và receipt riêng.

| Nguồn đúng ở V3 | B2 | Ứng viên |
|---|---:|---:|
| Trạng thái | 10/10 | 10/10 |
| Chuẩn bị phân bổ | 2/2 | 2/2 |
| Kiến thức | 10/19 | 15/19 |
| Đề xuất đã lưu | 2/5 | 4/5 |
| Hỏi lại tham chiếu | 1/3 | 1/3 |
| Báo giá | 1/1 | 1/1 |

## Lỗi theo bước và giới hạn

- **Nguồn và quyền hành động**. Trong V30, câu hỏi kiến thức đưa người dùng tới thẻ xác nhận. Ledger ghi 0 lần gọi tạo allocation. V01 hỏi về lần bị chặn trước đó nhưng worker đọc lại trạng thái hiện tại. Mã `SYSTEM_PAUSED` tình cờ vẫn đúng trong fixture, còn nguồn và thời điểm cho câu trả lời không đúng. V11 mất tham chiếu proposal. V16 và V18 nhận trợ giúp chung thay cho một câu hỏi làm rõ.
- **Từ truy xuất sang trả lời**. Trong 10/14 ca V3 đã đi đúng nhánh và lấy được claim đúng, V27 nhận được dẫn chứng đúng. Ở V22, V24, V26, V28, V29, V32, V33, V34 và V35, worker trả thẻ không có dẫn chứng. V2 có 12/12 ở cả hai bước. Cần kiểm riêng điều kiện chọn đoạn cho một câu hỏi mới có đủ ý nghĩa tương đương với câu trong tài liệu, rồi đối chiếu câu trả lời cuối.
- **Kiểm từng dòng**. Receipt `comparison-v2.json` và `comparison-v3.json` có hai cột trước/sau cho từng ID, gồm nguồn worker, claim trả từ API theo hạng và claim thực sự xuất hiện trong citation. Có 18/40 dòng v2 và 10/40 dòng v3 thay đổi ít nhất một trường so sánh. Thư mục là `output/rag-quality-v3/`. Hash đúng xác nhận đoạn được trích còn nguyên vẹn. Phép đo không xác nhận mọi phát biểu trong câu trả lời đúng nghĩa hoặc đủ ý. Đánh giá ngữ nghĩa dùng gói chấm riêng và phải nêu vai trò của người chấm.

## Chấm ngữ nghĩa độc lập

Một agent đọc riêng 40 câu trả lời, tình huống và nguồn tương ứng trong packet SHA-256 `8a115f25232c7323683cd7f5edf06b86d5620e238af4aec4eb213140e67d52d9`. Rubric chấm theo nhóm phát biểu chính, kể cả phát biểu về việc thiếu bằng chứng. Mỗi nhóm chỉ được tính đạt khi tất cả ý quan trọng đều có căn cứ. Hướng dẫn thao tác và câu mô tả khả năng chung được loại khỏi mẫu số. Reviewer chấm số ý trả lời đủ theo yêu cầu riêng với số nhóm phát biểu có căn cứ.

Có **33/47 nhóm phát biểu được hỗ trợ** (70,2%). Xét mức độ trả lời đúng trọng tâm và đầy đủ, 19/40 ca hoàn chỉnh, 4/40 một phần và 17/40 bỏ lỡ yêu cầu. Trong 14 câu kiến thức có đáp án, 0/14 hoàn chỉnh, 1/14 một phần và 13/14 bỏ lỡ. Trong 5 câu thiếu căn cứ, 4/5 ca hoàn chỉnh. Đây là nhận xét của một reviewer tự động sau khi khóa ứng viên. Hai người chấm độc lập chưa xác nhận các điểm mơ hồ.

## Độ trễ và điều kiện so sánh

Khóa giao thức đo trước khi đọc kết quả ứng viên. Hai service HTTP dùng chung đúng dòng corpus `912f72b2-5ea9-4f41-889e-38700b2e446b` và cùng ID đoạn. Mỗi đợt chạy đủ 36 truy vấn kiến thức của v2/v3 bốn vòng, đảo thứ tự gọi hai endpoint sau mỗi câu/cặp. Có ba đợt với client mới, tổng cộng 432 lần gọi trên mỗi nhánh. Tách 3 lần gọi đầu mỗi đợt khỏi 429 lần còn lại, dùng median và nearest-rank p95. Không xóa cache database. Máy dùng chung với hoạt động khởi động stack khác. [Benchmark ghép cặp](../../scripts/benchmark_knowledge_arms.py)

| Quan sát (p50/p95, ms) | B2 | Ứng viên |
|---|---:|---:|
| HTTP lần đầu (n=3) | 28,68 / 55,25 | 31,40 / 41,63 |
| HTTP tiếp theo (n=429) | 22,02 / 113,14 | 23,43 / 100,98 |
| Server-Timing tiếp theo (n=429) | 15,23 / 92,24 | 16,69 / 86,70 |
| Worker fixture lượt cuối V2, gộp 117 lượt sau lượt đầu | 55,60 / 383,06 | 35,16 / 177,52 |
| Worker fixture lượt cuối V3, gộp 117 lượt sau lượt đầu | 54,39 / 469,52 | 28,41 / 67,38 |

P95 HTTP warm pooled giảm **10,75%**, đạt giới hạn tăng tối đa 20% trong lần kiểm định này. Ba p95 theo đợt là 76,10 → 61,86 ms, 70,37 → 63,84 ms và 148,61 → 163,52 ms. Các phép đo worker trước/sau chạy ở các thời điểm khác, không ghép cặp theo từng câu. Chưa đo cold start của toàn stack.

## Tái lập

Dùng đúng hai bản mã ở thư mục receipt local `output/rag-quality-v3/baseline-src` và `output/rag-quality-v3/candidate-src`. Cả hai đều được giữ do working tree đã có thay đổi địa phương khi khởi động đánh giá. Khởi động PostgreSQL pgvector mới bằng tmpfs theo hướng dẫn Knowledge. Ở cổng 18971 chạy `serve_knowledge_eval.py` với mã baseline. Ở cổng 18972 dùng cùng database, cùng manifest và cờ `--read-existing` với mã ứng viên. Cờ này xác nhận hash corpus active trước khi phục vụ. [Khởi tạo Knowledge cô lập](KNOWLEDGE_RAG.md) · [Launcher](../../scripts/serve_knowledge_eval.py)

```sh
run_dir=$(mktemp -d)
export EVAL_KNOWLEDGE_FIXTURE_TOKEN=p3-local-read
for arm in baseline candidate; do
  port=18971
  if [ "$arm" = candidate ]; then port=18972; fi
  for suite in v2 v3; do
    for run in 1 2 3; do
      for mode in offline lexical conversation; do
        PYTHONPATH="$PWD/output/rag-quality-v3/$arm-src" .venv-software/bin/python scripts/eval_knowledge.py \
          --version "$suite" --split heldout --mode "$mode" --run "$run" \
          --knowledge-url "http://127.0.0.1:$port" --output "$run_dir/$arm-$suite-$mode-$run.json"
      done
    done
  done
done
for suite in v2 v3; do
  .venv-software/bin/python scripts/eval_knowledge_status.py \
    "$run_dir/baseline-$suite-conversation-1.json" "$run_dir/candidate-$suite-conversation-1.json" \
    "$run_dir/comparison-$suite.json"
done
.venv-software/bin/python scripts/benchmark_knowledge_arms.py --baseline-url http://127.0.0.1:18971 \
  --candidate-url http://127.0.0.1:18972 --output "$run_dir/matched-latency.json"
```
