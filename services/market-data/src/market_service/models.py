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
    ingestion_job_id: Mapped[str | None] = mapped_column(
        ForeignKey("ingestion_job.id"), nullable=True, index=True
    )
    data_origin: Mapped[str] = mapped_column(
        String(16), default="unverified", server_default="unverified"
    )
    price_basis: Mapped[str] = mapped_column(
        String(32), default="unverified", server_default="unverified"
    )


class IngestionJob(Base):
    __tablename__ = "ingestion_job"
    __table_args__ = (UniqueConstraint("actor_id", "idempotency_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_id: Mapped[str] = mapped_column(ForeignKey("market_actor.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="QUEUED")
    trace_context: Mapped[dict | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
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
    trace_context: Mapped[dict | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)
    published_at: Mapped[object | None] = mapped_column(
        DateTime(timezone=True), index=True
    )


class Inbox(Base):
    __tablename__ = "inbox_event"
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    received_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


class RegisteredDataset(Base):
    __tablename__ = "registered_dataset"
    dataset_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64))
    spec: Mapped[dict] = mapped_column(JSON)
    start_date: Mapped[object | None] = mapped_column(Date)
    end_date: Mapped[object | None] = mapped_column(Date)
    registered_by: Mapped[str] = mapped_column(ForeignKey("market_actor.id"))
    registered_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class DatasetRegistrationReceipt(Base):
    __tablename__ = "dataset_registration_receipt"
    __table_args__ = (UniqueConstraint("actor_id", "idempotency_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_id: Mapped[str] = mapped_column(ForeignKey("market_actor.id"))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict] = mapped_column(JSON)


class QualityReport(Base):
    __tablename__ = "ingestion_quality_report"
    job_id: Mapped[str] = mapped_column(
        ForeignKey("ingestion_job.id"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(24))
    report: Mapped[dict] = mapped_column(JSON)
    checked_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


class RefreshSchedule(Base):
    __tablename__ = "refresh_schedule"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_id: Mapped[str] = mapped_column(ForeignKey("market_actor.id"), index=True)
    config: Mapped[dict] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer, default=1)
    enabled: Mapped[int] = mapped_column(Integer, default=1)
    next_run_at: Mapped[object] = mapped_column(DateTime(timezone=True), index=True)
    last_successful_cutoff: Mapped[object | None] = mapped_column(Date)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


class RefreshJob(Base):
    __tablename__ = "refresh_job"
    __table_args__ = (UniqueConstraint("schedule_id", "tick_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    schedule_id: Mapped[str] = mapped_column(ForeignKey("refresh_schedule.id"), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("market_actor.id"), index=True)
    tick_key: Mapped[str] = mapped_column(String(128))
    config: Mapped[dict] = mapped_column(JSON)
    schedule_version: Mapped[int] = mapped_column(Integer)
    start_date: Mapped[object] = mapped_column(Date)
    cutoff_date: Mapped[object] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(24), default="QUEUED", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_token: Mapped[str | None] = mapped_column(String(36))
    lease_until: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    available_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)
    deadline: Mapped[object] = mapped_column(DateTime(timezone=True))
    error: Mapped[dict | None] = mapped_column(JSON)
    source_manifest: Mapped[dict | None] = mapped_column(JSON)
    artifacts: Mapped[list] = mapped_column(JSON, default=list)
    ingestion_job_ids: Mapped[list] = mapped_column(JSON, default=list)
    snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("market_snapshot.id"))
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))


class RefreshReceipt(Base):
    __tablename__ = "refresh_receipt"
    __table_args__ = (UniqueConstraint("actor_id", "idempotency_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_id: Mapped[str] = mapped_column(ForeignKey("market_actor.id"))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict] = mapped_column(JSON)
