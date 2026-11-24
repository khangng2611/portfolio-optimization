"""Prospective enrollment and internal shadow receipts, independent of proposals."""

from alembic import op
import sqlalchemy as sa

revision = "d099d443a191"
down_revision = "c9222026e001"
branch_labels = None
depends_on = None


def upgrade():
    enrollment = op.create_table(
        "gold_shadow_enrollment",
        sa.Column("study_id", sa.String(64), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.execute(
        enrollment.insert().values(
            study_id="gold-k5-derived-hybrid-shadow-v1", started_at=sa.func.now()
        )
    )
    op.create_table(
        "gold_shadow_decision",
        sa.Column("job_id", sa.String(36), primary_key=True),
        sa.Column("series_id", sa.String(36), nullable=False),
        sa.Column("receipt", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ix_gold_shadow_decision_series_id", "gold_shadow_decision", ["series_id"]
    )


def downgrade():
    op.drop_table("gold_shadow_decision")
    op.drop_table("gold_shadow_enrollment")
