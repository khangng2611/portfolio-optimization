"""Chat-owned conversations, turns, leased jobs, replay events and tool audit."""

from alembic import op
import sqlalchemy as sa

revision = "c10000000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "conversation",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_key", sa.String(64), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("portfolio_id", sa.String(36), nullable=True),
        sa.Column("active_job_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_conversation_owner_key", "conversation", ["owner_key"])
    op.create_table(
        "message",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("conversation.id"),
            nullable=False,
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("client_message_id", sa.String(128), nullable=True),
        sa.Column("body_hash", sa.String(64), nullable=True),
        sa.Column("structured", sa.JSON(), nullable=True),
        sa.Column("consumed_by", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("conversation_id", "client_message_id"),
    )
    op.create_index("ix_message_conversation_id", "message", ["conversation_id"])
    op.create_table(
        "chat_job",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("conversation.id"),
            nullable=False,
        ),
        sa.Column("owner_key", sa.String(64), nullable=False),
        sa.Column(
            "message_id", sa.String(36), sa.ForeignKey("message.id"), nullable=False
        ),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("reauthorization_id", sa.String(36), nullable=True),
        sa.Column("grant_id", sa.String(36), nullable=False),
        sa.Column("grant_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("provider_calls", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("lease_token", sa.String(36), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dependency_id", sa.String(36), nullable=True),
        sa.Column("recommendation_id", sa.String(36), nullable=True),
        sa.Column("result_message_id", sa.String(36), nullable=True),
        sa.Column("error", sa.String(64), nullable=True),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("message_id"),
    )
    op.create_index("ix_chat_job_conversation_id", "chat_job", ["conversation_id"])
    op.create_index("ix_chat_job_owner_key", "chat_job", ["owner_key"])
    op.create_index("ix_chat_job_claim", "chat_job", ["status", "next_attempt_at"])
    op.create_table(
        "job_event",
        sa.Column(
            "job_id", sa.String(36), sa.ForeignKey("chat_job.id"), primary_key=True
        ),
        sa.Column("sequence", sa.Integer(), primary_key=True),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_job_event_created_at", "job_event", ["created_at"])
    op.create_table(
        "tool_call",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "job_id", sa.String(36), sa.ForeignKey("chat_job.id"), nullable=False
        ),
        sa.Column("tool", sa.String(64), nullable=False),
        sa.Column("arguments_hash", sa.String(64), nullable=False),
        sa.Column("result_hash", sa.String(64), nullable=True),
        sa.Column("result_reference", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tool_call_job_id", "tool_call", ["job_id"])


def downgrade():
    for table in ("tool_call", "job_event", "chat_job", "message", "conversation"):
        op.drop_table(table)
