"""Chat-owned durable state. No cross-service foreign keys or bearer tokens."""

from uuid import uuid4
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from portfolio_contracts import utcnow


def new_id():
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class Conversation(Base):
    __tablename__ = "conversation"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_key: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(120))
    portfolio_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    active_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # Historical receipt fields. Provider access uses developer configuration.
    llm_consent: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    consent_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


class Message(Base):
    __tablename__ = "message"
    __table_args__ = (UniqueConstraint("conversation_id", "client_message_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversation.id"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    client_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    body_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    structured: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    consumed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


class Job(Base):
    __tablename__ = "chat_job"
    __table_args__ = (
        UniqueConstraint("message_id"),
        Index("ix_chat_job_claim", "status", "next_attempt_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversation.id"), index=True
    )
    owner_key: Mapped[str] = mapped_column(String(64), index=True)
    message_id: Mapped[str] = mapped_column(ForeignKey("message.id"))
    knowledge_checkpoint: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    request: Mapped[dict] = mapped_column(JSON)
    reauthorization_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    grant_id: Mapped[str] = mapped_column(String(36))
    grant_expires_at: Mapped[object] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="QUEUED")
    stage: Mapped[str] = mapped_column(String(32), default="INTENT")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    provider_calls: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_until: Mapped[object | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_attempt_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    deadline: Mapped[object] = mapped_column(DateTime(timezone=True))
    dependency_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    recommendation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    result_message_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    error: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_sequence: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProviderInvocation(Base):
    __tablename__ = "provider_invocation"
    job_id: Mapped[str] = mapped_column(ForeignKey("chat_job.id"), primary_key=True)
    purpose: Mapped[str] = mapped_column(String(24), primary_key=True)
    budget_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reserved_usd: Mapped[str] = mapped_column(
        String(32), default="0", server_default="0"
    )
    owner_key: Mapped[str] = mapped_column(String(64), index=True)
    output: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class Event(Base):
    __tablename__ = "job_event"
    job_id: Mapped[str] = mapped_column(ForeignKey("chat_job.id"), primary_key=True)
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class ToolCall(Base):
    __tablename__ = "tool_call"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("chat_job.id"), index=True)
    tool: Mapped[str] = mapped_column(String(64))
    arguments_hash: Mapped[str] = mapped_column(String(64))
    result_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_reference: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeEvidence(Base):
    __tablename__ = "knowledge_evidence"
    job_id: Mapped[str] = mapped_column(ForeignKey("chat_job.id"), primary_key=True)
    evidence_hash: Mapped[str] = mapped_column(String(64))
    evidence: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)
