from uuid import uuid4

from sqlalchemy import (
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


class User(Base):
    __tablename__ = "app_user"
    __table_args__ = (UniqueConstraint("issuer", "subject"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    issuer: Mapped[str] = mapped_column(String(500))
    subject: Mapped[str] = mapped_column(String(255))


class Portfolio(Base):
    __tablename__ = "portfolio"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("app_user.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    capital_vnd: Mapped[float] = mapped_column(Numeric(24, 4))
    universe_id: Mapped[str] = mapped_column(String(64))
    constraints: Mapped[dict] = mapped_column(JSON)
    risk_profile: Mapped[dict | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


class RiskAssessment(Base):
    """Append-only policy revisions and durable confirmation receipts.

    Existing portfolios intentionally receive no fabricated historical revisions.
    Active status is derived from Portfolio.risk_profile.version_id, so manual
    constraint edits deactivate a revision without mutating its audit record.
    """

    __tablename__ = "risk_assessment"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "portfolio_version"),
        UniqueConstraint("owner_user_id", "portfolio_id", "idempotency_key"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolio.id"), index=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("app_user.id"), index=True)
    portfolio_version: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(32))
    answers: Mapped[dict] = mapped_column(JSON)
    constraints: Mapped[dict] = mapped_column(JSON)
    risk_profile: Mapped[dict] = mapped_column(JSON)
    mapping_version: Mapped[str] = mapped_column(String(64))
    policy_version_id: Mapped[str] = mapped_column(String(128))
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    body_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


class Job(Base):
    __tablename__ = "job"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "portfolio_id", "idempotency_key"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("app_user.id"), index=True)
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolio.id"))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    body_hash: Mapped[str] = mapped_column(String(64))
    input_hash: Mapped[str] = mapped_column(String(64))
    trace_context: Mapped[dict | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    input: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="QUEUED")
    recommendation_id: Mapped[str | None] = mapped_column(String(36))
    error: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)
    deadline: Mapped[object] = mapped_column(DateTime(timezone=True))


class Recommendation(Base):
    __tablename__ = "recommendation"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("job.id"), unique=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("app_user.id"), index=True)
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolio.id"))
    run_id: Mapped[str] = mapped_column(String(36))
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


class AcceptedTarget(Base):
    __tablename__ = "accepted_target"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    recommendation_id: Mapped[str] = mapped_column(
        ForeignKey("recommendation.id"), unique=True
    )
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolio.id"), index=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("app_user.id"), index=True)
    portfolio_version: Mapped[int] = mapped_column(Integer)
    allocation: Mapped[dict] = mapped_column(JSON)
    accepted_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


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
