# Nghiệm thu Chat và truy xuất tiếng Việt ngày 23/11/2026

**Quyết định giữ nguyên corpus đang phục vụ.** Trên 40 kịch bản nghiệm thu, worker mới trả đúng loại phản hồi ở 28/40 ca (70%, ngưỡng 95%). Trong 12 câu kiến thức có đáp án, lexical lấy được claim đúng ở 8/12 ca, worker vừa chọn đúng nguồn vừa tìm được claim đúng ở 6/12 ca. Cả hai ngưỡng là 90%. Kết quả 3 lần lặp giống nhau về tử số và mẫu số.

## Thiết kế đối chứng

Bộ v2 có 20 ca phát triển, 40 ca nghiệm thu và 25 ca nhiều lượt. Mỗi ca lưu gia đình tình huống, hội thoại, trạng thái fixture, nguồn đúng, câu được phép nói, claim, hành động và nội dung phải từ chối. Hai tập tách theo gia đình kịch bản, người giữ bộ nghiệm thu khóa SHA-256 trước khi sửa router. Có một cặp dùng cùng lời hỏi và lịch sử hiển thị nhưng một ca đã đổi danh mục. Ngữ cảnh quyền và danh mục là một phần của đầu vào. Hai ca hồi quy kiến thức đã công bố của v1 có mặt ở tập phát triển v2. [Fixture](../../tests/fixtures/knowledge)

| Đối tượng | SHA-256 |
|---|---|
| Dataset v1 | `bbd12e32e888737bcc23c51261a92675d2ac16d2706ce573853ae0356802f4f3` |
| Phát triển v2 | `29d1e3fad8b63125ae3236ffca1dd6b778f4822e2af9492214a3fef671a964f3` |
| Nghiệm thu v2 | `8ebd77f8926e47123aaf2ba774a3d5c22d01b6dab0a1d34c72f018ae2894056a` |
| Nguồn Python của Chat trước thay đổi | `51886b5779dd151eea923951b6c90739bfc5ef8181072e1a9d9991891ca88225` |
| Nguồn Python của Chat lúc khóa nghiệm thu | `fff150c29b84491cd68fea7e4f610909ebb03333af441a1a34f91a0c9fd95092` |
| Corpus v1 đang active | `a8d21c647e8a514510873dce49b8414b7fc32921840c74b53a383b189e9600d4` |
| Corpus ứng viên trong PostgreSQL cô lập | `83759093ce950cc5f2a781eddf91049d181408fbdd69016bc931562c57d3d094` |

Git HEAD lúc đo là `ca0043b4a95c8d1fae0a5ec0f373377d307e00fb`. Working tree có sửa đổi địa phương từ trước. Hai bản chụp mã nguồn Chat lưu cạnh receipt để tái lập đúng mã chạy. Cutoff cố định trong phép so sánh là `2026-11-23T16:00:00Z`, trừ ca lịch sử dùng `2000-01-01T00:00:00Z`. Đây là thời điểm truy vấn của kịch bản. Trường `at` ghi thời gian chạy thực. Index tương thích `openai-small-1536-v1`, truy xuất lexical tối đa 5 đoạn, tắt embedding, rewrite và mọi provider.

- **Offline** gọi trực tiếp `intent_of` trên lời hỏi cuối. Các câu cần lịch sử hoặc phải đọc điều kiện nghiệp vụ chỉ được phân giải đầy đủ trong worker.
- **Lexical** gọi HTTP thực tới Knowledge API và PostgreSQL. Nhánh đang phục vụ dùng xác thực service của Compose. Ba nhánh đo độc lập dùng HTTP verifier fixture giới hạn loopback, cùng kiểu runtime trên cùng máy và cùng PostgreSQL cô lập. Thứ tự ba nhánh được xoay qua ba lần chạy.
- **Hội thoại** chạy Chat API qua FastAPI TestClient, SQLite tạm, queue và worker thật. Các lượt trước được gửi qua cùng API. Portfolio, readiness, sự cố kết nối, định danh chủ sở hữu và Market dùng fixture. Tool lấy kiến thức gọi HTTP thật, gồm lần kiểm lại corpus. Ca lịch sử đặt cutoff của fixture tại biên tool. Các số đo hội thoại là thời gian gửi, xử lý và đọc kết quả của lượt cuối. Phần browser/Compose có receipt riêng trong kế hoạch triển khai. [Harness](../../scripts/eval_knowledge.py)

