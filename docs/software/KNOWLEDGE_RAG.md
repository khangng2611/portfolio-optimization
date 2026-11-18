# Knowledge/RAG local MVP

Knowledge is an owner service, not an investment engine. Chat renders only approved
claim text or canonical Portfolio facts. It never creates allocations from a
knowledge question and cannot accept targets, trade or promote models. Numerical
facts, `facts_hash`, confirmations and acceptance keep their original contracts.

This implementation supports a reviewed PUBLIC Markdown corpus and lexical
retrieval. Semantic/provider acceptance is **not run** without a new specific
budget. Lexical-only results do not certify semantic RAG. Release eval thresholds
remain binding; the first held-out run did not meet intent or Hit@5 thresholds.
See the dated implementation status for measured results and outstanding gates.

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

CHAT_LLM_APPROVAL_CALL_LIMIT defaults to 20 and is clamped to 0–100. Invalid
values block new calls. The current authorized demo uses 100 per approval and 100
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
