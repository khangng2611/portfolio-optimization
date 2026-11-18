"""Per-approval indexing budget, without changing already indexed corpus versions."""

from alembic import op
import sqlalchemy as sa

revision = "k10000000002"
down_revision = "k10000000001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "embedding_invocation",
        sa.Column("budget_id", sa.String(128), nullable=False, server_default="legacy"),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "REVOKE UPDATE, DELETE ON document_chunk, corpus_document FROM knowledge_runtime"
        )


def downgrade():
    op.drop_column("embedding_invocation", "budget_id")
