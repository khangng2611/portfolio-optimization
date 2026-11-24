# Knowledge/RAG local MVP

Knowledge is an owner service, not an investment engine. Chat renders only approved
claim text or canonical Portfolio facts. It never creates allocations from a
knowledge question and cannot accept targets, trade or promote models. Numerical
facts, `facts_hash`, confirmations and acceptance keep their original contracts.

The default read path ranks published PUBLIC Markdown passages in PostgreSQL. The
optional Chat worker setting `CHAT_KNOWLEDGE_SEMANTIC_SELECTION=1` asks the existing
budgeted OpenAI adapter for exact quotations from those candidates. Each selection
must match the candidate hash, chunk ID, source text and permitted scope. Chat
renders the stored passages and records the corpus version and evidence hash.
The setting defaults to zero and uses the existing approval ledger. Query
embedding has a separate switch. QA measured text selection on lexical results and, in a separate run,
real document/query embeddings with the local passage selector.

### Kiểm tra Chat chọn nguồn cho câu hỏi về phân bổ

Chat đọc mục tiêu đã chấp nhận qua Portfolio, giải thích đề xuất qua bản ghi đề xuất và tra định nghĩa qua Knowledge. Khi cần phân biệt các nguồn, OpenAI nhận câu hỏi đã lọc cùng ba dấu hiệu về ngữ cảnh (đã chọn danh mục, có đề xuất tham chiếu, đang chờ chọn danh mục). Kết quả phân loại chỉ chứa tên nguồn. Backend kiểm tra quyền và lấy ID từ ngữ cảnh của lượt hỏi. Nếu thiếu quota, timeout hoặc kết quả không hợp lệ, Chat hỏi người dùng chọn nguồn. Lượt làm rõ có thể nối tiếp bằng “bản đã lưu”, “đề xuất đang mở” hoặc “khái niệm”.

Chạy lần lượt các chế độ QA để cùng dùng tài nguyên Docker. Dùng ID danh mục của tài khoản QA `alice` đã có mục tiêu được chấp nhận. Mỗi lần chạy ghi một receipt mới. Stack dùng Chat và Knowledge riêng, xác thực thật và một instance Portfolio chạy mã đang kiểm tra. Instance này dùng DB Portfolio của demo để đọc đúng bản ghi đã lưu và cấp grant cho từng job QA. Migrations chỉ chạy trên DB QA tạm.

```sh
.venv-software/bin/python scripts/eval_source_routing.py --mode dry-run
.venv-software/bin/python scripts/eval_source_routing.py --mode offline --portfolio "$QA_PORTFOLIO_ID" --output output/routing-offline.json
.venv-software/bin/python scripts/eval_source_routing.py --mode quota --portfolio "$QA_PORTFOLIO_ID" --output output/routing-quota.json
.venv-software/bin/python scripts/eval_source_routing.py --mode openai --portfolio "$QA_PORTFOLIO_ID" --output output/routing-openai.json
```

`quota` bật adapter với hạn mức bằng 0. `openai` giữ chỗ tối đa 12 lượt văn bản (0,0204 USD) vào cùng sổ ngân sách QA. Bộ câu tiếng Việt được khóa bằng SHA-256. Kiểm tra đối chiếu tool thực thi, bản ghi mục tiêu, các tỷ trọng dương trong câu trả lời và trích dẫn cho câu hỏi định nghĩa. Sau khi restart worker, QA đọc lại từng tin nhắn và so hash với receipt ban đầu.

See the [prospective Vietnamese evaluation](RAG_QUALITY_V5_2026_11_23.md) and
[OpenAI runbook and usage](RAG_OPENAI_QUALITY_2026_11_23.md) for the tested
checkout, corpus and outstanding release gates.

## Kiểm thử câu hỏi nối tiếp và trích dẫn theo từng ý · 24/11/2026

Ba cờ ở Chat worker có thể bật riêng trong cấu hình triển khai. Mặc định của Compose là `0`. PostgreSQL và pgvector tiếp tục phục vụ corpus Markdown. Các thay đổi dùng API, bảng ledger và checkpoint hiện hữu.