## Ứng viên A trên 40 ca giữ lại

| Thước đo | Chat cũ + Knowledge đang chạy | Chat mới + Knowledge đang chạy | Chat mới + Knowledge ứng viên |
|---|---:|---:|---:|
| Nguồn dự đoán từ lời cuối, offline | 14/40 | 25/40 | 25/40 |
| Nguồn thể hiện trên phản hồi cuối | 15/40 | 28/40 | 28/40 |
| Mã trạng thái đúng | 0/11 | 8/11 | 8/11 |
| Trạng thái có thời điểm và đọc đúng nguồn theo ngữ cảnh | 0/11 | 8/11 | 8/11 |
| Ca trạng thái giữ điều kiện chỉ đọc, không gọi Knowledge/provider | 8/11 | 11/11 | 11/11 |
| Công cụ lấy đúng claim, Hit@5 | 8/12 | 8/12 | 8/12 |
| MRR@5, điểm 0 khi trượt | 0,542 | 0,542 | 0,521 |
| Worker chọn đúng nguồn và lấy đúng claim | 3/12 | 6/12 | 6/12 |
| Thẻ cuối dẫn claim đúng | 3/12 | 2/12 | 2/12 |
| Nội dung tin nhắn chứa nguyên câu của claim đúng | 0/12 | 2/12 | 2/12 |
| Câu thiếu căn cứ trả thẻ thiếu bằng chứng, không có citation | 5/5 | 5/5 | 5/5 |
| Đọc đúng đề xuất đã ghim và khớp hash facts | 3/5 | 3/5 | 3/5 |
| Không gửi lệnh ghi hoặc hiện yêu cầu xác nhận ngoài dự kiến | 37/40 | 40/40 | 40/40 |

Trong mỗi lần chạy ứng viên, trên 40 lượt cuối có 37 lần đọc profile, 28 lần truy xuất kiến thức (kể cả kiểm lại corpus), 10 lần đọc trạng thái, 9 lần đọc tóm tắt danh mục, 3 lần đọc proposal, 3 lần đọc evidence của proposal và 1 lần đọc Market. Có 0 lần gọi provider, 0 USD, 0 lần gọi tạo allocation, 0 lần đọc proposal ngoài scope fixture và 0 phản hồi READY sai trong 11 ca trạng thái. Baseline cũng có 0 lệnh ghi nhưng đề nghị xác nhận ở 3 ca chỉ hỏi. Đây là số đo trên fixture, còn quyền thực và bảo toàn dữ liệu sau restart cần bằng chứng Compose.

| Nhóm nguồn | Cũ | Ứng viên | p50/p95 lượt cuối ứng viên (ms) |
|---|---:|---:|---:|
| Trạng thái | 0/11 | 8/11 | 14,83 / 38,67 |
| Hành động | 2/2 | 2/2 | 13,78 / 28,97 |
| Kiến thức, kể cả thiếu căn cứ | 8/17 | 11/17 | 37,66 / 137,30 |
| Đề xuất đã lưu | 3/5 | 3/5 | 35,89 / 84,88 |
| Hỏi lại tham chiếu | 1/4 | 3/4 | 12,58 / 34,05 |
| Báo giá | 1/1 | 1/1 | 7,80 / 19,49 |

