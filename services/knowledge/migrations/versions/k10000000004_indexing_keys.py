"""Record every acknowledged indexing key, including content-deduped aliases."""

from alembic import op
import sqlalchemy as sa

revision = "k10000000004"
down_revision = "k10000000003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "indexing_key",
        sa.Column("actor", sa.String(64), primary_key=True),
        sa.Column("idempotency_key", sa.String(128), primary_key=True),
        sa.Column("body_hash", sa.String(64), nullable=False),
        sa.Column(
            "job_id", sa.String(36), sa.ForeignKey("indexing_job.id"), nullable=False
        ),
    )
    op.execute(
        "INSERT INTO indexing_key(actor,idempotency_key,body_hash,job_id) SELECT actor,idempotency_key,body_hash,id FROM indexing_job"
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("REVOKE UPDATE, DELETE ON indexing_key FROM knowledge_runtime")


def downgrade():
    op.drop_table("indexing_key")
