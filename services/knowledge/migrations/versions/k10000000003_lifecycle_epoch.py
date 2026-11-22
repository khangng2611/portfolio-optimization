"""Fence stale lifecycle intentions across different corpus versions."""

from alembic import op
import sqlalchemy as sa

revision = "k10000000003"
down_revision = "k10000000002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "active_corpus",
        sa.Column("epoch", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade():
    op.drop_column("active_corpus", "epoch")