Trên tập phát triển, ứng viên đúng nguồn 20/20, trạng thái 6/6, vừa đúng nguồn vừa lấy đúng claim 6/6, trích đúng claim trong nội dung 6/6 và từ chối 1/1. Trên bộ hồi quy v1, baseline đo lại khớp intent 30/40, lexical Hit@5 14/16, từ chối 2/2. Giữ tập nghiệm thu v2 đã mở kết quả này cho hồi quy. Một lần chỉnh tiếp cần tập giữ lại độc lập để kết luận khả năng khái quát.

## Vị trí còn lỗi ở ứng viên A

- **Đọc trạng thái**. H07, H08 và H10 rơi vào trợ giúp hoặc tóm tắt danh mục. Các biến thể về độ mới NAV, khả năng tạo khi dịch vụ lỗi và đã chuyển danh mục cần đi qua phép đọc readiness hiện tại.
- **Tham chiếu đề xuất**. H14, H15 và H18 trả trợ giúp chung. Cần phân biệt tham chiếu thuộc đúng chủ với câu hỏi cần yêu cầu chọn đề xuất. Không có lần đọc ngoài quyền trong các ca này.
- **Chọn nguồn kiến thức**. H27, H30, H32, H33, H34 và H40 đi sang nguồn khác. Các câu hỏi về quy tắc chung có thể nhắc đến danh mục hoặc target dù người dùng chưa yêu cầu thao tác.
- **Lexical và lựa chọn dẫn chứng**. H27, H30, H33 và H40 trượt claim ngay trong top 5. H24, H26, H28 và H29 đã vào đúng nhánh và có đúng claim trong top 5, nhưng thẻ cuối không giữ được claim mong đợi. H25 và H31 trả đúng đoạn trong nội dung.
- **Chấm nội dung**. Điểm trích nguyên văn chỉ kiểm một điều kiện máy có thể chấm. Chưa có hai người chấm độc lập từng phát biểu, tính đúng nghĩa và độ đầy đủ của câu trả lời. Hai ngưỡng 95% phát biểu được hỗ trợ và 90% câu được trả lời đúng, đủ chưa được xác nhận. Chưa có số liệu hành vi người dùng sau rollout.

## Độ trễ của ứng viên A

Các cột ghi p50/p95 theo mili giây, gộp quan sát của 3 lần chạy bằng median và nearest-rank p95. Với mỗi nhánh lexical có 3 lần gọi đầu tiên của client mới và 69 lần gọi tiếp theo, gồm cả hai tập. Với hội thoại có 3 lượt đầu và 177 lượt tiếp theo. Máy dùng chung, không khởi động lại PostgreSQL hoặc xóa cache. Cột đầu đo chi phí bắt đầu phía client và đường truyền đã có sẵn phía server. Các receipt lưu riêng HTTP, Server-Timing và thời gian lượt Chat.

| Luồng và cấu hình | Đầu tiên | Tiếp theo |
|---|---:|---:|
| Offline, router cũ | 0,20 / 0,21 | 0,01 / 0,05 |
| Offline, router mới | 0,83 / 2,11 | 0,02 / 0,10 |
| Lexical, Compose v1 đo baseline | 14,45 / 70,23 | 6,07 / 17,03 |
| Lexical, ranker cũ + corpus v1, cô lập | 22,49 / 39,25 | 7,95 / 34,33 |
| Lexical, ranker mới + cùng corpus v1, cô lập | 31,27 / 56,61 | 15,15 / 62,31 |
| Lexical, ranker mới + corpus ứng viên, cùng vòng đo cô lập | 17,08 / 37,28 | 12,27 / 30,28 |
| Hội thoại, Chat cũ + Knowledge đang chạy | 25,47 / 31,17 | 19,48 / 81,64 |
| Hội thoại, Chat mới + Knowledge đang chạy | 49,89 / 71,02 | 37,63 / 119,74 |
| Hội thoại, Chat mới + Knowledge ứng viên | 26,69 / 76,48 | 31,42 / 106,07 |

