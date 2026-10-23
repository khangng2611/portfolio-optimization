"""Nullable durable trace metadata; existing business rows remain untouched."""

from alembic import op
import sqlalchemy as sa

revision = "30cfeec6786b"
down_revision = "10f6adda892e"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ingestion_job", sa.Column("trace_context", sa.JSON(), nullable=True))
    op.add_column("outbox_event", sa.Column("trace_context", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("outbox_event", "trace_context")
    op.drop_column("ingestion_job", "trace_context")
