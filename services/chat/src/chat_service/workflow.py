from datetime import timedelta
import re
import unicodedata
import hashlib
import time
from uuid import uuid4
import httpx
from sqlalchemy import delete
from portfolio_contracts import aware, canonical_hash, system_hybrid_enabled, system_hybrid_managed, utcnow
from .models import ToolCall, Event
from .provider import Provider, render
from .queue import Queue
from .tools import ALLOCATION_INPUT_ERRORS, ToolError
from .llm import Dialogue
from .knowledge import (
    Retrieval,
    previous_knowledge_topic,
    render_evidence,
    save_checkpoint,
)
from .openai_provider import redact


BLOCKED_INTENT = re.compile(
    r"bo qua .*huong dan|ignore .*instructions|system prompt|api key|bearer |tu .*chap nhan|tu .*promote"
)


def normalize_intent(text):
    return "".join(
        c
        for c in unicodedata.normalize("NFKD", text.casefold().replace("đ", "d"))
        if not unicodedata.combining(c)
    )


def is_knowledge_followup(text):
    text = normalize_intent(text).strip()
    return text.endswith("?") and re.match(
        r"(?:(?:vay|the|con)\s+)?(?:no|cai nay|cai do|phuong phap nay|phuong phap do|cach nay|cach do)\b",
        text,
    )


def is_evidence_followup(text):
    value = normalize_intent(text)
    if BLOCKED_INTENT.search(value) or re.search(r"(?:tao|tinh|hay) (?:de xuat|phan bo)|lap phuong an|toi uu|chay (?:ew|mvo|bl)", value):
        return False
    linked = bool(re.search(r"de xuat|phan bo|ty trong|cua ro|anh huong|lien quan",value))
    if "thi truong" in value and (not linked or re.search(r"hom nay|hien tai|moi nhat", value)):
        return False
    if "ho so" in value and not linked:
        return False
    if re.search(r"la gi|nghia la|khai niem",value) and not linked:
        from portfolio_contracts.assets import EQUITY_IDS
        if not any(re.search(r"\b"+a.lower()+r"\b",value) for a in EQUITY_IDS):
            return False
    if "rui ro" in value and "ho so" not in value:
        return True
    return bool(re.search(r"\b(?:views?|du bao|tin hieu|rsi|macd|momentum|dac trung|xu huong|bien dong|drawdown|k5)\b", value) or ("ho so" in value and re.search(r"anh huong|lien quan|phan bo|de xuat", value)))


def intent_of(request):
    if request.get("confirmation"):
        return "allocation"
    if request.get("intent"):
        return request["intent"]
    text = request["content"].casefold()
    normalized = normalize_intent(text)
    if BLOCKED_INTENT.search(normalized):
        return "help"
    if re.search(
        r"la gi|nghia la|kien thuc|khai niem|da dang hoa|hiep phuong sai|covariance|black.?litterman|backtest|turnover",
        normalized,
    ) or (
        re.search(r"\b(ew|mvo|bl_ml)\b", normalized)
        and re.search(r"giai thich|tai sao|nhuoc diem|uu diem", normalized)
    ):
        return "knowledge"
    if (
        "giai thich" in normalized
        or "explain" in normalized
        or normalized.strip(" ?!.")
        in {"de xuat nao", "de xuat nao vay", "ban dang noi de xuat nao"}
        or (
            re.search(r"\b(vi sao|tai sao)\b", normalized)
            and re.search(r"phan bo|ty trong|quyet dinh|de xuat", normalized)
        )
    ):
        return "explain"
    if any(
        s in normalized
        for s in (
            "phan bo",
            "allocation",
            "toi uu",
            "tao de xuat",
            "lap phuong an dau tu",
        )
    ):
        return "allocation"
    if any(s in text for s in ("thị trường", "market")):
        return "market"
    if "hồ sơ" in text:
        return "profile"
    if "danh mục" in text:
        return "portfolio"
    return "help"


