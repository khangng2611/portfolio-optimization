"""Owner-scoped dialogue context and durable billing reservations, never tool authority."""

import os
import re
from decimal import Decimal
from uuid import UUID
from sqlalchemy import select, update, func

from portfolio_contracts import system_hybrid_managed, utcnow
from .models import Conversation, Job, Message, ProviderInvocation
from .openai_provider import OpenAIProvider, redact
from .embeddings import Embeddings, approved_budget


def developer_enabled():
    return os.environ.get("CHAT_LLM_ENABLED") == "1"


class InvocationLedger:
    def __init__(self, sessions):
        self.sessions = sessions

    def invoke(self, job, purpose, call, *, rag=False):
        if purpose not in ("intent", "explanation", "query_embedding", "response"):
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
            if not conversation or conversation.owner_key != job.owner_key:
                return None, {"reason": "OWNER_REQUIRED"}
            if not developer_enabled():
                return None, {"reason": "DEVELOPER_DISABLED"}
            if (
                purpose == "query_embedding"
                and os.environ.get("CHAT_QUERY_EMBEDDINGS_ENABLED") != "1"
            ):
                return None, {"reason": "EMBEDDINGS_DISABLED"}
            budget = approved_budget() if rag or purpose == "query_embedding" else None
            if (rag or purpose == "query_embedding") and not budget:
                return None, {"reason": "BUDGET_NOT_APPROVED"}
            old = s.get(ProviderInvocation, (job.id, purpose))
            if old:
                return old.output, old.details or {
                    "reason": "PROVIDER_BUDGET_EXHAUSTED"
                }
            reserved = Decimal("0")
            if budget:
                try:
                    text_limit = min(
                        100,
                        max(
                            0, int(os.environ.get("CHAT_LLM_APPROVAL_CALL_LIMIT", "20"))
                        ),
                    )
                except ValueError:
                    text_limit = 0
                embedding = purpose == "query_embedding"
                reserved = Decimal("0.00016" if embedding else "0.0017")
                previous = s.scalars(
                    select(ProviderInvocation).where(
                        ProviderInvocation.budget_id == budget[0]
                    )
                ).all()
                group = [
                    r for r in previous if (r.purpose == "query_embedding") == embedding
                ]
                if len(group) >= (50 if embedding else text_limit) or sum(
                    (Decimal(r.reserved_usd) for r in group), Decimal("0")
                ) + reserved > budget[1] * Decimal("0.2" if embedding else "0.6"):
                    return None, {"reason": "ACCEPTANCE_BUDGET_EXHAUSTED"}
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
                .where(
                    ProviderInvocation.created_at >= day,
                    (ProviderInvocation.purpose == "query_embedding")
                    if purpose == "query_embedding"
                    else (ProviderInvocation.purpose != "query_embedding"),
                )
            )
            if used >= (50 if purpose == "query_embedding" else limit):
                return None, {"reason": "DAILY_BUDGET_EXHAUSTED"}
            s.add(
                ProviderInvocation(
                    job_id=job.id,
                    purpose=purpose,
                    owner_key=job.owner_key,
                    budget_id=budget[0] if budget else None,
                    reserved_usd=str(reserved),
                    created_at=now,
                )
            )
            if purpose != "query_embedding":
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
            developer_enabled()
            and os.environ.get("CHAT_LLM_PROVIDER") == "openai"
            and self.provider.configured
        )

    @property
    def contextual(self):
        return self.enabled and os.environ.get("CHAT_CONTEXTUAL_REPLIES") == "1"

    def recommendation_reference(self, job):
        with self.sessions() as s:
            conversation = s.get(Conversation, job.conversation_id)
            current = s.get(Message, job.message_id)
            portfolio_id = job.request.get("portfolio_id")
            if (
                not conversation
                or conversation.owner_key != job.owner_key
                or not current
                or current.conversation_id != conversation.id
                or not portfolio_id
            ):
                return None
            reference = s.scalar(
                select(Message.structured["recommendation_id"].as_string())
                .where(
                    Message.conversation_id == conversation.id,
                    Message.role == "assistant",
                    Message.created_at < current.created_at,
                    Message.structured["type"].as_string() == "recommendation",
                    Message.structured["facts"]["portfolio_id"].as_string()
                    == str(portfolio_id),
                )
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(1)
            )
        try:
            return str(UUID(reference)) if reference else None
        except (ValueError, TypeError, AttributeError):
            return None

    def context(self, job):
        with self.sessions() as s:
            c = s.get(Conversation, job.conversation_id)
            if not c or c.owner_key != job.owner_key or not developer_enabled():
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
            last_result = self.recommendation_reference(job)
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
            return request, {"reason": "DEVELOPER_DISABLED"}
        plan, meta = self.ledger.invoke(
            job,
            "intent",
            lambda: self.provider.interpret(context),
            rag=self.contextual or bool(approved_budget()),
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
            request["strategy"] = None if system_hybrid_managed() else request.get("strategy") or (
                strategy if verified else None
            )
            if plan["reference"] == "last_recommendation" and last_result:
                request["recommendation_id"] = (
                    request.get("recommendation_id") or last_result
                )
        return request, meta

    def respond(self, job, state):
        if not self.contextual or not approved_budget():
            return None, {"reason": "BUDGET_NOT_APPROVED"}
        context, _ = self.context(job)
        if context is None:
            return None, {"reason": "DEVELOPER_DISABLED"}
        safe_state = {k: state[k] for k in ("type", "fields") if k in state}
        if state.get("knowledge"):
            safe_state["has_sources"] = bool(state["knowledge"]["citations"])
        return self.ledger.invoke(
            job,
            "response",
            lambda: self.provider.respond(context | {"state": safe_state}),
            rag=True,
        )

    def explain(self, job, facts, digest, knowledge_data=None):
        if not self.enabled:
            return None, {"reason": "NOT_CONFIGURED"}
        if knowledge_data and approved_budget():
            return self.ledger.invoke(
                job,
                "explanation",
                lambda: self.provider.explain_with_knowledge(
                    facts, digest, knowledge_data, question=job.request["content"]
                ),
                rag=True,
            )
        return self.ledger.invoke(
            job,
            "explanation",
            lambda: self.provider.explain(
                facts, digest, question=job.request["content"]
            ),
        )

    def explain_claims(self, job, digest, evidence, claims):
        if not self.enabled:
            return None, {"reason": "NOT_CONFIGURED"}
        context, _ = self.context(job)
        return self.ledger.invoke(
            job, "explanation", lambda: self.provider.explain_claims(
                digest, evidence["evidence_hash"], claims, question=job.request["content"], history=(context or {}).get("history", [])
            ), rag=True,
        )

    def select_knowledge(self, job, data):
        if not self.enabled:
            return None, {"reason": "NOT_CONFIGURED"}
        # New RAG spending never inherits old Chat approval or a configured key.
        if not approved_budget():
            return None, {"reason": "BUDGET_NOT_APPROVED"}
        return self.ledger.invoke(
            job,
            "explanation",
            lambda: self.provider.select_knowledge(
                data, question=job.request["content"]
            ),
            rag=True,
        )

    def embed_query(self, job, query):
        return self.ledger.invoke(
            job, "query_embedding", lambda: Embeddings().embed(query)
        )
