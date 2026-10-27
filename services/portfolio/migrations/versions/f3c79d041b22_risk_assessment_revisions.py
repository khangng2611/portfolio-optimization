"""Append-only risk revisions and confirmation receipts; leave legacy pins intact."""

from alembic import op
import sqlalchemy as sa

revision = "f3c79d041b22"
down_revision = "c2e6b917a034"
branch_labels = None
depends_on = None


def upgrade():
    # No backfill: the current legacy profile does not prove when its assessment
    # occurred, and modifying it would change existing queued command hashes.
    op.create_table(
        "risk_assessment",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "portfolio_id", sa.String(36), sa.ForeignKey("portfolio.id"), nullable=False
        ),
        sa.Column(
            "owner_user_id", sa.String(36), sa.ForeignKey("app_user.id"), nullable=False
        ),
        sa.Column("portfolio_version", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("answers", sa.JSON(), nullable=False),
        sa.Column("constraints", sa.JSON(), nullable=False),
        sa.Column("risk_profile", sa.JSON(), nullable=False),
        sa.Column("mapping_version", sa.String(64), nullable=False),
        sa.Column("policy_version_id", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("body_hash", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("portfolio_id", "portfolio_version"),
        sa.UniqueConstraint("owner_user_id", "portfolio_id", "idempotency_key"),
    )
    op.create_index(
        "ix_risk_assessment_portfolio_id", "risk_assessment", ["portfolio_id"]
    )
    op.create_index(
        "ix_risk_assessment_owner_user_id", "risk_assessment", ["owner_user_id"]
    )


def downgrade():
    op.drop_table("risk_assessment")