P95 lexical warm trên cùng corpus tăng từ 34,33 lên 62,31 ms (khoảng 81,5%, ngưỡng 20%). P95 của ba lần lần lượt là 10,15 / 50,06 / 11,52 ms với ranker cũ và 83,41 / 12,28 / 56,55 ms với ranker mới. Phép đo này trượt ngưỡng và có độ dao động cao. Corpus kích hoạt trong môi trường cô lập có các ID chunk được tạo tại lần nạp, thứ tự các kết quả bằng điểm có thể khác Compose. MRR của ranker cũ trên corpus v1 cô lập là 0,500. Chưa thử vector/provider có phí hoặc cold start của toàn stack.

## Hồi quy B và B2 sau khi khóa ứng viên A

Nhóm triển khai dùng các ca v1 đã biết để sửa router và bộ chọn claim. Các ca v2 giữ lại đã được đo trước đó. Phép đo lại dưới đây là **hồi quy trên cùng bộ v2**. Các lần chạy này chưa có bộ nghiệm thu tiến cứu mới hoặc điểm chấm độc lập của con người. Receipt, SHA và kết quả của A ở trên được giữ riêng.

- Mã Chat B có SHA-256 `2e1044a8b1ca6204311c67c9ca583b5581618a7ac6b7239b428f914a2b0926ed`. Với 24 câu kiến thức v1 đã biết, bộ chọn claim cải thiện từ 21/24 lên 24/24. Cả hai phiên bản giữ 3/3 ca thiếu bằng chứng. Khi nạp lại corpus vào cơ sở dữ liệu mới, có trường hợp chọn định nghĩa phụ thuộc thứ tự chunk đồng hạng. B2 sửa cách chọn này. Số liệu v1 là phép thử bộ chọn với phản hồi Knowledge thật.
- SHA-256 của toàn bộ package Chat B2 là `50c5e201264a9593b757022fccd560e85e42a043b66bdda26e9782dfaccda3aa`. Truy xuất B2 đọc các đoạn được chọn bằng một truy vấn SQL, giữ thứ hạng và bộ lọc. SHA-256 của `retrieval.py` là `5d59b7ca2836ba82e88fa290700292a14ce582fc9cc8e4287f1ffaff3186b5eb`. Hai corpus, ID cơ sở dữ liệu của từng nhánh, cutoff, fixture và ngưỡng được giữ xuyên suốt phép đo hiệu năng.
- Với mỗi phiên bản B và B2, chạy offline 3 lần. Chạy lexical và hội thoại fixture 3 lần trên từng nhánh Knowledge đang phục vụ và ứng viên. B và B2 cùng đạt 20/20 nguồn trên tập phát triển. Trên tập giữ lại, kết quả từng nhóm và các ID lỗi khớp bảng A. B2 đạt 25/40 nguồn offline, 28/40 nguồn trên worker, 8/11 trạng thái đúng, Hit@5 8/12 (MRR 0,521 với corpus ứng viên), 6/12 vừa đúng nguồn vừa trúng claim, 2/12 trích đúng claim và 5/5 từ chối. Có 0 lần gọi provider, 0 yêu cầu tạo allocation, 40/40 ca giữ đúng giới hạn hành động.

Cùng một vòng xoay thứ tự đo với 3 lần/nhánh, mỗi nhánh có 3 lần gọi đầu và 69 lần tiếp theo. Bảng ghi p50/p95 (ms) của B2.

| Luồng | Đầu tiên | Tiếp theo |
|---|---:|---:|
| HTTP ranker cũ + corpus v1, cô lập | 38,82 / 72,23 | 8,20 / 30,51 |
| HTTP ranker B2 + cùng corpus v1, cô lập | 40,54 / 75,13 | 11,87 / 44,93 |
| HTTP ranker B2 + corpus ứng viên, cô lập | 32,54 / 39,80 | 9,37 / 26,41 |
| Worker fixture B2 + Knowledge Compose v1 | 18,47 / 20,04 | 26,92 / 284,48 |
| Worker fixture B2 + Knowledge ứng viên | 29,82 / 40,43 | 18,14 / 95,13 |

