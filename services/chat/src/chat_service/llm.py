"""Owner-scoped dialogue context and durable billing reservations, never tool authority."""

import os
import re
from sqlalchemy import select, update, func

from portfolio_contracts import utcnow
from .models import Conversation, Job, Message, ProviderInvocation
from .openai_provider import OpenAIProvider, redact


class InvocationLedger:
    def __init__(self, sessions):
        self.sessions = sessions

    def invoke(self, job, purpose, call):
        if purpose not in ("intent", "explanation"):
            return None, {"reason": "INVALID_PURPOSE"}
        now = utcnow()
        with self.sessions.begin() as s:
            if s.bind.dialect.name == "postgresql":
                s.execute(select(func.pg_advisory_xact_lock(784512304)))
                # Match HTTP lock order: conversation before job.
                s.scalar(
                    select(Conversation)
                    .where(Conversation.id == job.conversation_id)
                    .with_for_update()
                )
            fenced = s.execute(
                update(Job)
                .where(
                    Job.id == job.id,
                    Job.owner_key == job.owner_key,
                    Job.status == "RUNNING",
                    Job.lease_token == job.lease_token,
                    Job.lease_until > now,
                )
                .values(lease_token=Job.lease_token)
            )
            if fenced.rowcount != 1:
                return None, {"reason": "LEASE_LOST"}
            conversation = s.get(Conversation, job.conversation_id)
            if (
                not conversation
                or conversation.owner_key != job.owner_key
                or not conversation.llm_consent
            ):
                return None, {"reason": "CONSENT_REQUIRED"}
            old = s.get(ProviderInvocation, (job.id, purpose))
            if old:
                return old.output, old.details or {
                    "reason": "PROVIDER_BUDGET_EXHAUSTED"
                }
            try:
                limit = min(
                    100, max(0, int(os.environ.get("CHAT_LLM_DAILY_CALL_LIMIT", "20")))
                )
            except ValueError:
                limit = 0  # fail closed on a malformed deployment quota
            day = now.replace(hour=0, minute=0, second=0, microsecond=0)
            used = s.scalar(
                select(func.count())
                .select_from(ProviderInvocation)
                .where(ProviderInvocation.created_at >= day)
            )
            if used >= limit:
                return None, {"reason": "DAILY_BUDGET_EXHAUSTED"}
            s.add(
                ProviderInvocation(
                    job_id=job.id,
                    purpose=purpose,
                    owner_key=job.owner_key,
                    created_at=now,
                )
            )
            s.execute(
                update(Job)
                .where(Job.id == job.id)
                .values(provider_calls=Job.provider_calls + 1)
            )
        # Reservation survives crashes and uncertain HTTP outcomes. Never retry it.
        value, metadata = call()
        with self.sessions.begin() as s:
            record = s.get(ProviderInvocation, (job.id, purpose))
            record.output, record.details = value, metadata
        return value, metadata


class Dialogue:
    def __init__(self, sessions):
        self.sessions, self.provider = sessions, OpenAIProvider()
        self.ledger = InvocationLedger(sessions)

    @property
    def enabled(self):
        return (
            os.environ.get("CHAT_LLM_PROVIDER") == "openai" and self.provider.configured
        )

    def context(self, job):
        with self.sessions() as s:
            c = s.get(Conversation, job.conversation_id)
            if not c or c.owner_key != job.owner_key or not c.llm_consent:
                return None, None
            current = s.get(Message, job.message_id)
            rows = s.scalars(
                select(Message)
                .where(
                    Message.conversation_id == c.id,
                    Message.id != current.id,
                    Message.created_at <= current.created_at,
                )
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(4)
            ).all()
            previous = next(
                (m.structured for m in rows if m.role == "assistant" and m.structured),
                {},
            )
            last_result = next(
                (
                    m.structured.get("recommendation_id")
                    for m in rows
                    if m.role == "assistant"
                    and m.structured
                    and m.structured.get("type") == "recommendation"
                ),
                None,
            )
            context = {
                "content": redact(job.request["content"]),
                "previous": {
                    k: previous[k] for k in ("type", "fields") if k in previous
                },
                "history": [
                    {"role": m.role, "content": redact(m.content[:400])}
                    for m in reversed(rows)
                ],
                "has_portfolio": bool(job.request.get("portfolio_id")),
                "has_recommendation": bool(last_result),
            }
            return context, last_result

    def interpret(self, job):
        request = job.request.copy()
        if request.get("confirmation") or request.get("intent") or not self.enabled:
            return request, None
        context, last_result = self.context(job)
        if context is None:
            return request, {"reason": "CONSENT_REQUIRED"}
        plan, meta = self.ledger.invoke(
            job, "intent", lambda: self.provider.interpret(context)
        )
        if plan:
            request["intent"] = plan["intent"]
            # An explicit UI strategy wins; otherwise use only extracted intent.
            evidence = {
                "EW": r"\bew\b|chia đều|equal.?weight",
                "MVO": r"\bmvo\b|mean.?variance|trung bình.?phương sai",
                "BL_ML": r"\bbl[_+\s]*ml\b|black.?litterman.*\bml\b",
            }
            strategy = plan["strategy"]
            verified = strategy and re.search(
                evidence[strategy], request["content"], re.IGNORECASE
            )
            request["strategy"] = request.get("strategy") or (
                strategy if verified else None
            )
            if plan["reference"] == "last_recommendation" and last_result:
                request["recommendation_id"] = (
                    request.get("recommendation_id") or last_result
                )
        return request, meta

    def explain(self, job, facts, digest):
        if not self.enabled:
            return None, {"reason": "NOT_CONFIGURED"}
        return self.ledger.invoke(
            job,
            "explanation",
            lambda: self.provider.explain(
                facts, digest, question=job.request["content"]
            ),
        )
