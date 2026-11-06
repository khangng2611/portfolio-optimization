"""Opt-in dialogue consent and durable per-purpose paid invocation budget."""

from alembic import op
import sqlalchemy as sa

revision = "c10000000002"
down_revision = "c10000000001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "conversation",
        sa.Column(
            "llm_consent", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.create_table(
        "provider_invocation",
        sa.Column(
            "job_id", sa.String(36), sa.ForeignKey("chat_job.id"), primary_key=True
        ),
        sa.Column("purpose", sa.String(24), primary_key=True),
        sa.Column("owner_key", sa.String(64), nullable=False),
        sa.Column("output", sa.JSON(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_provider_invocation_owner_key", "provider_invocation", ["owner_key"]
    )
    op.create_index(
        "ix_provider_invocation_created_at", "provider_invocation", ["created_at"]
    )


def downgrade():
    op.drop_table("provider_invocation")
    op.drop_column("conversation", "llm_consent")
