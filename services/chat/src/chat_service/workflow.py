from datetime import timedelta
import time
from uuid import uuid4
import httpx
from sqlalchemy import delete
from portfolio_contracts import aware, canonical_hash, utcnow
from .models import ToolCall, Event
from .provider import Provider, render
from .queue import Queue
from .tools import ToolError
from .llm import Dialogue


def intent_of(request):
    if request.get("confirmation"):
        return "allocation"
    if request.get("intent"):
        return request["intent"]
    text = request["content"].casefold()
    if any(s in text for s in ("phân bổ", "allocation", "tối ưu")):
        return "allocation"
    if any(s in text for s in ("giải thích", "explain")):
        return "explain"
    if any(s in text for s in ("thị trường", "market")):
        return "market"
    if "hồ sơ" in text:
        return "profile"
    if "danh mục" in text:
        return "portfolio"
    return "help"


class Worker:
    def __init__(self, sessions, tools, provider=None, clock=utcnow):
        self.sessions, self.tools, self.clock = sessions, tools, clock
        self.q, self.provider = Queue(sessions), provider or Provider()
        self.dialogue = Dialogue(sessions)

    def call(self, job, name, args):
        if time.monotonic() - self.started > 20 or self.tool_count >= 6:
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
                    raise ToolError("ALLOCATION_FAILED", permanent=True)
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
                        "strategy": pin["strategy"],
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
            r, self.dialogue_metadata = self.dialogue.interpret(job)
            intent = intent_of(r)
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
                if not r.get("recommendation_id"):
                    return self.reply(
                        job,
                        "Chọn đề xuất cần giải thích.",
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
                )
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
            if not r.get("strategy") and not r.get("confirmed_input"):
                return self.reply(
                    job,
                    "Chọn chiến lược EW, MVO hoặc BL_ML; hệ thống không tự chuyển chiến lược khi có lỗi.",
                    {"type": "input_required", "fields": ["strategy"]},
                    status="WAITING_INPUT",
                    stage="COLLECT",
                )
            if not r.get("confirmation"):
                return self.confirmation(job, p, r["strategy"])
            pin = r["confirmed_input"]
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

    def explain(self, job, facts):
        digest = canonical_hash(facts)
        if self.dialogue.enabled:
            sections, metadata = self.dialogue.explain(job, facts, digest)
        elif self.q.reserve_provider(job, now=self.clock()):
            sections, metadata = self.provider.explain(facts, digest)
        else:
            sections, metadata = None, {"reason": "PROVIDER_BUDGET_EXHAUSTED"}
        text = render(facts, sections)
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
                    "explanation_status": "VERIFIED" if sections else "TEMPLATE",
                    "provider": metadata,
                    "schema_version": "fact-plan-v1",
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

    def prune_events(self):
        with self.sessions.begin() as s:
            s.execute(
                delete(Event).where(Event.created_at < self.clock() - timedelta(days=7))
            )