| Cờ | Hành vi khi bật |
| --- | --- |
| `CHAT_CONTEXT_FOLLOWUPS` | Đọc đề xuất đã ghim hoặc được tham chiếu trong cùng hội thoại và danh mục. “Thế còn POW?” tiếp tục ý hỏi trước. Chat lấy tỷ trọng, vốn lúc tính và dữ kiện các nhánh từ Portfolio. Một câu mơ hồ đủ ngữ cảnh có thể dùng một lần phân loại `proposal_focus`. |
| `CHAT_KNOWLEDGE_CLAUSES` | Gửi tối đa sáu phần của câu hỏi cùng các đoạn ứng viên cho bộ chọn. Backend đối chiếu từng chỉ mục, mã đoạn, trích văn, phạm vi và hash. Thẻ `structured.knowledge.clause_evidence` lưu quan hệ giữa ý hỏi và đoạn nguồn. `PARTIAL` nêu phần còn thiếu. Receipt cũ tiếp tục đọc theo phiên bản của nó. |
| `CHAT_KNOWLEDGE_REWRITE` | Khi lexical trả `NO_EVIDENCE`, thử một truy vấn ngắn với cùng corpus và cutoff. Có thể dùng tên tài liệu công khai vừa được trích. Ledger giới hạn một lần `query_rewrite` cho mỗi job. Lượt này dùng lexical. Bật thêm cờ clauses để chấm đoạn tìm được theo câu hỏi gốc. |

**Tái lập.** Chạy các lệnh từ thư mục gốc với demo Auth và các owner service đang hoạt động. Harness dựng PostgreSQL tạm và chạy migration trong database QA. Bản chạy cho đề xuất đã lưu đọc dữ kiện của đề xuất thuộc tài khoản nghiệm thu.

```sh
.venv-software/bin/python -m pytest -q tests/software
.venv-software/bin/python scripts/eval_proposal_followup.py --mode dry-run
.venv-software/bin/python scripts/eval_knowledge_openai.py --protocol clauses2-v5 --dry-run
.venv-software/bin/python scripts/eval_knowledge_openai.py --protocol clauses2-v6 --dry-run
.venv-software/bin/python scripts/eval_knowledge_openai.py --protocol rewrite-v6 --dry-run
.venv-software/bin/python scripts/eval_knowledge_openai.py --protocol combined-v6 --dry-run
```

Các protocol lexical nhận `--offline --output output/<tên-mới>.json` để chạy Chat và Knowledge thật với provider tắt. Protocol combined cần embedding thật cho cả tài liệu và truy vấn. Đợt trả phí thay `--offline` bằng `--execute --approval-id <approval đã duyệt cho protocol>`. Với các protocol nêu trên, ID của đợt này lần lượt là `rag-clauses2-v5-20261124`, `rag-clauses2-v6-20261124`, `rag-rewrite-v6-20261124`, `rag-combined-v6-20261124`. Một lần thực thi giữ chỗ trước khi gọi provider. Ledger theo đợt ở ngoài Git ngăn chạy lại cùng approval trên cùng workspace, kể cả với tên output mới. Đọc packet `COMPLETE` để đối chiếu `job_id`, `message_hash`, usage và `same_receipts_after_restart`.

Bộ V6 khóa 40 ca bằng SHA-256 trước nghiệm thu. Trong đó 36 câu có ít nhất một ý trả lời được, gồm bốn câu có cả ý thiếu nguồn. Bốn câu còn lại cần từ chối hoàn toàn. Hit@5 đếm câu có đoạn phù hợp trong năm kết quả đầu. Citation hit yêu cầu đoạn phù hợp xuất hiện trong câu trả lời cùng trích dẫn khớp hash. Người chấm đọc câu trả lời và nguồn để quyết định câu nào trả lời đủ tất cả ý. Các ngưỡng và kết quả phát hành nằm trong [trạng thái triển khai](IMPLEMENTATION_STATUS.md).

## Developer-managed provider policy — 18/11/2026

Provider access is controlled by deployment configuration. The composer has no
OpenAI checkbox or outbound-data popover. CHAT_LLM_ENABLED=1 enables Chat model
access when provider/key and the required budget are configured. Set it to 0 to
stop new model calls, including reuse through the invocation ledger. Independent
CHAT_QUERY_EMBEDDINGS_ENABLED=1 enables query embedding only when Chat is enabled
and a new embedding budget is available. It defaults to 0, retaining lexical
retrieval. Keep CHAT_CONTEXTUAL_REPLIES=1 for contextual reply generation.

Historical llm_consent/consent_version database fields remain for receipt
compatibility. They do not authorize outbound calls. POST conversation preferences
now returns 403 after checking ownership. Conversation creation also rejects
requests to grant the historical consent fields. No migration or backfill occurs.
Earlier consent-v1/v2 instructions in this runbook describe the previous policy.

For the current demo at http://127.0.0.1:3100, preserve the ignored
.generated/managed-web-port.yaml overlay. It pins both published port and
APP_ORIGIN. Use the current operator env file when recreating services:

```sh
docker compose -p portfolio-auth-demo --env-file infra/local/.generated/.env --env-file infra/local/.generated/chat-contextual.env -f infra/local/compose.yaml -f infra/local/compose.chat-llm.yaml -f infra/local/.generated/managed-web-port.yaml up -d --no-deps chat-api chat-worker web
```