class Worker:
    def __init__(
        self, sessions, tools, provider=None, clock=utcnow, *, query_rewriter=None
    ):
        self.sessions, self.tools, self.clock = sessions, tools, clock
        self.q, self.provider = Queue(sessions), provider or Provider()
        self.dialogue = Dialogue(sessions)
        # In-process experiment only. The adapter owns its one-second deadline.
        self.query_rewriter = query_rewriter
        self.started, self.tool_count = time.monotonic(), 0

    def has_time(self, seconds, *, reserve=7):
        # Reserve the final 3s corpus recheck and 4s owner authorization read.
        return 20 - (time.monotonic() - self.started) >= seconds + reserve

    def call(self, job, name, args):
        if time.monotonic() - self.started > 20 or self.tool_count >= 7:
            raise ToolError("TOOL_BUDGET_EXCEEDED", permanent=True)
        self.tool_count += 1
        try:
            result = self.tools.call(job, name, args)
        except (httpx.HTTPError, ToolError):
            with self.sessions.begin() as s:
                s.add(
                    ToolCall(
                        job_id=job.id,
                        tool=name,
                        arguments_hash=canonical_hash(args),
                        status="FAILED",
                    )
                )
            raise
        with self.sessions.begin() as s:
            s.add(
                ToolCall(
                    job_id=job.id,
                    tool=name,
                    arguments_hash=canonical_hash(args),
                    result_hash=canonical_hash(result),
                    result_reference=result.get("id") or result.get("job_id"),
                    status="SUCCEEDED",
                )
            )
        return result

    def reply(
        self,
        job,
        text,
        structured,
        *,
        status="SUCCEEDED",
        events=(),
        stage="COMPLETE",
        error=None,
    ):
        mid = str(uuid4())
        if (
            self.dialogue.contextual
            and self.query_rewriter is None
            and not (system_hybrid_managed() and structured.get("type") in {"help", "input_required"})
            and structured.get("type")
            in {"help", "input_required", "knowledge", "profile", "portfolio", "market"}
            and self.has_time(9, reserve=1)
        ):
            # Authorization is refreshed before even a conversational model call.
            self.call(job, "get_profile", {})
            generated, response_meta = self.dialogue.respond(job, structured)
            structured["response"] = response_meta
            if generated and (
                structured.get("fields") != ["strategy"]
                or all(label in generated for label in ("EW", "MVO", "ML"))
            ):
                text = generated
        if getattr(self, "dialogue_metadata", None):
            structured["dialogue"] = self.dialogue_metadata
        if structured.get("type") == "confirmation":
            structured["confirmation_message_id"] = mid
        ending = (
            "input_required" if status == "WAITING_INPUT" else "completed",
            {"message_id": mid, "status": status},
        )
        return self.q.finish(
            job,
            status=status,
            stage=stage,
            error=error,
            message={"id": mid, "content": text, "structured": structured},
            events=[*events, ending],
            now=self.clock(),
        )

    def confirmation(self, job, p, strategy, reason="CONFIRM_INPUT"):
        inputs = {"portfolio": p, "strategy": strategy}
        return self.reply(
            job,
            "Vui lòng kiểm tra danh mục, hồ sơ rủi ro và ràng buộc trước khi tạo đề xuất."
            if strategy == "HYBRID" else
            "Vui lòng kiểm tra danh mục, hồ sơ rủi ro, chiến lược và ràng buộc trước khi tạo đề xuất.",
            {
                "type": "confirmation",
                "reason": reason,
                "input": inputs,
                "facts_hash": canonical_hash(inputs),
            },
            status="WAITING_INPUT",
            stage="CONFIRMATION",
        )

    def tick(self):
        job = self.q.claim(now=self.clock())
        if not job:
            return False
        self.started, self.tool_count = time.monotonic(), 0
        self.dialogue_metadata = None
        try:
            if aware(job.deadline) <= self.clock():
                return self.q.finish(
                    job,
                    status="FAILED",
                    error="DEADLINE_EXCEEDED",
                    events=[("failed", {"code": "DEADLINE_EXCEEDED"})],
                    now=self.clock(),
                )
            if aware(job.grant_expires_at) <= self.clock():
                raise ToolError("AUTHORIZATION_REQUIRED", permanent=True)
            if job.attempts >= job.max_attempts:
                raise ToolError("RETRY_EXHAUSTED", permanent=True)
            r = job.request
            if job.stage == "WAIT_ALLOCATION":
                status = self.call(
                    job, "get_allocation_job", {"resource_id": job.dependency_id}
                )
                if status["status"] in ("QUEUED", "RUNNING", "RETRY"):
                    return self.q.finish(
                        job,
                        status="WAITING_DEPENDENCY",
                        stage="WAIT_ALLOCATION",
                        delay=1,
                        now=self.clock(),
                    )
                if status["status"] != "SUCCEEDED" or not status.get(
                    "recommendation_id"
                ):
                    code = (status.get("error") or {}).get("code")
                    raise ToolError(code if code in ALLOCATION_INPUT_ERRORS else "ALLOCATION_FAILED", permanent=True)
                facts = self.call(
                    job,
                    "get_recommendation",
                    {"resource_id": status["recommendation_id"]},
                )
                return self.explain(job, facts)
            if job.stage == "SUBMIT":
                pin = r["confirmed_input"]
                result = self.call(
                    job,
                    "request_allocation",
                    {
                        "portfolio_id": pin["portfolio"]["id"],
                        **({"strategy": pin["strategy"]} if pin["strategy"] != "HYBRID" else {}),
                        "expected_version": pin["portfolio"]["version"],
                        "expected_policy_version": pin["portfolio"][
                            "policy_version_id"
                        ],
                    },
                )
                return self.q.finish(
                    job,
                    status="WAITING_DEPENDENCY",
                    stage="WAIT_ALLOCATION",
                    dependency_id=result["job_id"],
                    events=[
                        (
                            "stage_changed",
                            {
                                "stage": "WAIT_ALLOCATION",
                                "allocation_job_id": result["job_id"],
                            },
                        )
                    ],
                    now=self.clock(),
                )
            deterministic = intent_of(r)
            if (not r.get("intent") and not r.get("confirmation")
                and is_evidence_followup(r["content"])
                and (r.get("recommendation_id") or self.dialogue.recommendation_reference(job))):
                deterministic = "explain"
            if deterministic == "explain" and not r.get("confirmation"):
                r = r | {"intent": "explain"}
            topic = None
            if (
                self.query_rewriter is not None
                and (
                    deterministic == "knowledge"
                    or (deterministic == "help" and not r.get("intent"))
                )
                and is_knowledge_followup(r["content"])
                and not BLOCKED_INTENT.search(normalize_intent(r["content"]))
            ):
                topic = previous_knowledge_topic(self.sessions, job)
            profile = None
            if (
                self.dialogue.enabled
                and not r.get("intent")
                and not r.get("confirmation")
                and self.dialogue.context(job)[0] is not None
            ):
                # Validate current account/role/grant at its owner before sending
                # even bounded prior conversation context to an external model.
                profile = self.call(job, "get_profile", {})
            if deterministic == "knowledge" or topic:
                r = r | {"intent": "knowledge"}
            elif deterministic != "explain":
                r, self.dialogue_metadata = self.dialogue.interpret(job)
            intent = intent_of(r)
            if intent == "knowledge":
                if profile is None:
                    self.call(job, "get_profile", {})
                evidence = self.knowledge(job, previous_topic=topic)
                return self.reply(
                    job,
                    "Các đoạn tham khảo từ corpus đã duyệt."
                    if evidence["citations"]
                    else "Chưa có nguồn phù hợp trong corpus để trả lời câu hỏi này.",
                    {"type": "knowledge", "knowledge": evidence},
                )
            if intent in ("help", "clarify", "unsupported"):
                return self.reply(
                    job,
                    "Bạn muốn xem hồ sơ, tóm tắt danh mục, dữ liệu thị trường, tạo đề xuất hay giải thích đề xuất? Tôi không tự chấp nhận target, giao dịch hoặc thay ràng buộc.",
                    {"type": "help"},
                )
            if intent == "market":
                facts = self.call(job, "get_market_facts", {})
                return self.reply(
                    job,
                    "Facts thị trường do Market Service cung cấp, kèm nguồn và thời điểm trong thẻ dữ liệu.",
                    {
                        "type": "market",
                        "facts": facts,
                        "facts_hash": canonical_hash(facts),
                    },
                )
            if not r.get("portfolio_id"):
                return self.reply(
                    job,
                    "Chọn danh mục trước khi tiếp tục. Bạn có thể tạo danh mục và xác nhận hồ sơ trong mục Danh mục.",
                    {"type": "input_required", "fields": ["portfolio_id"]},
                    status="WAITING_INPUT",
                    stage="COLLECT",
                )
            if profile is None:
                profile = self.call(job, "get_profile", {})
            p = self.call(
                job, "get_portfolio_summary", {"portfolio_id": r["portfolio_id"]}
            )
            if intent == "profile":
                return self.reply(
                    job,
                    "Hồ sơ đã xác nhận từ Portfolio Service.",
                    {
                        "type": "profile",
                        "facts": profile,
                        "facts_hash": canonical_hash(profile),
                    },
                )
            if intent == "portfolio":
                return self.reply(
                    job,
                    "Tóm tắt danh mục từ Portfolio Service.",
                    {"type": "portfolio", "facts": p, "facts_hash": canonical_hash(p)},
                )
            if intent == "explain":
                r = r | {
                    "recommendation_id": r.get("recommendation_id")
                    or self.dialogue.recommendation_reference(job),
                }
                if not r.get("recommendation_id"):
                    return self.reply(
                        job,
                        "Mình chưa tìm thấy đề xuất của danh mục đang chọn trong cuộc trao đổi này. Bạn muốn mở một đề xuất đã có hay chuẩn bị đề xuất mới?",
                        {"type": "input_required", "fields": ["recommendation_id"]},
                        status="WAITING_INPUT",
                        stage="COLLECT",
                    )
                return self.explain(
                    job,
                    self.call(
                        job,
                        "get_recommendation",
                        {"resource_id": r["recommendation_id"]},
                    ),
                    requested=True,
                )
            if system_hybrid_managed() and not system_hybrid_enabled():
                raise ToolError("INPUT_UNAVAILABLE", permanent=True)
            if not p.get("risk_profile") or not p["risk_profile"].get("version_id"):
                return self.reply(
                    job,
                    "Cần xác nhận hồ sơ rủi ro trước khi tạo đề xuất qua Chat.",
                    {
                        "type": "input_required",
                        "fields": ["confirmed_risk_profile"],
                        "portfolio_id": p["id"],
                    },
                    status="WAITING_INPUT",
                    stage="COLLECT",
                )
            if not system_hybrid_managed() and not r.get("strategy") and not r.get("confirmed_input"):
                return self.reply(
                    job,
                    "Chọn chiến lược EW, MVO hoặc BL_ML; hệ thống không tự chuyển chiến lược khi có lỗi.",
                    {"type": "input_required", "fields": ["strategy"]},
                    status="WAITING_INPUT",
                    stage="COLLECT",
                )
            if not r.get("confirmation"):
                return self.confirmation(job, p, "HYBRID" if system_hybrid_managed() else r["strategy"])
            pin = r["confirmed_input"]
            if system_hybrid_managed() and pin["strategy"] != "HYBRID":
                return self.confirmation(job, p, "HYBRID", "STALE_CONFIRMATION")
            if (
                canonical_hash({"portfolio": p, "strategy": pin["strategy"]})
                != r["confirmation"]["facts_hash"]
            ):
                return self.confirmation(job, p, pin["strategy"], "STALE_CONFIRMATION")
            # The dependency intent is committed before the HTTP mutation; stable job
            # identity is the downstream business key, including after a hard crash.
            return self.q.finish(
                job,
                status="QUEUED",
                stage="SUBMIT",
                events=[("stage_changed", {"stage": "TOOL_AUTHORIZED"})],
                now=self.clock(),
            )
        except ToolError as exc:
            attempts = job.attempts + 1
            status = (
                "AUTHORIZATION_REQUIRED"
                if exc.code == "AUTHORIZATION_REQUIRED"
                else "FAILED"
                if exc.permanent or attempts >= job.max_attempts
                else "RETRY"
            )
            return self.q.finish(
                job,
                status=status,
                error=exc.code,
                attempts=attempts,
                delay=min(16, 2**attempts),
                events=[
                    (
                        "input_required"
                        if status == "AUTHORIZATION_REQUIRED"
                        else "failed"
                        if status == "FAILED"
                        else "stage_changed",
                        {"code": exc.code, "status": status},
                    )
                ],
                now=self.clock(),
            )
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            attempts = job.attempts + 1
            final = attempts >= job.max_attempts
            return self.q.finish(
                job,
                status="FAILED" if final else "RETRY",
                error="DEPENDENCY_UNAVAILABLE",
                attempts=attempts,
                delay=min(16, 2**attempts),
                events=[
                    (
                        "failed" if final else "stage_changed",
                        {"code": "DEPENDENCY_UNAVAILABLE"},
                    )
                ],
                now=self.clock(),
            )

    def explain(self, job, facts, *, requested=False):
        digest = canonical_hash(facts)
        evidence, claims, selected_claim_ids = None, None, None
        from .explanation import build_claims, default_ids, render_claims, validate_plan

        try:
            candidate = self.call(job, "get_recommendation_evidence", {"resource_id": facts["id"]})
            claims = build_claims(facts, candidate)
            evidence = candidate
        except (ValueError, KeyError, TypeError, AttributeError, ToolError, httpx.HTTPError):
            # Older grants/services can still explain the canonical facts already read.
            # Final owner authorization below remains mandatory.
            pass
        knowledge = self.knowledge(
            job, select_claims=False, strategy=facts.get("strategy")
        )
        if not self.has_time(8):
            sections, metadata = None, {"reason": "TURN_BUDGET_EXHAUSTED"}
        elif evidence is not None:
            plan, metadata = self.dialogue.explain_claims(job, digest, evidence, claims)
            sections = None
            if plan:
                try:
                    selected_claim_ids = validate_plan(plan, facts, evidence, claims, job.request["content"])
                    sections = selected_claim_ids
                except ValueError:
                    metadata = metadata | {"reason": "UNVERIFIED_OUTPUT"}
        elif self.dialogue.enabled:
            sections, metadata = self.dialogue.explain(
                job, facts, digest, self.knowledge_data
            )
        elif self.q.reserve_provider(job, now=self.clock()):
            sections, metadata = self.provider.explain(facts, digest)
        else:
            sections, metadata = None, {"reason": "PROVIDER_BUDGET_EXHAUSTED"}
        if evidence is not None:
            selected_claim_ids = selected_claim_ids or default_ids(claims, job.request["content"])
            text = render_claims(claims, selected_claim_ids)
            metadata = metadata | {"schema_version": "explanation-claims-v1", "prompt_version": "allocation-explanation-v1"}
        else:
            text = render(facts, sections)
        if metadata.get("knowledge_plan"):
            knowledge = render_evidence(
                self.knowledge_data,
                metadata["knowledge_plan"],
                query_hash=knowledge["query_hash"],
                metadata={k: v for k, v in metadata.items() if k != "knowledge_plan"},
            )
        knowledge = self.validate_knowledge(job, knowledge)
        if requested:
            method = "\n\n".join(p["text"] for p in knowledge["citations"])
            text = "\n\n".join(
                part
                for part in (
                    "Mình đang giải thích đề xuất này dựa trên kết quả định lượng và hồ sơ đã xác nhận.",
                    method,
                    text,
                )
                if part
            )
        rid = facts["id"]
        mid = str(uuid4())
        return self.q.finish(
            job,
            status="SUCCEEDED",
            stage="COMPLETE",
            recommendation_id=rid,
            message={
                "id": mid,
                "content": text,
                "structured": {
                    "type": "recommendation",
                    "recommendation_id": rid,
                    "facts": facts,
                    "facts_hash": digest,
                    **({"explanation_evidence": evidence, "selected_claim_ids": selected_claim_ids,
                        "explanation_claims": [c.model_dump(mode="json") for c in claims],
                        "renderer_version": "allocation-explanation-v1"} if evidence is not None else {}),
                    "knowledge": knowledge,
                    "explanation_status": "VERIFIED" if sections else "TEMPLATE",
                    "explanation_requested": requested,
                    "provider": metadata,
                    "schema_version": metadata.get("schema_version", "fact-plan-v1"),
                    "prompt_version": metadata.get("prompt_version", "chat-v1"),
                    "template_version": "chat-template-v2",
                },
            },
            events=[
                ("artifact_ready", {"type": "recommendation", "id": rid}),
                ("text_delta", {"text": text}),
                (
                    "completed",
                    {
                        "message_id": mid,
                        "explanation_status": "VERIFIED" if sections else "TEMPLATE",
                    },
                ),
            ],
            now=self.clock(),
        )

    def rewrite_knowledge(self, job, args, baseline, topic):
        query = args["query"]
        if (
            not baseline.corpus_id
            or not baseline.corpus_hash
            or baseline.reason != "NO_EVIDENCE"
            or BLOCKED_INTENT.search(normalize_intent(job.request["content"]))
            or (is_knowledge_followup(query) and not topic)
            or not self.has_time(4)
        ):
            return None
        try:
            rewritten = self.query_rewriter(
                query[:800], redact(topic) if topic else None
            )
            if not isinstance(rewritten, str):
                return None
            rewritten = rewritten.strip()
            if (
                not re.fullmatch(r"[^\W\d_][\w -]{0,159}", rewritten)
                or rewritten.casefold() == query.strip().casefold()
                or redact(rewritten) != rewritten
                or not self.has_time(3)
            ):
                return None
            result = self.call(
                job,
                "retrieve_knowledge",
                args | {"query": rewritten, "corpus_id": str(baseline.corpus_id)},
            )
            parsed = Retrieval.model_validate(result)
            if (
                parsed.corpus_id == baseline.corpus_id
                and parsed.corpus_hash == baseline.corpus_hash
                and parsed.retrieval_version == baseline.retrieval_version
                and parsed.mode == "LEXICAL"
                and parsed.reason == "MATCH"
                and parsed.passages
                and all(
                    p.available_at <= aware(job.created_at) for p in parsed.passages
                )
            ):
                return result | {
                    "rewritten_query_hash": hashlib.sha256(
                        rewritten.encode()
                    ).hexdigest()
                }
        except (TimeoutError, httpx.HTTPError, ValueError, ToolError):
            pass
        return None

    def knowledge(self, job, select_claims=True, *, previous_topic=None, strategy=None):
        # Never retry a paid call or switch corpora after the first checkpoint.
        query = redact(job.request["content"])
        if strategy in ("EW", "MVO", "BL_ML"):
            query = f"{query} {strategy}"
        query_hash = hashlib.sha256(query.encode()).hexdigest()
        args = {"query": query, "as_of": aware(job.created_at).isoformat()}
        try:
            data = job.knowledge_checkpoint
            if data is None:
                if not self.has_time(3):
                    raise ValueError("retrieval deadline budget")
                vector, embedding_meta = (
                    self.dialogue.embed_query(job, query)
                    if self.query_rewriter is None and self.has_time(8)
                    else (None, {"reason": "TURN_BUDGET_EXHAUSTED"})
                )
                if vector:
                    args |= {
                        "embedding": vector["embedding"],
                        "embedding_model": "text-embedding-3-small",
                        "index_version": "openai-small-1536-v1",
                    }
                data = self.call(job, "retrieve_knowledge", args)
                parsed = Retrieval.model_validate(data)
                if any(p.available_at > aware(job.created_at) for p in parsed.passages):
                    raise ValueError("cutoff mismatch")
                if (
                    self.query_rewriter is not None
                    and select_claims
                    and not parsed.passages
                ):
                    data = (
                        self.rewrite_knowledge(job, args, parsed, previous_topic)
                        or data
                    )
                data = save_checkpoint(self.sessions, job, data)
            plan, metadata = None, None
            if (
                select_claims
                and self.query_rewriter is None
                and "rewritten_query_hash" not in data
                and data["passages"]
                and self.has_time(8)
            ):
                plan, metadata = self.dialogue.select_knowledge(job, data)
            evidence = render_evidence(
                data, plan, query_hash=query_hash, metadata=metadata
            )
        except (httpx.HTTPError, ValueError, KeyError, TypeError, ToolError):
            data = {
                "corpus_id": None,
                "corpus_version": None,
                "corpus_hash": None,
                "index_version": "openai-small-1536-v1",
                "retrieval_version": "knowledge-retrieval-v1",
                "mode": "LEXICAL",
                "reason": "KNOWLEDGE_UNAVAILABLE",
                "passages": [],
            }
            evidence = render_evidence(data, None, query_hash=query_hash)
        self.knowledge_data = data
        return self.validate_knowledge(job, evidence) if select_claims else evidence

    def validate_knowledge(self, job, evidence):
        try:
            if evidence.get("corpus_id"):
                active = self.call(
                    job,
                    "retrieve_knowledge",
                    {
                        "query": redact(job.request["content"]),
                        "as_of": aware(job.created_at).isoformat(),
                        "corpus_id": evidence["corpus_id"],
                    },
                )
                if active.get("corpus_hash") != evidence.get("corpus_hash"):
                    raise ValueError("deactivated corpus")
        except (httpx.HTTPError, ValueError, ToolError, KeyError):
            data = self.knowledge_data | {
                "passages": [],
                "reason": "CORPUS_UNAVAILABLE",
            }
            evidence = render_evidence(data, None, query_hash=evidence["query_hash"])
        self.call(job, "get_profile", {})
        return evidence

    def prune_events(self):
        with self.sessions.begin() as s:
            s.execute(
                delete(Event).where(Event.created_at < self.clock() - timedelta(days=7))
            )
