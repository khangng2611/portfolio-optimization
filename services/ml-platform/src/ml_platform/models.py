from sqlalchemy import DateTime, JSON, String, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from portfolio_contracts import utcnow


class Base(DeclarativeBase):
    pass


class TrainingJob(Base):
    __tablename__ = "ml_training_job"
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


class Model(Base):
    __tablename__ = "ml_model"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    training_job_id: Mapped[str] = mapped_column(
        ForeignKey("ml_training_job.id"), unique=True
    )
    status: Mapped[str] = mapped_column(String(16), index=True)
    version: Mapped[int] = mapped_column(default=1)
    # Immutable training metadata never changes when a reviewer decides.
    manifest: Mapped[dict] = mapped_column(JSON)
    provenance: Mapped[dict] = mapped_column(JSON)
    candidate_ref: Mapped[dict] = mapped_column(JSON)
    approved_ref: Mapped[dict | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


class Review(Base):
    __tablename__ = "ml_review"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    model_id: Mapped[str] = mapped_column(ForeignKey("ml_model.id"), unique=True)
    actor: Mapped[str] = mapped_column(String(80))
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    body_hash: Mapped[str] = mapped_column(String(64))
    decision: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(String(1000))
    expected_version: Mapped[int]
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)