The contextual v2 eval fixture expresses developer policy. Run enabled cases
D01–D09 and disabled case D10 separately under matching server configuration.
Provider keys, quotas and budget remain server-side. The user cannot change them
through the conversation API or UI. Existing receipt verification remains valid.


## Ownership and storage

- Knowledge API: localhost 8006, `/docs`, `/health/live`, `/health/ready`.
- `knowledge-postgres` is a separate PostgreSQL 17.11 cluster with only a **new**
  `knowledge-data` volume and no published DB port. The existing cluster is unchanged.
- Official pgvector v0.8.1, commit `778dacf20c07caf904557a88705142631818d8cb`;
  PostgreSQL base digest and verified local image content ID are recorded in
  `infra/local/knowledge-postgres/build-pin.json`. This is a local content digest,
  not a claimed registry distribution digest; no image was pushed.
- Owner/migrator/runtime roles are separate. Privileged bootstrap installs
  pgvector. Runtime cannot create tables, become owner, rewrite document versions,
  delete chunks or update/delete lifecycle audit. Chat evidence is append-only.
- Knowledge revisions: `k10000000001` corpus/documents/chunks/membership/jobs/audit/
  embedding ledger; `k10000000002` approval budgets; `k10000000003` lifecycle epoch; `k10000000004` durable indexing-key aliases.
  Chat revision `c10000000003` adds consent version (legacy default 1), retrieval
  checkpoint, immutable evidence and invocation reservations. No cross-service FK.
- Index jobs: DRAFT → INDEXING → READY/FAILED, leased/fenced and bounded to five
  attempts. Corpus membership becomes visible only after a READY pointer swap.
  An operator's `If-Match` also fences a stale swap against a different corpus.
  Old cited versions are retained on deactivation and rollback.

## Local setup (no provider calls)

Use the existing software venv and local generated credentials. The normal setup
entrypoint adds Knowledge without rotating existing secrets or deleting volumes:

```sh
python3 scripts/setup_software.py up --tracing
.venv-software/bin/python -m knowledge_service.cli validate
.venv-software/bin/python scripts/smoke_knowledge.py
.venv-software/bin/python scripts/smoke_chat_knowledge.py
.venv-software/bin/python scripts/smoke_knowledge_lifecycle.py
.venv-software/bin/python infra/local/verify_knowledge.py
```

`smoke_knowledge.py` explicitly indexes and activates the project-authored v1 corpus;
API POST itself only enqueues. These gates create disposable local jobs,
conversations and a corpus version. Lifecycle verification restores the original
active corpus in `finally`; it preserves old citations and all existing business
results. It does not accept any target. The browser canonical gate below accepts
one existing test proposal only through its explicit UI action.

A deployment that already has the old Chat OpenAI overlay enabled must first apply
its normal **non-paid** Compose configuration to Chat worker. Do not carry a paid
overlay into these commands. New Knowledge paid budget defaults to zero; API keys
and old consent/quota are not budget authorization. Do not change Auto Recharge.

CLI commands use UTF-8 files below `services/knowledge/corpus` only. The manifest
contains stable claim IDs, sources/locators, content hashes, actual availability,
parser/chunker versions and provenance review. Each approved paragraph is a chunk.
No URL fetching, PDF, HTML, arbitrary file path, private corpus or admin upload UI.
Limits: 64 KiB/document, 1 MiB/batch/body, 1000 chunks/corpus. Traversal, escaped
symlinks, hash mismatch, unknown versions and nonpublic notes are rejected.

For the disposable local test identity, the wrapper obtains tokens in memory:

```sh
.venv-software/bin/python scripts/knowledge_operator.py list
.venv-software/bin/python scripts/knowledge_operator.py index --key knowledge-local-v1
```

For explicit `activate`/`deactivate`, the CLI requires the selected corpus `--corpus-id`,
current `--version` returned by `list`, a stable `--key`, and `--reason`. Those values
are local identities, never checked into documentation. Repeat the same key/body
for uncertain responses; different bodies conflict. Rollback explicitly activates
an existing READY version with its **current** version precondition. `--receipt`
keeps a token-free lifecycle receipt outside Git; `verify-receipt` never creates
another job. A later intentional lifecycle change invalidates that mutable
lifecycle receipt; immutable Chat citation receipts remain verifiable.

## API contracts

| Route | Authorization / behavior |
| --- | --- |
| POST `/api/v1/knowledge/indexing-jobs` | `data-operator`, `knowledge:write`, Idempotency-Key; normalized inline manifest only; 202 |
| GET `/api/v1/knowledge/indexing-jobs/{id}` | Operator + `knowledge:read`; safe state/chunk count |
| GET `/api/v1/knowledge/corpora` | Operator + `knowledge:read`; bounded limit/offset and count headers |
| POST `/api/v1/knowledge/corpora/{id}/activate` or `/deactivate` | Operator + write scope, If-Match, key, reason; audited atomic swap |
| POST `/internal/v1/knowledge/retrieve` | `knowledge-api` audience, `chat-service` client, `knowledge:retrieve`; no BFF route |

