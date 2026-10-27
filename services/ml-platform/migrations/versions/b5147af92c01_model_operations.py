"""ML-owned manual training queue, immutable model metadata and review audit."""

from alembic import op
import sqlalchemy as sa

revision = "b5147af92c01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ml_training_job",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("idempotency_key", sa.String(200), nullable=False, unique=True),
        sa.Column("body_hash", sa.String(64), nullable=False),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("lease_token", sa.String(36)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result", sa.JSON(none_as_null=True)),
        sa.Column("safe_error", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ml_training_job_status", "ml_training_job", ["status"])
    op.create_index(
        "ix_ml_training_job_next_attempt_at", "ml_training_job", ["next_attempt_at"]
    )
    op.create_table(
        "ml_model",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "training_job_id",
            sa.String(36),
            sa.ForeignKey("ml_training_job.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("candidate_ref", sa.JSON(), nullable=False),
        sa.Column("approved_ref", sa.JSON(none_as_null=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ml_model_status", "ml_model", ["status"])
    op.create_table(
        "ml_review",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "model_id",
            sa.String(36),
            sa.ForeignKey("ml_model.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("actor", sa.String(80), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False, unique=True),
        sa.Column("body_hash", sa.String(64), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("expected_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("ml_review")
    op.drop_table("ml_model")
    op.drop_table("ml_training_job")
