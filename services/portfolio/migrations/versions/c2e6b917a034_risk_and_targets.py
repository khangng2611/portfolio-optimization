"""Risk onboarding and immutable accepted targets; preserve existing portfolios."""

from alembic import op
import sqlalchemy as sa

revision = "c2e6b917a034"
down_revision = "7f012aa934d1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "portfolio",
        sa.Column("risk_profile", sa.JSON(none_as_null=True), nullable=True),
    )
    op.create_table(
        "accepted_target",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "recommendation_id",
            sa.String(36),
            sa.ForeignKey("recommendation.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "portfolio_id", sa.String(36), sa.ForeignKey("portfolio.id"), nullable=False
        ),
        sa.Column(
            "owner_user_id", sa.String(36), sa.ForeignKey("app_user.id"), nullable=False
        ),
        sa.Column("portfolio_version", sa.Integer(), nullable=False),
        sa.Column("allocation", sa.JSON(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_accepted_target_portfolio_id", "accepted_target", ["portfolio_id"]
    )
    op.create_index(
        "ix_accepted_target_owner_user_id", "accepted_target", ["owner_user_id"]
    )


def downgrade():
    op.drop_table("accepted_target")
    op.drop_column("portfolio", "risk_profile")
