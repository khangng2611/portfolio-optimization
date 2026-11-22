"""Nullable explanation sidecar; no changes to existing numerical receipts."""

from alembic import op
import sqlalchemy as sa

revision = "c9222026e001"
down_revision = "b70211d9e301"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("recommendation", sa.Column("explanation_evidence", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("recommendation", "explanation_evidence")
