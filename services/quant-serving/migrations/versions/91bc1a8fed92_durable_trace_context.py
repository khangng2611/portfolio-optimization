"""Nullable durable trace metadata; existing business rows remain untouched."""

from alembic import op
import sqlalchemy as sa

revision = "91bc1a8fed92"
down_revision = "61ece06160ae"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("numerical_run", sa.Column("trace_context", sa.JSON(), nullable=True))
    op.add_column("outbox_event", sa.Column("trace_context", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("outbox_event", "trace_context")
    op.drop_column("numerical_run", "trace_context")
