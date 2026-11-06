# Chat LLM implementation — 05/11/2026

User selected proposal B: LLM understands conversation, backend orchestrates. Execute
in the current checkout, preserve the previous Chat MVP and unrelated work. Use
writing-plans, inline execution and TDD. No commit/push or billing changes.

## Design and decisions

Alternatives considered: explanation-only adapter (A), hosted structured dialogue
(B, selected), local model deployment (C). Add OpenAI Responses using existing
httpx, no agent framework, autonomous tools, RAG or model training. Initial model
`gpt-6-luna`, reasoning none: official current model page supports Responses and
Structured Outputs, $0.10/M input and $0.50/M output. Record returned model plus
prompt/schema versions; no dated snapshot is advertised. Older GPT-4.1 mini is
deprecated, so do not introduce it. References:
https://developers.openai.com/api/docs/models/gpt-6-luna
https://developers.openai.com/api/docs/guides/structured-outputs

Backend accepts structured intent/strategy/reference selections only. Model output
cannot supply resource IDs, grants, versions, numerical claims, confirmations or
mutation authority. Server builds confirmation cards from canonical Portfolio,
and retains the existing explicit accept UI. Explanation is a model-selected
fact plan rendered with verified backend values; unverified prose is rejected.
Context is bounded, redacted and owner/conversation scoped. New per-conversation
consent defaults off; revocation is checked before any outbound model call.

Cost controls: explicit UI intents/confirmations bypass interpretation. At most
one intent and one explanation invocation per job, durably reserved before I/O;
no paid retry after timeout/crash. Global UTC-day cap initially 20 calls, with
SQL serialization across workers. Response max 384 output tokens, input envelope
at most 12000 bytes, 8-second wall deadline per call. Daily cap counts failures
and uncertain in-flight reservations. Persist validated output for restart reuse
and actual API usage; no prompts/tokens/keys in logs or SSE. No cross-user cache.
Use store=false, no hosted tools or provider-managed conversation storage.
Secret in ignored .generated/chat-openai.env, worker-only optional Compose overlay.
Do not enable Auto Recharge. Live acceptance at most 6 calls, after offline suite;
report actual usage, not fabricated estimates. Missing key blocks only live checks.

## Tasks and verification

- [x] 1. Add tests for Responses request/response boundaries, refusal/quota/timeout,
  unknown tools/IDs/prose, redaction and actual usage. Observe RED; implement
  openai_provider.py and preserve the legacy adapter/template behavior; GREEN.
- [x] 2. Add consent + durable provider-invocation schema/migration. Tests pin
  lease fencing, per-purpose dedupe, daily cap including concurrency, crash and
  replay. Add consent API and bounded context resolution. No allocation before
  structured confirmation even if the model says otherwise. RED → GREEN.
- [x] 3. Wire worker routing/clarification/follow-up/explanation and UI consent,
  auto strategy and provider provenance. Add cross-user/consent-revocation and
  contextual strategy/recommendation tests. Preserve idempotency/session behavior.
- [x] 4. Add worker-only Compose overlay/example, budget inspection and opt-in
  cheap real-provider gate. Run complete Python/web/typecheck/Ruff/contracts,
  real migration/health and browser flow. Use no HTTP interception for live evidence.
- [x] 5. Review final changes, fix defects, document setup, measured live costs,
  fallback/restart evidence and limitations. Keep artifacts/credentials outside Git.

Review focus: model-supplied confirmation bypass; resource-ID injection; delayed
consent revocation; duplicate paid calls after crash; quota races; current request
mistaken for stale context; missing strategy silently becoming MVO; unverified
numeric/causal claims; output usage lost after error; secrets escaping Compose/UI.

## Execution ledger

Initial inspection: no OPENAI_API_KEY or CHAT_PROVIDER_KEY configured. Asked user to
save a key locally; continue offline work. Previous complete Chat changes and
extensions_C_v1 remain in place. User's execution request authorizes implementation
of the selected B proposal without another design/plan approval round.

Final evidence: 539 Python/core passed, 1 unrelated opt-in skip; 104 web tests,
TypeScript, Ruff, 11 contracts and production builds passed. Real migration
metadata check and DB/broker/Identity boundaries passed. Three PostgreSQL Chat
concurrency probes passed, including the new global paid-call reservation cap.

Paid browser reached explicit accept: 5 verified OpenAI Responses calls, 1786
input and 196 output tokens, conservative estimate $0.00032125. Reporting initially
missed intent usage inside a follow-up explanation; fixed with job-ledger usage
and RED→GREEN regression, then verified exact persisted resources/requests after
restart without repeating paid calls. Real cap exhaustion and connection-refused
HTTPS proxy fault both produced canonical TEMPLATE; 6 reservations total, 5 paid
responses. Proxy removed, normal daily quota restored to 20. API/BFF have no key;
recent application log scan found no configured secrets or bearer strings.

Independent review found BL + ML spelling rejection; regression RED→GREEN fixed.
Additional self-review added current owner-grant/account preflight before paid
interpretation; revoked grants now prevent any invocation reservation. Full paid
lifecycle was not repeated after these fixes to preserve credits; unit/storage
gates and original-receipt browser verification cover the final changes.

Final grounding check: explanation planner also receives the redacted current
question; a schema/transport regression verifies question focus without exposing
email/keys. No additional paid call was made for this final change.