P95 warm trên cùng corpus v1 tăng **47,3%** (30,51 → 44,93 ms). P95 từng lần là 18,22 / 31,62 / 21,99 ms với ranker cũ và 15,56 / 26,43 / 49,31 ms với B2. Cả ba lượt theo đúng thứ tự ca và cùng quy tắc tính nearest-rank như A. Lần đo trung gian B, trước thay đổi SQL, cho 27,13 → 21,80 ms. Độ dao động cao trên máy dùng chung. Phép đo chốt B2 chưa đạt ngưỡng +20%.

## HTTP thật trên Compose, worker B2 và corpus v1

Chạy cùng 17/40 kịch bản ba lần, bắt đầu lúc 22:35 GMT+7 ngày 23/11. Kết quả chất lượng từng ca và bộ đếm tool khớp ở cả ba lần. Bảng ghi mẫu số của một lần chạy. Trước khi gửi, harness đối chiếu hash mã Chat của worker đang chạy với bản B2, kiểm provider và embeddings đã tắt, đăng nhập một lần, kiểm quyền truy cập danh mục và xác nhận Portfolio đang trả `SYSTEM_PAUSED`. Worker image là `sha256:581729a9ae2bf81aa79f72445a2aee40c4ff5fd5a63e708b40b63170aca37a89`. Mỗi kịch bản tạo một hội thoại kiểm thử riêng để các câu hỏi độc lập có đúng ngữ cảnh. HTTP đi qua auth, Chat API, worker và các dịch vụ của Compose. Hồ sơ, trạng thái và cutoff là giá trị thật tại thời điểm gửi.

| Chỉ số | Số đạt/tổng số |
|---|---:|
| Đúng nguồn của phản hồi cuối | 11/17 |
| Trạng thái kiểm lại từ Portfolio, đúng danh mục, có thời điểm | 1/1 |
| Trích đúng claim vào nội dung và thẻ dẫn chứng | 2/12 |
| Thiếu bằng chứng, trả câu từ chối và citation trống | 4/4 |
| Có evidence hash khớp payload kiến thức | 10/16 |

Có 12 câu kiến thức trả lời được, 4 câu kiến thức thiếu bằng chứng và 1 hội thoại hai lượt ở trạng thái thật `SYSTEM_PAUSED`. Có 10 thẻ kiến thức, 1 thẻ trạng thái, 4 thẻ trợ giúp, 1 thẻ danh mục và 1 thẻ hồ sơ. Mọi citation thu được đều thuộc corpus v1. P50/p95 đầu-cuối HTTP qua ba lần lần lượt là 631/908, 682/1.077 và 618/895 ms, gồm thời gian xếp hàng và poll job mỗi 250 ms. Gộp 51 lượt cuối đạt 640/938 ms. Ba mẫu đầu tiên (một lượt mỗi đợt) đạt 643/738 ms, còn 48 lượt sau đạt 636/938 ms. Backend đã qua healthcheck, cache PostgreSQL được giữ nguyên.

Đối chiếu ledger cho 18 Chat job mỗi lần (tổng 54) cho thấy mỗi lần có 22 lần đọc profile, 20 lần đọc Knowledge, 2 lần đọc trạng thái và 2 lần đọc tóm tắt danh mục. Có 0 lần gọi tool tạo allocation, 0 liên kết dependency, 0 liên kết proposal và 0 hàng provider. 23 ca giữ lại còn lại cần mốc lịch sử, trạng thái có kiểm soát, điều kiện đổi chủ/danh mục hoặc một loại đề xuất ghim xác định. Chúng được đo trong worker fixture. Receipt live không lưu prompt, ID người dùng, ID danh mục hoặc số tiền. [Harness HTTP Compose](../../scripts/eval_knowledge_compose.py)

