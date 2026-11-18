"""Finite approved claims only; independent from quantitative facts and their hashes."""

import hashlib
import json
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID
from pydantic import Field, model_validator
from portfolio_contracts import StrictModel, canonical_hash, utcnow
from sqlalchemy import select, update
from .models import Conversation, Job, Message


class Passage(StrictModel):
    chunk_id: UUID
    document_version_id: UUID
    document_version: int = Field(ge=1)
    document_title: str = Field(min_length=1, max_length=300)
    claim_id: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=2000)
    text_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_title: str = Field(min_length=1, max_length=300)
    source_url: str = Field(max_length=2048)
    locator: str = Field(min_length=1, max_length=300)
    available_at: datetime
    published_at: datetime | None = None

    @model_validator(mode="after")
    def integrity(self):
        u = urlsplit(self.source_url)
        if (
            u.scheme != "https"
            or not u.hostname
            or u.username
            or u.password
            or any(ord(c) < 33 for c in self.source_url)
        ):
            raise ValueError("unsafe citation")
        if (
            hashlib.sha256(self.text.encode()).hexdigest() != self.text_hash
            or self.available_at.tzinfo is None
        ):
            raise ValueError("evidence mismatch")
        return self


class Retrieval(StrictModel):
    corpus_id: UUID | None
    corpus_version: str | None
    corpus_hash: str | None = Field(pattern=r"^[a-f0-9]{64}$")
    index_version: Literal["openai-small-1536-v1"]
    retrieval_version: Literal["knowledge-retrieval-v1", "knowledge-retrieval-v2"]
    mode: Literal["LEXICAL", "HYBRID"]
    reason: str = Field(max_length=80)
    passages: list[Passage] = Field(max_length=5)


def previous_knowledge_topic(sessions, job):
    with sessions() as s:
        current = s.get(Message, job.message_id)
        if not current or current.conversation_id != job.conversation_id:
            return None
        previous = s.scalar(
            select(Message.structured)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(
                Message.conversation_id == job.conversation_id,
                Conversation.owner_key == job.owner_key,
                Message.role == "assistant",
                Message.created_at < current.created_at,
            )
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(1)
        )
    if not previous or previous.get("type") != "knowledge":
        return None
    topics = {c["document_title"] for c in previous["knowledge"]["citations"]}
    return next(iter(topics)) if len(topics) == 1 else None


class ClaimPlan(StrictModel):
    selected_chunk_ids: list[str] = Field(max_length=3)
    candidate_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


def render_evidence(data, plan, *, query_hash, metadata=None):
    original = {
        key: value for key, value in data.items() if key != "rewritten_query_hash"
    }
    parsed = Retrieval.model_validate(original)
    if len(json.dumps(data["passages"], ensure_ascii=False).encode()) > 8000:
        raise ValueError("context budget")
    ids = [str(p.chunk_id) for p in parsed.passages]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate chunk")
    reason = "PROVIDER_DISABLED"
    selected = ids[:3]
    status = "REFERENCE" if selected else "MISSING"
    if plan is not None:
        try:
            p = ClaimPlan.model_validate(plan)
            if (
                p.candidate_hash != canonical_hash(data)
                or len(set(p.selected_chunk_ids)) != len(p.selected_chunk_ids)
                or not set(p.selected_chunk_ids) <= set(ids)
            ):
                raise ValueError("references")
            selected = p.selected_chunk_ids
            status = "VERIFIED_REFERENCES" if selected else "MISSING"
            reason = "VALID_REFERENCES"
        except ValueError:
            reason = "INVALID_REFERENCES"
    result = {
        k: data[k]
        for k in (
            "corpus_id",
            "corpus_version",
            "corpus_hash",
            "index_version",
            "retrieval_version",
            "mode",
        )
    }
    result.update(
        status=status,
        reason=data["reason"],
        selection_reason=reason,
        query_hash=query_hash,
        schema_version="knowledge-claims-v1",
        prompt_version="knowledge-selection-v1",
        retrieved_chunk_ids=ids,
        selected_chunk_ids=selected,
        citations=[
            p.model_dump(mode="json")
            for p in parsed.passages
            if str(p.chunk_id) in selected
        ],
        provider=metadata or {"reason": "NOT_CONFIGURED"},
    )
    if "rewritten_query_hash" in data:
        result["rewritten_query_hash"] = data["rewritten_query_hash"]
    result["evidence_hash"] = canonical_hash(result)
    return result


def save_checkpoint(sessions, job, data):
    now = utcnow()
    with sessions.begin() as s:
        result = s.execute(
            update(Job)
            .where(
                Job.id == job.id,
                Job.status == "RUNNING",
                Job.lease_token == job.lease_token,
                Job.lease_until > now,
                Job.knowledge_checkpoint.is_(None),
            )
            .values(knowledge_checkpoint=data)
        )
        if result.rowcount == 1:
            return data
        return s.get(Job, job.id).knowledge_checkpoint
