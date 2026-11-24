from uuid import uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
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
    __table_args__ = (ForeignKeyConstraint(
        ["id", "asset_selection_revision_id"],
        ["portfolio_asset_selection.portfolio_id", "portfolio_asset_selection.id"],
        name="fk_portfolio_owned_asset_selection", use_alter=True,
    ),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("app_user.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    capital_vnd: Mapped[float] = mapped_column(Numeric(24, 4))
    universe_id: Mapped[str] = mapped_column(String(64))
    constraints: Mapped[dict] = mapped_column(JSON)
    risk_profile: Mapped[dict | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    asset_selection_revision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


class PortfolioAssetSelection(Base):
    """Append-only candidate revisions; NULL Portfolio pointer preserves legacy."""
    __tablename__ = "portfolio_asset_selection"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "portfolio_version"),
        UniqueConstraint("portfolio_id", "id"),
        UniqueConstraint("owner_user_id", "portfolio_id", "idempotency_key"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolio.id"), index=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("app_user.id"), index=True)
    portfolio_version: Mapped[int] = mapped_column(Integer)
    candidate_asset_ids: Mapped[list] = mapped_column(JSON)
    candidate_hash: Mapped[str] = mapped_column(String(64))
    selection_policy_id: Mapped[str] = mapped_column(String(64), default="user-k5-v1")
    risk_policy_id: Mapped[str] = mapped_column(String(64), default="custom-mixed-risk-v1")
    actor: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    body_hash: Mapped[str] = mapped_column(String(64))
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
    explanation_evidence: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


class GoldShadowEnrollment(Base):
    __tablename__ = "gold_shadow_enrollment"
    study_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    started_at: Mapped[object] = mapped_column(DateTime(timezone=True))


class GoldShadowDecision(Base):
    __tablename__ = "gold_shadow_decision"
    job_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    series_id: Mapped[str] = mapped_column(String(36), index=True)
    receipt: Mapped[dict] = mapped_column(JSON)


class GoldShadowWitness(Base):
    __tablename__ = "gold_shadow_witness"
    job_id: Mapped[str] = mapped_column(ForeignKey("gold_shadow_decision.job_id"), primary_key=True)
    witnessed_at: Mapped[object] = mapped_column(DateTime(timezone=True))
    receipt_sha256: Mapped[str] = mapped_column(String(64))


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


class DelegationGrant(Base):
    __tablename__ = "delegation_grant"
    __table_args__ = (UniqueConstraint("owner_user_id", "chat_job_id", "authorization_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("app_user.id"), index=True)
    actor: Mapped[str] = mapped_column(String(64))
    conversation_id: Mapped[str] = mapped_column(String(36))
    chat_job_id: Mapped[str] = mapped_column(String(36))
    authorization_id: Mapped[str] = mapped_column(String(36), default="initial")
    portfolio_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    tools: Mapped[list] = mapped_column(JSON)
    body_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[object] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