## Kiểm tra cuối trên demo

Sau ba vòng Chromium của B2 và restart Web, Chat API, Chat worker, Portfolio API, bộ kiểm tra mở lại đúng đề xuất cũ từ `output/concise-explanation/paid-final-receipt.json`. ID đề xuất `23df1353-2021-4d8d-bc19-c232b1f70148`, facts, evidence, tin nhắn và usage khớp receipt. Sau nghiệm thu, bốn dịch vụ đã trở lại đúng image và cấu hình trước thử nghiệm. Đọc lại cùng receipt vẫn đạt. Knowledge đang phục vụ `knowledge-vi-v1`, hash `a8d21c647e8a514510873dce49b8414b7fc32921840c74b53a383b189e9600d4`, qua `knowledge-retrieval-v2`. Chi phí provider phát sinh trong đợt bằng 0 USD. [Kết quả Chromium và cách verify](RAG_STATUS_BROWSER_2026_11_23.md).

Để kiểm riêng receipt cũ trên demo, từ gốc repo chạy:

```sh
.venv-software/bin/python scripts/smoke_allocation_explanation.py --verify-receipt \
  --receipt output/concise-explanation/paid-final-receipt.json
```

## Tái lập

Từ gốc repo, giữ nguyên demo, dùng script phục vụ Knowledge cô lập theo hướng dẫn và token đặc quyền tối thiểu của verifier thử nghiệm. Thông tin cấu hình ba nhánh nằm trong [hướng dẫn Knowledge](KNOWLEDGE_RAG.md). Các receipt của lần đánh giá này nằm trong thư mục local `output/rag-status-20261123/`. Mỗi dòng kết quả chỉ chứa mã ca, phân loại, mã lỗi, counters và thời gian.

```sh
.venv-software/bin/python -m pytest -q tests/software/test_eval_knowledge_status.py

eval_dir=output/rag-status-20261123
replay_dir=$(mktemp -d)
for pass in 1 2 3; do
  for mode in offline lexical conversation; do
    PYTHONPATH="$PWD/$eval_dir/baseline-src" .venv-software/bin/python scripts/eval_knowledge.py \
      --version v2 --mode "$mode" --run "$pass" --output "$replay_dir/baseline-$mode-$pass.json"
    EVAL_KNOWLEDGE_FIXTURE_TOKEN=p3-local-read PYTHONPATH="$PWD/$eval_dir/candidate-src" \
      .venv-software/bin/python scripts/eval_knowledge.py --version v2 --mode "$mode" \
      --knowledge-url http://127.0.0.1:18966 --run "$pass" --output "$replay_dir/candidate-$mode-$pass.json"
  done
done
```

Bỏ `PYTHONPATH` để chạy đúng working tree hiện tại. Bỏ `--knowledge-url` để dùng Compose trên cổng 8006. Đo ranker trên cùng corpus bằng chế độ lexical với endpoint 18967 (cũ/v1) và 18968 (mới/v1), luân phiên thứ tự cùng endpoint 18966. Dùng `--split dev` khi phát triển. Bộ v1 tiếp tục chạy bằng `--version v1 --mode offline` hoặc `--mode lexical`.

Để tái lập B2, thay `candidate-src` bằng `candidate-b2-src`, dùng retrieval B2 ở endpoint 18966 và 18968, đồng thời dùng tên output mới. Thay bằng `candidate-b-src` để đối chiếu B trước bản sửa thứ tự. Các receipt B2 bắt đầu bằng `v2-candidate-b2`, `v2-active-b2`, `v2-matched-b2`, và `v2-live-compose-b2.json`. Chạy HTTP thật một lần sẽ tạo hội thoại kiểm thử mới.

```sh
PYTHONPATH="$PWD/output/rag-status-20261123/candidate-b2-src" .venv-software/bin/python \
  scripts/eval_knowledge_compose.py --run --output "$replay_dir/live-compose-b2.json"
```