Retrieval pins PUBLIC corpus membership, READY/active state and
`available_at <= as_of` **in SQL before ranking**. Vietnamese Unicode/diacritics are
normalized for PostgreSQL `simple` full text. A small fixed question-phrase filter
handles queries such as “EW là gì?”. In `knowledge-retrieval-v2`, an empty
full-text result can fall back to exact topic phrases from the approved corpus.
The topic map recognizes bounded Vietnamese paraphrases, abbreviations and
English labels. A query without a known topic gets no fallback. Both passes use
the same eligibility filters. Chat accepts v1 and v2 evidence so existing
checkpoints remain readable. This change requires no corpus reindex or migration.
A read-only REPEATABLE READ transaction pins ranking and passage loading to one database snapshot. Exact cosine uses pinned 1536-dimensional `text-embedding-3-small` vectors,
threshold 0.45; each branch has at most 20 candidates, RRF k=60, stable chunk-ID
ties, top 5, <=8000 UTF-8 bytes of passage context. No ANN indexes or reranker. Optional provider calls are skipped when insufficient turn time remains for the final corpus and owner authorization checks.
Internal HTTP deadline is 3s; statement timeout 2.5s. `Server-Timing` reports
retrieval time separately from provider and client transport.

Chat pins retrieval once per job, rechecks active corpus before publication and
stores selected/retrieved IDs, minimal excerpts, source metadata, versions, query
hash, reason and `evidence_hash` separately from facts. A provider can select at
most three candidate IDs; it cannot supply prose, URLs, financial numbers or tool
arguments. A combined `fact-claims-v2` plan shares the existing single explanation
reservation. Without provider/consent, excerpts are labelled **references**; no
evidence produces an explicit missing-source response. Stored history remains
readable after corpus changes and supports old messages without Knowledge fields.

Consent v1 retains the previous LLM permission. Query embedding requires explicit
consent v2; existing records are never silently upgraded. Turning consent off
blocks both outbound paths. Indexing sends reviewed PUBLIC text only; query
embedding receives a redacted question, not profile, weights, IDs or history.
Redaction is bounded defense, not a guarantee that arbitrary free text has no PII.

## Eval, browser and persistence

The frozen dataset is `tests/fixtures/knowledge/eval-vi-v1.jsonl`, with its SHA-256
sidecar: 60 cases, 20 dev + 40 held-out; 24 answerable, 24 safety/abstention and 12
canonical/multi-turn cases. Do not edit cases or thresholds to improve a score.

```sh
.venv-software/bin/python scripts/eval_knowledge.py --mode offline --output output/knowledge-rag/eval-offline.json
.venv-software/bin/python scripts/eval_knowledge.py --mode lexical --split dev --output output/knowledge-rag/eval-lexical-dev.json
.venv-software/bin/python scripts/eval_knowledge.py --mode lexical --split heldout --output output/knowledge-rag/eval-lexical-heldout.json
E2E_DISPOSABLE_STACK=1 npm --prefix apps/web run test:browser:knowledge
```

Offline mode evaluates deterministic intent, not live dialogue quality. Lexical
mode measures the real owner API and reports applicable denominators; security,
conversation state and canonical cases that retrieval alone cannot certify are
marked not run there. Separate unit and live authorization/lifecycle gates must
not be presented as a completed 60-case live conversation eval. Human review of
all answerable held-out support/relevance is still a release requirement. Paid
hybrid eval and full conversation eval are separate outstanding gates.

### Query rewrite experiment

The default Chat worker has no rewriter. An in-process test adapter can propose
one short search query after a lexical miss on a Knowledge turn. A supported
follow-up form such as “Vậy nó …?” can use a single topic from the most recent
assistant Knowledge card in the same owned conversation. Ambiguous references
skip rewriting. The adapter gets the redacted question and that title, and
owns a one-second deadline. Chat repeats the lexical lookup within the original
corpus and cutoff, rechecks authorization, and stores only the rewrite hash
alongside the evidence when the retry succeeds.

Run the paired eval on an idle, dedicated local stack after building and
starting the current Chat image. The runner temporarily stops the regular Chat
worker and restores it in a finally block. It creates isolated conversations
through the normal Chat API, runs real workers against PostgreSQL, Auth,
Portfolio and Knowledge, and substitutes only the text rewrite adapter.

```sh
.venv-software/bin/python scripts/eval_knowledge_rewrite.py
.venv-software/bin/python scripts/eval_knowledge_rewrite.py --verify-report
```

The report compares Hit@5 from the final retrieval candidates with a separate
hit rate from citations in the saved Chat message. The two arms use the same
10 Vietnamese cases and corpus. The fixture supplies rewrites, so this measures
the effect of those queries and verifies integration. It does not measure
model quality. The eval starts no paid provider and adds no new provider config.

