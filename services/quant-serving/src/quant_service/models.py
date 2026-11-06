from sqlalchemy import DateTime, JSON, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from portfolio_contracts import utcnow


class Base(DeclarativeBase):
    pass


class Run(Base):
    __tablename__ = "numerical_run"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(36), unique=True)
    input_hash: Mapped[str] = mapped_column(String(64))
    trace_context: Mapped[dict | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


class Outbox(Base):
    __tablename__ = "outbox_event"
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    trace_context: Mapped[dict | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    payload: Mapped[dict] = mapped_column(JSON)
    published_at: Mapped[object | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )


class Inbox(Base):
    __tablename__ = "inbox_event"
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    received_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


class PublicationJob(Base):
    """Operator request pins never change after insertion; leases fence completion."""

    __tablename__ = "publication_job"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    body_hash: Mapped[str] = mapped_column(String(64))
    request: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    max_attempts: Mapped[int] = mapped_column(default=5)
    lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_until: Mapped[object | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_attempt_at: Mapped[object] = mapped_column(DateTime(timezone=True), index=True)
    result: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    safe_error: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)
