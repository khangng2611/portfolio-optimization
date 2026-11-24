# Kiểm tra OpenAI trên câu trả lời RAG tiếng Việt

Đợt ngày 23/11/2026 có ngân sách người dùng cho phép tối đa 10 USD. Runbook dành cho một đợt kiểm tra nhỏ bằng `gpt-6-luna` qua Responses API và prompt chọn chunk hiện có. Câu trả lời hiển thị trích lại các claim mà backend đã kiểm. Chín lượt bao gồm hai cặp định nghĩa/giới hạn, một câu nối tiếp dùng đại từ, tuổi dữ liệu NAV, câu ngoài corpus, câu nhiều vế và yêu cầu kiểm trạng thái hiện tại.

## Giới hạn chi phí

Worker kiểm approval, ngân sách và số lượt bằng ledger PostgreSQL trước khi gọi model. Đợt này cấu hình 0,04 USD, giới hạn 10 lời gọi văn bản suốt approval, 12.000 byte payload và 384 output token mỗi lời gọi. Tổng phần dành trước tối đa là 0,017 USD. Embedding và contextual response tắt. Model có thể chọn chunk hoặc từ chối. Receipt ghi riêng những chunk model đã chọn, các claim cuối được trích và số liệu sử dụng do API trả về.

Giá chuẩn ngày kiểm tra là 0,10 USD/triệu token đầu vào, 0,01 USD/triệu token đầu vào cache và 0,50 USD/triệu token đầu ra. Adapter dùng 0,125 USD/triệu token cho toàn bộ đầu vào để bao gồm chi phí ghi cache thường. Chi phí quy đổi theo token có thể khác hóa đơn của tổ chức. [Giá model](https://developers.openai.com/api/docs/models/gpt-6-luna) · [Bảng giá OpenAI](https://developers.openai.com/api/docs/pricing)

## Cách chạy

Dùng checkout hiện tại cùng các image của Compose `portfolio-auth-demo`. Mỗi lần chạy khởi tạo PostgreSQL/pgvector trên tmpfs, migrate các DB riêng cho Chat, Portfolio và Knowledge, chạy chính các API/worker của repo và đăng nhập qua dịch vụ OIDC đang phục vụ local. Corpus ứng viên được index và kích hoạt trong DB của lần thử. Các dịch vụ demo và corpus đang phục vụ giữ nguyên cấu hình. OpenAI chỉ nhận câu hỏi và các đoạn ứng viên trong những lượt thực sự chọn claim. Dữ liệu từng hội thoại trong QA là dữ liệu kiểm thử.

```sh
.venv-software/bin/python scripts/eval_knowledge_openai.py --dry-run
.venv-software/bin/python -m pytest -q tests/software/test_eval_knowledge_openai.py
.venv-software/bin/python scripts/eval_knowledge_openai.py --offline \
  --output output/rag-quality-v3/openai-offline.json
```

Lệnh sau tiêu ngân sách đã duyệt một lần. Approval có marker bền vững ngoài Git để tránh chạy lại trên ledger mới. Mở receipt hiện có để xem kết quả, kể cả khi lượt đã dừng giữa chừng.

```sh
.venv-software/bin/python scripts/eval_knowledge_openai.py --execute \
  --approval-id rag-quality-v3-20261123 \
  --output output/rag-quality-v3/openai-check.json
```

Receipt quyền 0600 lưu câu hỏi kiểm thử, nguyên văn câu trả lời, hash bằng chứng, nguồn/claim, mức bao phủ, usage và trạng thái chọn chunk của OpenAI. Grader kiểm lời đáp chính xác bằng nội dung đã lưu và các claim cho phép, kiểm hash văn bản/corpus/evidence, cùng lời báo thiếu nguồn nếu chỉ trả lời được một phần. Điểm này bổ sung cho đánh giá trên bộ giữ lại và việc đọc từng câu trả lời.

## Kết quả đợt đối chứng V3

Chạy đủ 9 lượt qua các API thật trong môi trường tách riêng. Corpus ứng viên có hash `83759093ce950cc5f2a781eddf91049d181408fbdd69016bc931562c57d3d094`. Cả hai chế độ offline và bật OpenAI đều đạt **9/9 kiểm tra tự động về loại nguồn, câu trích, hash và coverage**. Đọc trực tiếp từng câu trả lời cho kết quả **8/9 trả lời đủ ý**. Đây là một lần đánh giá ngữ nghĩa bởi trợ lý AI.

| Người dùng cần biết | Nội dung thực tế |
|---|---|
| EW và nhược điểm | Nêu quy tắc chia đều. Câu nối tiếp hiểu đúng EW và giải thích danh mục vẫn có thể lỗ. Câu hỏi về bảo đảm lợi nhuận trích đúng `ew-limit`. |
| Views ML | Câu hỏi về độ chắc chắn nhận giải thích có thể dự báo sai chiều. Câu hỏi định nghĩa lại nhận đoạn nói model phải được duyệt và tương thích. Đoạn `ml-views-definition` đúng ID nhưng thiếu ý chính rằng view là một ước lượng lợi suất. |
| Tuổi dữ liệu VFF | Nêu rõ hai chính sách cùng đo tuổi từ ngày NAV và phân biệt cách xác định thời điểm khả dụng. |
| Câu ngoài corpus và câu nhiều vế | Một lượt từ chối đúng. Lượt nhiều vế giải thích EW, nói rõ thiếu căn cứ cho giá quỹ ngày mai. |
| Trạng thái | Đọc trạng thái tạo đề xuất tạm dừng, không tiêu token. |

OpenAI trả 6 lần chọn đã xác minh, **5.515 input token, 501 output token**. Theo mức tính bảo thủ của adapter, chi phí ước tính **0,000939875 USD**. Câu nối tiếp dùng đúng chủ đề trước, câu ngoài corpus và câu trạng thái được xử lý với 0 cuộc gọi model. Cả 6 lượt có usage riêng trên job API. Không đối soát hóa đơn tổ chức.

Đối chiếu sau restart của riêng V3 **chưa xác minh**. Cả 9 packet trước restart đã có câu hỏi, câu trả lời, hash và token. Bước đọc lại dùng cổng host ngẫu nhiên cũ của Docker sau khi restart, hết thời gian chờ rồi môi trường tạm được dọn. Receipt gốc vẫn mang trạng thái chưa hoàn tất bước kiểm tra bổ sung. Bộ kiểm thử kế tiếp đọc lại địa chỉ công bố sau restart và ghi packet trước khi kiểm persistence. [Receipt gốc](../../output/rag-quality-v3/openai-check.json) · [Điểm ngữ nghĩa từng câu](../../output/rag-quality-v3/paid-preparation/semantic-v3.json)

## Lượt giữ lại V4

Cohort được xác định trước bằng các điều kiện kiểm thử được qua API thật. Harness nhận tất cả kịch bản nguồn Knowledge trong bộ v4 đã khóa có thể chạy với thời điểm hiện tại và trạng thái thật. Giữ thứ tự các tin nhắn trong từng kịch bản và dùng một hội thoại riêng cho mỗi ca. Những ID đòi hỏi mốc lịch sử hay trạng thái kiểm soát được ghi vào `skipped_ids`. Trường `CHAT_KNOWLEDGE_SEMANTIC_SELECTION` của worker tạm bật. Receipt lưu ý mà người dùng hỏi, nguyên văn trích dẫn, chunk đã truy xuất, quote model chọn và việc quote có xuất hiện nguyên văn trong nguồn.

Đợt hai được cấu hình 0,16 USD và tối đa 48 lời gọi, dành trước tối đa 0,0816 USD. Hai đợt có chung khóa ngân sách trên ổ đĩa. Tổng dành trước cả hai đợt là 0,0986 USD dưới ngưỡng nội bộ 0,10 USD. Việc restart, tạo DB kiểm thử mới hay đổi tên file đầu ra vẫn giữ nguyên marker của từng approval. Lệnh dry-run đọc fixture và tính phạm vi kiểm thử với 0 lần gọi trả phí.

```sh
.venv-software/bin/python scripts/eval_knowledge_openai.py --protocol heldout-v4 --dry-run
snapshot="$PWD/output/rag-quality-v4/owner-src"
export PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp/rag-qa-host-v4
export PYTHONPATH="$snapshot/services/chat/src:$snapshot/services/knowledge/src:$snapshot/packages/contracts/src"
.venv-software/bin/python scripts/eval_knowledge_openai.py --protocol heldout-v4 --offline --source-root "$snapshot" \
  --output output/rag-quality-v3/openai-offline-v4-isolated.json
.venv-software/bin/python scripts/eval_knowledge_openai.py --protocol heldout-v4 --execute \
  --source-root "$snapshot" --approval-id rag-quality-v4-20261123 --output output/rag-quality-v3/openai-check-v4.json
```

Snapshot trên máy kiểm thử chứa package Chat/Knowledge đã khóa cho V4, source Portfolio/contracts cùng phiên bản, Alembic migrations và manifest Markdown. Bước khởi động đầu tiên trên checkout dừng trước khi có câu trả lời hay token. Stack chạy chính thức mount snapshot chỉ đọc, dùng cache Python tách riêng. Một checkout mới có thể kiểm thử source hiện hành bằng cách đặt `snapshot="$PWD"` và chọn một đường dẫn output mới cho lần offline.

### Kết quả V4

Đã chạy 18 câu Knowledge theo thời điểm thật. Bộ 40 ca còn có 21 ca ngoài nhóm Knowledge và một ca Knowledge đòi mốc lịch sử. Mười tám cặp dùng cùng corpus `83759093…3d094`, cùng fixture `29877078…988c6d` và cùng Chat `775166e1…c1ed2e`.

| Qua API thật | Đúng claim và coverage | Câu có tài liệu | Từ chối đúng khi thiếu tài liệu | Trung vị từ gửi đến nhận |
|---|---:|---:|---:|---:|
| Tắt OpenAI | 11/18 | 8/14 | 3/4 | 632 ms |
| Bật OpenAI, kiểm quote | 14/18 | 10/14 | 4/4 | 2.613 ms |

OpenAI cải thiện ba câu về sai số dự báo ML, đánh đổi lợi nhuận/rủi ro của MVO và câu ngoài corpus về rho quyền chọn. Hai câu về hiệu lực của việc chấp nhận đề xuất và thay đổi hồ sơ vẫn bị chuyển sang bước chọn danh mục. Với backtest, model chọn nguyên văn câu phù hợp nhưng bộ kiểm từ chối. Với target hết hạn, retrieval bỏ sót đoạn cần thiết và model từ chối theo đúng các đoạn đã thấy.

Đọc nội dung thực của 18 câu bật provider cho kết quả **12 đầy đủ, 2 đúng một phần, 4 bỏ sót** theo đánh giá của một trợ lý AI. Nhận xét chặt hơn phép chấm theo ID đối với hai câu. Đoạn về trượt giá nhắc chi phí giao dịch nhưng chưa giải thích giá khớp bất lợi. Đoạn về turnover nói đến mua bán tái cơ cấu nhưng chưa diễn đạt rõ mức độ thay đổi của danh mục. Có 11 lượt kết thúc bằng `VERIFIED_QUOTES`, gồm một lượt model trả danh sách nguồn rỗng vì thiếu căn cứ. Cả 11 đoạn quote model đề xuất đều khớp nguyên văn, bao gồm một đoạn bị validator từ chối.

OpenAI trả usage cho **16 lời gọi**, gồm 12 lần chọn bằng chứng và 4 lần phân loại ý định. Tổng thực tế **14.355 token vào, 1.351 token ra**, ước tính bảo thủ **0,002469875 USD**. Tổng V3–V4 là **0,003409750 USD**. Không có lượt thiếu usage. Đã restart Chat API và worker, đọc lại chính 18 job/message cũ, đối chiếu nguyên vẹn hash, usage và toàn bộ ledger. [Receipt offline](../../output/rag-quality-v3/openai-offline-v4-isolated.json) · [Receipt OpenAI có persistence](../../output/rag-quality-v3/openai-check-v4.json) · [Điểm ngữ nghĩa từng câu](../../output/rag-quality-v3/paid-preparation/semantic-v4.json)

## Browser trên stack cô lập

Từ gốc repo, dùng image Web đã build và snapshot V5 có cấu trúc giống repo. Launcher dùng OIDC local, Redis mới cho BFF và PostgreSQL tạm cho các owner. Các container có tên ngẫu nhiên. Receipt chỉ lưu tên container QA, địa chỉ loopback và hash corpus.

```sh
.venv-software/bin/python scripts/serve_knowledge_eval_web.py \
  --source-root "$PWD/output/rag-quality-v5/owner-src" --image portfolio-rag-v5-qa-web:local \
  --metadata output/rag-quality-v5/browser-stack.json
```

Trong terminal thứ hai, chạy pha đầu đúng một lần để tạo hội thoại, hỏi nối tiếp, mở nguồn và ghi hash chính hội thoại đó. Sau khi restart ba container chỉ định trong receipt của launcher, pha hai đăng nhập lại, đọc lịch sử cũ và so hash. Cấu hình `RAG_BROWSER_SUITE` xác định thư mục receipt. Pha tạo trả lỗi nếu đường dẫn receipt gốc đã tồn tại.

```sh
cd apps/web
export PLAYWRIGHT_BASE_URL=http://127.0.0.1:3138 RAG_BROWSER_SUITE=v5
RAG_V3_BROWSER_MODE=exercise ./node_modules/.bin/playwright test knowledge.e2e.ts -g 'real RAG definition'
python3 - <<'PY'
import json, re, subprocess
from pathlib import Path
qa = json.loads(Path("../../output/rag-quality-v5/browser-stack.json").read_text())
names = [qa[k] for k in ("chat_api", "worker", "web")]
assert all(re.fullmatch(r"rag-qa-[0-9a-f]{12}-(chat-api|chat-worker|web)", n) for n in names)
subprocess.run(["docker", "restart", *names], check=True)
PY
curl --silent --show-error --fail --retry 20 --retry-connrefused --retry-delay 1 "$PLAYWRIGHT_BASE_URL/health/live"
RAG_V3_BROWSER_MODE=verify ./node_modules/.bin/playwright test knowledge.e2e.ts -g 'real RAG definition'
touch ../../output/rag-quality-v5/browser-stack.stop
```

## Lượt giữ lại V5

V5 dùng bộ câu mới `d9051b0e…edc66b` và source Chat đã khóa `38276c02…5d3e79`. Mỗi chế độ có 14 câu có tài liệu và 4 câu ngoài corpus hợp lệ theo đồng hồ thật. Bản chạy offline đầu tiên dừng ở lời gửi thứ 18 do mất phản hồi HTTP. Receipt 17 câu được giữ riêng. Harness thử gửi lại đúng nội dung và cùng idempotency key khi mất phản hồi. Chạy lại trên stack tách riêng thu đủ 18 lời đáp.

| Qua API thật | Đúng claim và coverage | Câu có tài liệu | Từ chối đúng khi thiếu tài liệu | Trung vị từ gửi đến nhận |
|---|---:|---:|---:|---:|
| Tắt OpenAI | 11/18 | 7/14 | 4/4 | 899 ms |
| Bật OpenAI, kiểm quote | 14/18 | 10/14 | 4/4 | 2.048 ms |

Kiểm ngữ nghĩa trực tiếp của trợ lý AI chấm **12 đầy đủ, 2 đúng một phần, 4 bỏ sót** trong câu trả lời của chế độ bật OpenAI. Hai câu thiếu cụ thể liên quan đến chiều tác động của độ tin cậy trong BL và ý nghĩa đo mức độ thay đổi của turnover. Bốn câu bỏ sót hỏi về khớp lệnh khi chấp nhận đề xuất, tuổi dữ liệu, rủi ro còn lại sau đa dạng hóa và tác động của chat lên hồ sơ. Bảy lượt không cần gọi model hoặc thiếu ứng viên phù hợp đã kết thúc qua đường xử lý lexical, một lượt chuyển sang chọn danh mục. Chi tiết nguồn, lý do và nguyên văn được giữ trong receipt.

**10 lời gọi OpenAI chọn bằng chứng**, **11.398 input + 1.073 output token**, **0,001961250 USD** ước tính theo adapter. Mười tám hash lời đáp, usage và ledger được kiểm lại sau khi restart Chat API/worker. Tổng cả ba đợt model văn bản là **0,005371000 USD**. Chi phí đối soát hóa đơn tổ chức chưa chạy. [Receipt offline](../../output/rag-quality-v5/openai-offline-complete.json) · [Receipt OpenAI](../../output/rag-quality-v5/openai-check.json) · [Đánh giá ngữ nghĩa](../../output/rag-quality-v5/semantic-openai.json)

```sh
snapshot="$PWD/output/rag-quality-v5/owner-src"
export PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp/rag-qa-host-v5
export PYTHONPATH="$snapshot/services/chat/src:$snapshot/services/knowledge/src:$snapshot/packages/contracts/src"
.venv-software/bin/python scripts/eval_knowledge_openai.py --protocol heldout-v5 --dry-run
.venv-software/bin/python scripts/eval_knowledge_openai.py --protocol heldout-v5 --source-root "$snapshot" \
  --offline --output output/rag-quality-v5/openai-offline-complete.json
.venv-software/bin/python scripts/eval_knowledge_openai.py --protocol heldout-v5 --source-root "$snapshot" \
  --execute --approval-id rag-quality-v5-20261123 --output output/rag-quality-v5/openai-check.json
```

### Đối chứng embedding thật

V5 có thêm một lượt tách riêng dùng `text-embedding-3-small`, 1.536 chiều, để kiểm vai trò của pgvector. Worker Knowledge index 30 đoạn trong 13 tài liệu; worker Chat có thể tạo embedding cho câu thực sự đi vào Knowledge. Cả hai ledger trong DB mới dùng chung approval và trần 0,025 USD, mỗi owner được tối đa 20% trần để gọi embedding. Từng owner vì vậy tối đa 31 lời gọi × 0,00016 USD. Các lời gọi LLM văn bản bị giới hạn ở 0 trong lượt này. Tổng dành trước tối đa của cả bốn lượt là 0,19012 USD so với ngưỡng nội bộ 0,20 USD. Giá quy đổi embedding thường là 0,02 USD/triệu token đầu vào. [Giá model OpenAI](https://developers.openai.com/api/docs/models/text-embedding-3-small)

```sh
.venv-software/bin/python scripts/eval_knowledge_openai.py --protocol hybrid-v5 --dry-run
.venv-software/bin/python scripts/eval_knowledge_openai.py --protocol hybrid-v5 --source-root "$snapshot" \
  --execute --approval-id rag-embeddings-v5-20261123 --output output/rag-quality-v5/embedding-check.json
```

Index tạo vector thật cho đủ **30/30 đoạn** trong DB mới. Knowledge ghi 30 invocation xác minh, 1.828 token, **0,00003656 USD**. Chat ghi 17 query embedding xác minh, 508 token, **0,00001016 USD**, không có cuộc gọi model văn bản. Tổng embedding **0,00004672 USD**. Mười bảy lượt trả evidence `HYBRID`. Một câu hỏi đi sang bước chọn danh mục trước retrieval. Sau restart, đã đối chiếu lại 18 job/lời đáp cũ, query ledger và 30 receipt index. [Receipt embedding](../../output/rag-quality-v5/embedding-check.json)

| V5, toàn bộ 18 ca qua Chat/owner thật | Hit@5 trong 14 câu có nguồn | Trích đúng và đủ coverage trong 14 câu có nguồn | Từ chối đúng ở 4 câu ngoài corpus |
|---|---:|---:|---:|
| Lexical, chọn bằng quy tắc | 10/14 | 7/14 | 4/4 |
| Lexical, cho phép selector OpenAI | 10/14 | 10/14 | 4/4 |
| Hybrid embedding thật, chọn bằng quy tắc | 13/14 | 8/14 | 4/4 |

Hit@5 ở bảng này đo những đoạn chính Chat đã truy xuất theo route thực tế, kể cả khi không đi vào Knowledge. Hybrid đưa đúng nguồn vào top 5 cho ba câu bổ sung về tuổi dữ liệu, đa dạng hóa và tác động của chat lên hồ sơ. Chỉ câu về đa dạng hóa chuyển thành câu trả lời trích đúng. Hai câu thiếu nguồn về CDS spread và convexity nhận candidate không liên quan khi dùng vector, sau đó selector từ chối đúng. Chi phí ước tính tất cả các đợt là **0,005417720 USD**. Lượt kết hợp hybrid với selector văn bản chưa chạy.
