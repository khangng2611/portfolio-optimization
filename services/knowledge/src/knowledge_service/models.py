"""Knowledge-owned versions, queue, immutable references and lifecycle audit."""

from uuid import uuid4
import json
from sqlalchemy import (
    String,
    Text,
    Integer,
    JSON,
    DateTime,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import UserDefinedType
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql.base import ischema_names
from portfolio_contracts import utcnow


def new_id():
    return str(uuid4())


class Vector(UserDefinedType):
    cache_ok = True

    def __init__(self, dimensions=1536):
        if dimensions != 1536:
            raise ValueError("unsupported vector dimension")

    def get_col_spec(self, **kw):
        return "vector(1536)"

    def bind_processor(self, dialect):
        return lambda v: json.dumps(v, allow_nan=False) if v is not None else None


@compiles(Vector, "sqlite")
def sqlite_vector(type_, compiler, **kw):
    return "TEXT"


class Base(DeclarativeBase):
    pass


class Corpus(Base):
    __tablename__ = "corpus"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    body_hash: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="DRAFT")
    version: Mapped[int] = mapped_column(Integer, default=1)
    manifest: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


class ActiveCorpus(Base):
    __tablename__ = "active_corpus"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    corpus_id: Mapped[str | None] = mapped_column(
        ForeignKey("corpus.id"), nullable=True
    )
    epoch: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class Document(Base):
    __tablename__ = "document_version"
    __table_args__ = (UniqueConstraint("document_key", "version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_key: Mapped[str] = mapped_column(String(80))
    version: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    metadata_hash: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(300))
    visibility: Mapped[str] = mapped_column(String(16))
    published_at: Mapped[object | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    available_at: Mapped[object] = mapped_column(DateTime(timezone=True))


class Membership(Base):
    __tablename__ = "corpus_document"
    corpus_id: Mapped[str] = mapped_column(ForeignKey("corpus.id"), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("document_version.id"), primary_key=True
    )


class Chunk(Base):
    __tablename__ = "document_chunk"
    __table_args__ = (UniqueConstraint("document_id", "claim_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("document_version.id"))
    claim_id: Mapped[str] = mapped_column(String(80))
    text: Mapped[str] = mapped_column(Text)
    text_hash: Mapped[str] = mapped_column(String(64))
    search_text: Mapped[str] = mapped_column(Text)
    source_title: Mapped[str] = mapped_column(String(300))
    source_url: Mapped[str] = mapped_column(String(2048))
    locator: Mapped[str] = mapped_column(String(300))
    embedding: Mapped[object | None] = mapped_column(Vector(), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    index_version: Mapped[str] = mapped_column(
        String(80), default="openai-small-1536-v1"
    )


class IndexJob(Base):
    __tablename__ = "indexing_job"
    __table_args__ = (UniqueConstraint("actor", "idempotency_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    corpus_id: Mapped[str] = mapped_column(ForeignKey("corpus.id"), unique=True)
    actor: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    body_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="DRAFT", index=True)
    lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_until: Mapped[object | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


class LifecycleAudit(Base):
    __tablename__ = "lifecycle_audit"
    __table_args__ = (UniqueConstraint("actor", "idempotency_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    body_hash: Mapped[str] = mapped_column(String(64))
    corpus_id: Mapped[str] = mapped_column(ForeignKey("corpus.id"))
    action: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(String(300))
    response: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


class EmbeddingInvocation(Base):
    __tablename__ = "embedding_invocation"
    content_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    budget_id: Mapped[str] = mapped_column(String(128), server_default="legacy")
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reserved_usd: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


# PostgreSQL reflection must understand the pinned extension type for Alembic checks.

ischema_names["vector"] = Vector


class IndexingKey(Base):
    __tablename__ = "indexing_key"
    actor: Mapped[str] = mapped_column(String(64), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    body_hash: Mapped[str] = mapped_column(String(64))
    job_id: Mapped[str] = mapped_column(ForeignKey("indexing_job.id"))
