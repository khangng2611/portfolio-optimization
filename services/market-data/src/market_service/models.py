from uuid import uuid4

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from portfolio_contracts import utcnow


def new_id():
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class Actor(Base):
    __tablename__ = "market_actor"
    __table_args__ = (UniqueConstraint("issuer", "subject"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    issuer: Mapped[str] = mapped_column(String(500))
    subject: Mapped[str] = mapped_column(String(255))


class Asset(Base):
    __tablename__ = "asset"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))
    unit: Mapped[str] = mapped_column(String(32))


class PriceRevision(Base):
    __tablename__ = "price_revision"
    __table_args__ = (
        UniqueConstraint(
            "asset_id", "observation_date", "provider", "price_type", "revision"
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    asset_id: Mapped[str] = mapped_column(ForeignKey("asset.id"), index=True)
    observation_date: Mapped[object] = mapped_column(Date, index=True)
    price_vnd: Mapped[object] = mapped_column(Numeric(24, 6))
    unit: Mapped[str] = mapped_column(String(32))
    source_unit: Mapped[str] = mapped_column(String(32))
    provider: Mapped[str] = mapped_column(String(100))
    price_type: Mapped[str] = mapped_column(String(16))
    revision: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    published_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    available_at: Mapped[object] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)
    source_hash: Mapped[str | None] = mapped_column(String(64))


class IngestionJob(Base):
    __tablename__ = "ingestion_job"
    __table_args__ = (UniqueConstraint("actor_id", "idempotency_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_id: Mapped[str] = mapped_column(ForeignKey("market_actor.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="QUEUED")
    trace_context: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    input: Mapped[dict] = mapped_column(JSON)
    inserted_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)
    deadline: Mapped[object] = mapped_column(DateTime(timezone=True))


class Snapshot(Base):
    __tablename__ = "market_snapshot"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True)
    manifest: Mapped[dict] = mapped_column(JSON)
    observations: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


class Outbox(Base):
    __tablename__ = "outbox_event"
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    trace_context: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)
    published_at: Mapped[object | None] = mapped_column(
        DateTime(timezone=True), index=True
    )


class Inbox(Base):
    __tablename__ = "inbox_event"
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    received_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)