After recording successful receipts, restart the actual local application
processes, then verify **the same** receipts (do not regenerate flows):

```sh
docker compose --env-file infra/local/.generated/.env -f infra/local/compose.yaml -f infra/local/compose.tracing.yaml restart chat-api chat-worker knowledge-api knowledge-worker web
.venv-software/bin/python scripts/smoke_chat.py --verify-receipt
.venv-software/bin/python scripts/smoke_knowledge.py --verify-receipt
.venv-software/bin/python scripts/smoke_chat_knowledge.py --verify-receipt
E2E_DISPOSABLE_STACK=1 npm --prefix apps/web run test:browser:knowledge:persistence
```

Receipts live in ignored `infra/local/.generated`; sanitized captures/reports in
ignored `output`. Do not enable raw Playwright auth traces, videos or storageState.
Legacy Chat receipts compare their original conversation fields; additive
consent-v1 schema expansion does not rewrite an old receipt or mask changed facts.

## Paid acceptance preparation — not authorized by this document

Dry run makes no HTTP/provider calls and defaults to budget zero:

```sh
.venv-software/bin/python scripts/accept_knowledge_paid.py --dry-run
.venv-software/bin/python scripts/accept_knowledge_paid.py --dry-run --budget-usd 1
```

The latter is an estimate, **not permission**. Reviewed prices on 7 November 2026:
[text-embedding-3-small](https://developers.openai.com/api/docs/models/text-embedding-3-small)
$0.02/M input tokens; [gpt-6-luna standard](https://developers.openai.com/api/docs/pricing)
$0.10/M input and $0.50/M output. Reservations conservatively use $0.125/M input
for possible cache-write premium. Bounds: 100 embedding requests at <=8000 input
tokens and 20 dialogue requests at <=12000 input +384 output, at most $0.050 in
reserved upper bounds and always within the separately granted total cap. Actual
usage/estimate is not an invoice. Unknown/crashed outbound outcomes retain their
reservation and are never automatically paid-retried.

Only after a new explicit user grant: prepare the ignored
`infra/local/knowledge-openai.env` from its example, set a new
`KNOWLEDGE_PAID_APPROVAL` identifier and `KNOWLEDGE_BUDGET_USD` to the granted cap,
review the official price sheet, then apply `compose.knowledge-paid.yaml` to the
**two workers only**. The cap is partitioned 20% ingestion / 20% query / 60%
dialogue, with <=50 ingestion +50 query embeddings and <=20 dialogue reservations.
Both counters and all uncertain reservations persist across restarts.

Indexing an embedding-enabled revision must use a **new document version**
(`knowledge_operator.py index --version 2` with an explicit stable timezone-aware `--available-at` value recorded before the first POST), inspect its READY status and explicitly
activate it before hybrid acceptance. Existing lexical document versions are not
silently rewritten. The paid runner requires `--execute`, the specific positive
`--budget-usd` and new `--approval-id`, matching environment configuration and
`KNOWLEDGE_PRICE_REVIEWED=2026-11-07`; it runs 10 representative real Chat cases,
checkpoints conversation creation state, stable case keys and accepted job IDs **before** subsequent work, saves each outcome/assessment/usage, and has `--verify-receipt` for the same cases after restart. Partial runs resume those exact keys/jobs; uncertain conversation creation stops for owner-API reconciliation. The runner verifies both workers’ actual budget configuration, a fully embedded active corpus, real query/selection usage, expected intent, allowed claims, references and abstention; transport-only HYBRID is insufficient. It preserves failed assessments and does not silently replace failed or expired jobs. A representative smoke pass still does not certify the full release eval.
Do not run it until the grant exists. Recheck prices at execution time; this
pinned review does not authorize future prices or change recharge settings.

After the grant and worker-only key setup, the executable acceptance commands use
the exact approved environment values (empty/mismatched values fail closed):

```sh
docker compose --env-file infra/local/.generated/.env -f infra/local/compose.yaml -f infra/local/compose.knowledge-paid.yaml up -d --no-deps chat-worker knowledge-worker
.venv-software/bin/python scripts/accept_knowledge_paid.py --execute --budget-usd "$KNOWLEDGE_BUDGET_USD" --approval-id "$KNOWLEDGE_PAID_APPROVAL"
# After a real process restart, verify the same paid receipt without a new provider call:
.venv-software/bin/python scripts/accept_knowledge_paid.py --execute --verify-receipt --budget-usd "$KNOWLEDGE_BUDGET_USD" --approval-id "$KNOWLEDGE_PAID_APPROVAL"
.venv-software/bin/python scripts/knowledge_usage.py --approval-id "$KNOWLEDGE_PAID_APPROVAL"
```

Prepare/activate the embedding-enabled revision first as described above; the
runner refuses a lexical-only or partially embedded active corpus. Capture and
retain the explicit document availability timestamp before the first versioned
index POST so the exact CLI payload can be replayed after a lost response.


`knowledge_usage.py` reads only aggregate invocation metadata, with optional
`--since`/`--approval-id`, separating uncertain reservations and actual reported
tokens/estimates. It never sends a provider request or returns vectors/query/key.

## Deliberate exclusions

No PDF/OCR/crawler/malware pipeline, private/tenant corpus, deletion automation,
admin UI, historical research RAG, free-prose agent, new investment algorithm,
production HA/load certification or automated checklist/Google Sheet updates.


## Verification incident retained as evidence

The initial Knowledge canonical browser case accepted the API baseline fixture's
proposal, increasing that portfolio's version from 1 to 2. The old strict
`smoke_chat.py --verify-receipt` summary hash consequently fails. Its receipt was
not rewritten: canonical facts/input hash, original message history and
conversation still match. The original Chat browser and Knowledge receipts passed
after restart. The corrected canonical harness creates/accepts a separate
portfolio, asserts that the API fixture stays unchanged, and writes a separate
receipt. This does not retroactively turn the old strict API failure into a pass.
Historical Market–Quant parity and P1 availability checks can also fail when their
old serving inputs have expired; preserve those failures rather than altering
stored expiry or generating replacement flows.

### Contextual OpenAI replies

The optional Chat dialogue overlay supports CHAT_CONTEXTUAL_REPLIES=1.
Set a fresh KNOWLEDGE_PAID_APPROVAL and KNOWLEDGE_BUDGET_USD for the authorized
test budget. Keep these settings in an ignored operator env file and pass it as
an additional Compose --env-file. The private API key remains in the existing
.generated/chat-openai.env, read only by Chat worker. Use -p portfolio-auth-demo
for the currently running demo and apply compose.chat-llm.yaml with the base
Compose file. Retain any other overlays already used by that project.

The model writes conversational introductions and clarification questions after
backend state resolution. Financial numbers remain in canonical cards, and
knowledge excerpts retain their original source/version/hash. Generated replies
are checked for bounds, URLs, common PII, numbers and action-completion claims.
These checks do not prove all natural-language statements semantically correct.

```sh
.venv-software/bin/python -m pytest -q tests/software/test_chat_contextual.py
.venv-software/bin/python scripts/eval_chat_contextual.py
# Run only with the user's specific approval and matching worker budget.
.venv-software/bin/python scripts/eval_chat_contextual.py --run --approval-id APPROVAL_ID --budget-usd 0.50
# After restarting the same Chat API/worker, verify the saved resources.
.venv-software/bin/python scripts/eval_chat_contextual.py --verify-receipt
```

Dry-run performs no HTTP/provider call. The default live report is ignored under
output/knowledge-rag. The 10-case contextual fixture is separate from the frozen
retrieval eval. Report real-model behavior and offline injected-adapter results
with their applicable denominators.

The approved 18/11/2026 run uses the ignored .generated/chat-contextual.env.
For this demo the invocation cap is 20 text calls per approval and the global
daily limit was set to 40 to accommodate the targeted regression run. Keep the
new approval env file when recreating the worker, otherwise the base Compose
file alone disables the optional provider. Example for the current setup:

```sh
docker compose -p portfolio-auth-demo --env-file infra/local/.generated/.env --env-file infra/local/.generated/chat-contextual.env -f infra/local/compose.yaml -f infra/local/compose.chat-llm.yaml up -d --no-deps chat-api chat-worker
```

The first real-model report has 10/12 passing turns. Targeted D01/D07 regression
has 2/2 passing on the final source. The two report files remain separate and
both verify the same saved messages after restart. No complete real-model rerun
on final source is claimed. In addition to schema checks, the final renderer
rejects proposed strategy questions which omit EW, MVO or ML. The 600-character
bound and a five-second response deadline keep the final reply within the turn
budget after interpretation and authorization.

### Recommendation follow-up regression

The backend resolves a prior recommendation from the same owned conversation
and current portfolio, with a cutoff at the current user message. This lookup is
independent of provider availability and the four-message text-context window.
Explicit recommendation IDs retain priority. Explanation responses carry the
additive explanation_requested flag so the explanation opens immediately.

CHAT_LLM_APPROVAL_CALL_LIMIT defaults to 20 and is clamped to 0–250. Invalid
values block new calls. The current authorized demo uses 250 per approval and 100
per day, with a USD 1.00 budget approved on 18/11/2026. The existing approval ID
and recorded usage are retained; billing settings are unchanged. Provider outages/exhaustion still permit canonical
read-only follow-up explanations.

```sh
.venv-software/bin/python scripts/smoke_chat_followup.py
# Requires the existing authorized provider budget and an owner-scoped result.
.venv-software/bin/python scripts/smoke_chat_followup.py --run
# After restarting Chat API/worker/Web, verify the SAME receipt.
.venv-software/bin/python scripts/smoke_chat_followup.py --verify-receipt
```

The run makes five turns in a new test conversation using an existing result.
It checks both screenshot questions after intervening messages, exact facts/hash,
no paid intent for deterministic follow-ups, and persisted messages/usage. It
refuses to overwrite an existing receipt. Unit cases also cover owner/portfolio
isolation, future-message cutoff and explicit-ID precedence. Full conversation-quality and investment-methodology evaluations remain outstanding.

Requested explanations also retrieve approved notes using the strategy pinned
in canonical facts. Selected source excerpts are included verbatim after the
final corpus/authorization recheck, with the same immutable evidence references.
These passages explain the method; per-asset causal attribution still requires
additional canonical diagnostics and is outside this regression.

### Vietnamese lexical candidate, 23 November 2026

The serving v1 manifest remains at `services/knowledge/corpus/manifest.json`. The independent candidate is `services/knowledge/corpus/candidate-20261123`, containing 13 documents and 30 finite claims. Its canonical payload hash is `83759093ce950cc5f2a781eddf91049d181408fbdd69016bc931562c57d3d094`. The application does not load that directory automatically. Unedited documents reuse their original immutable versions. Revised documents use version 20261123 and their actual authoring time. Older citations retain their original version, text and source hash.

| Question covered by a new or revised claim | Stable claim ID | Source |
| --- | --- | --- |
| Does equal weighting guarantee a profit or equal risk contributions? | ew-limit | MOSEK Cookbook §2.1, return and variance |
| Can the ML view predict the wrong direction? | ml-views-limit | Allocation explanation, raw forecasts and confidence |
| How do market returns and model views determine the inputs for portfolio optimization? | bl-method-ml | Numerical contract, posterior and allocator |
| From which date are the seven calendar days measured? | freshness-window | Selection panel, availability and project |
| When does a VFF NAV become eligible? | vff-nav-availability | Phase 1 serving runbook, pinned snapshot availability policy |
| What happens to saved targets when inputs expire? | freshness-history | Weeks 6–7, accepted target history |
| Who may review a model candidate? | model-approval-reviewer | ML Platform, human review and decision recording |
| What can an investor do during a pause? | proposal-pause-rule | Managed HYBRID release and historical access |
| What do the two benchmarks represent? | proposal-method-comparison | HYBRID method and read-only comparisons |

Each manifest claim supplies its source URL and locator. Project citations pin Git commits. Their files were checked in the local repository. On 23 November an anonymous GitHub request for the pinned Phase 1 source at ca0043b4 returned HTTP 404, while the older published revision returned HTTP 200. Before operator activation, make the pinned sources accessible to the intended readers and verify their links. For VFF, the five-session buffer applies to the baseline and selected v1. The live NAV v2 policy uses a verified ingestion time. Both enforce the seven-calendar-day age limit from the NAV date. An actual portfolio's status and current availability require a portfolio-scoped backend read.

`knowledge-retrieval-v3` adds Vietnamese fallback phrases, including “chia đều” and “views ML”. PUBLIC, active-corpus, cutoff, vector compatibility, score threshold, top five and byte limits retain their existing behavior. Standalone Chat knowledge replies quote the selected paragraphs verbatim after the final corpus and authorization check. Selection also requires the requested concepts to appear in a paragraph, with a small Vietnamese synonym vocabulary. Missing parts receive an explicit short answer about insufficient evidence. This deterministic check can miss paraphrases and cannot certify general semantic entailment. Operator and independent human review remain release gates.

Under the common synthetic cutoff `2026-11-23T16:00:00Z`, all three runs of the six answerable v2 development questions produced the following results. The unrelated development question returned zero passages in all nine attempts. For the eight v1 development definitions, all three arms found an allowed claim in the top five on all three runs. The staged reports include only IDs, ranks, times and settings.

| Development arm | Hit@5 | MRR@5 | Provider calls / cost |
| --- | --- | --- | --- |
| v1 corpus, v2 ranker | 2/6 | 0.333 | 0 / USD 0 |
| candidate corpus, v2 ranker | 3/6 | 0.500 | 0 / USD 0 |
| candidate corpus, v3 ranker | 6/6 | 0.750 | 0 / USD 0 |

Receipts are in `output/rag-status-20261123/p3-{baseline,content,lexical}.json`. First request and remaining requests were labelled separately. These are local HTTP results from disposable PostgreSQL and a synthetic internal identity. The full matrix includes matched machine/corpus latency and conversation measurements.

To reproduce the HTTP arms, run the following from the repository root. The database uses tmpfs and a random loopback port. Each API process opens only a retrieval route to the test identity. Existing database tables cause startup to fail before indexing. The commands require the local pgvector image and software virtualenv used by Compose.

```sh
(
  set -eu
  eval_tmp=$(mktemp -d)
  eval_pg=$(docker run --rm -d --pull=never --tmpfs /var/lib/postgresql/data \
    -e POSTGRES_HOST_AUTH_METHOD=trust -p 127.0.0.1::5432 portfolio-software-knowledge-postgres:pg17-vector081)
  eval_pids=""
  trap 'for pid in $eval_pids; do kill "$pid" 2>/dev/null || true; done; docker stop "$eval_pg" >/dev/null' EXIT
  until docker exec "$eval_pg" pg_isready -U postgres >/dev/null 2>&1; do sleep 1; done
  eval_port=$(docker port "$eval_pg" 5432/tcp | awk -F: '{print $NF}')
  git archive ca0043b4a95c8d1fae0a5ec0f373377d307e00fb services/knowledge/src | tar -x -C "$eval_tmp"
  for arm in baseline content candidate matched; do
    docker exec "$eval_pg" createdb -U postgres "rag_eval_$arm"
    case "$arm" in
      baseline) port=18967; corpus=services/knowledge/corpus; src="$eval_tmp/services/knowledge/src" ;;
      content) port=18965; corpus=services/knowledge/corpus/candidate-20261123; src="$eval_tmp/services/knowledge/src" ;;
      candidate) port=18966; corpus=services/knowledge/corpus/candidate-20261123; src=services/knowledge/src ;;
      matched) port=18968; corpus=services/knowledge/corpus; src=services/knowledge/src ;;
    esac
    PYTHONPATH="$src" .venv-software/bin/python scripts/serve_knowledge_eval.py \
      --postgres-port "$eval_port" --database "rag_eval_$arm" --port "$port" --corpus "$corpus" &
    eval_pids="$eval_pids $!"
  done
  until curl -fsS http://127.0.0.1:18966/health/ready >/dev/null 2>&1; do sleep 1; done
  KNOWLEDGE_EVAL_PORT=18966 .venv-software/bin/python -m pytest -q tests/software/test_knowledge_postgres.py -k candidate
  # Run the v2 evaluation commands against these loopback endpoints while this shell waits.
  wait
)
```

The internal test bearer is `p3-local-read`. Each HTTP arm serves `/internal/v1/knowledge/retrieve`. Stop the shell after collecting receipts. For an approved rollout, validate the candidate directory, index it through the existing operator CLI with an idempotency key, inspect READY, then activate using the lifecycle version. Use the same lifecycle operation with the prior corpus ID for rollback. Preserve the previous activation receipt by passing a new `--receipt` path each time.

The final selector was also compared with its initial implementation using only the previously examined v1 questions, before the final v2 rerun. With identical candidate passages the initial selector selected an allowed claim on 21/24 answerable cases and abstained on 3/3 unrelated questions. A17, A18 and A22 found suitable paragraphs but the selector missed the freshness, model approval and input-dependence phrasing. The revised vocabulary and definition preference select an allowed paragraph on 24/24, and abstain on 3/3. Explicit definition questions prefer a definition among supporting passages, including when insertion-generated UUIDs break a lexical tie. This was checked on two independently indexed candidate databases. The initial selector source and the row-level receipts are in `output/rag-status-20261123/candidate-a-knowledge.py` and `v1-selection-{a,b}.json`. The v1 tests are development regressions.

Retrieval loads the final ranked IDs in one bound SQL metadata query inside the existing repeatable-read snapshot. The service reapplies visibility, active version and availability constraints and emits paragraphs in fused rank order within the byte budget. The isolated PostgreSQL test counts one metadata query for three passages. Run the full PostgreSQL probe using the disposable database while the eval arms are running.

```sh
KNOWLEDGE_EVAL_PORT=18966 KNOWLEDGE_POSTGRES_TEST=1 \
  KNOWLEDGE_POSTGRES_TEST_URL="postgresql+psycopg://postgres@127.0.0.1:$eval_port/rag_eval_candidate" \
  .venv-software/bin/python -m pytest -q tests/software/test_knowledge_postgres.py
```

An additional regression probe alternated the two SQL implementations for every v1 development question on the **same active v1 corpus and chunk IDs**. It recorded 30 requests per arm over three rounds after warm-up, including the two empty-result queries. All ordered ID lists matched. Local HTTP p50/p95 were 59.8/191.1 ms before and 44.0/163.2 ms after batching. The service's p95 was 145.6/106.1 ms respectively. These wall-clock measurements apply to this local run and its load. See `output/rag-status-20261123/p3-v1-dev-matched.json` for request-level timings. The v2 locked comparison uses its own receipts.
