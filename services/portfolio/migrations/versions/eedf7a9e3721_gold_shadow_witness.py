"""A second transaction attests the original decision was already durable."""

from alembic import op
import sqlalchemy as sa

revision = "eedf7a9e3721"
down_revision = "d099d443a191"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "gold_shadow_witness",
        sa.Column(
            "job_id",
            sa.String(36),
            sa.ForeignKey("gold_shadow_decision.job_id"),
            primary_key=True,
        ),
        sa.Column("witnessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("receipt_sha256", sa.String(64), nullable=False),
    )


def downgrade():
    op.drop_table("gold_shadow_witness")
