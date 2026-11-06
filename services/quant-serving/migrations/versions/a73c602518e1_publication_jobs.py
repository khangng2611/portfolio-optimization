"""Durable operator publication jobs; no investor mutation surface."""

from alembic import op
import sqlalchemy as sa

revision = "a73c602518e1"
down_revision = "91bc1a8fed92"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "publication_job",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("idempotency_key", sa.String(200), nullable=False, unique=True),
        sa.Column("body_hash", sa.String(64), nullable=False),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("lease_token", sa.String(36), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("safe_error", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_publication_job_status", "publication_job", ["status"])
    op.create_index(
        "ix_publication_job_next_attempt_at", "publication_job", ["next_attempt_at"]
    )


def downgrade():
    op.drop_table("publication_job")
