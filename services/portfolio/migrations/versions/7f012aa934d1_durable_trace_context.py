"""Nullable durable trace metadata; existing business rows remain untouched."""

from alembic import op
import sqlalchemy as sa

revision = "7f012aa934d1"
down_revision = "e725cea52e0e"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("job", sa.Column("trace_context", sa.JSON(), nullable=True))
    op.add_column("outbox_event", sa.Column("trace_context", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("outbox_event", "trace_context")
    op.drop_column("job", "trace_context")
