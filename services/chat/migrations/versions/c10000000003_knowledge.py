"""Additive consent v2, retrieval checkpoint and immutable Knowledge evidence."""

from alembic import op
import sqlalchemy as sa

revision = "c10000000003"
down_revision = "c10000000002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "provider_invocation", sa.Column("budget_id", sa.String(128), nullable=True)
    )
    op.add_column(
        "provider_invocation",
        sa.Column("reserved_usd", sa.String(32), nullable=False, server_default="0"),
    )
    op.add_column(
        "conversation",
        sa.Column("consent_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "chat_job", sa.Column("knowledge_checkpoint", sa.JSON(), nullable=True)
    )
    op.create_table(
        "knowledge_evidence",
        sa.Column(
            "job_id", sa.String(36), sa.ForeignKey("chat_job.id"), primary_key=True
        ),
        sa.Column("evidence_hash", sa.String(64), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("REVOKE UPDATE, DELETE ON knowledge_evidence FROM chat_runtime")


def downgrade():
    op.drop_column("provider_invocation", "reserved_usd")
    op.drop_column("provider_invocation", "budget_id")
    op.drop_table("knowledge_evidence")
    op.drop_column("chat_job", "knowledge_checkpoint")
    op.drop_column("conversation", "consent_version")
