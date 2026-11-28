"""Owner-scoped paper accounts and immutable decision previews."""

from alembic import op
import sqlalchemy as sa

revision = "f1a202611270"
down_revision = "eedf7a9e3721"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "paper_account",
        sa.Column(
            "portfolio_id",
            sa.String(36),
            sa.ForeignKey("portfolio.id"),
            primary_key=True,
        ),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.JSON(), nullable=False),
    )
    op.create_table(
        "paper_decision",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "portfolio_id",
            sa.String(36),
            sa.ForeignKey("paper_account.portfolio_id"),
            nullable=False,
        ),
        sa.Column(
            "target_id",
            sa.String(36),
            sa.ForeignKey("accepted_target.id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("action", sa.String(8)),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("quote", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ix_paper_decision_portfolio_id", "paper_decision", ["portfolio_id"]
    )


def downgrade():
    op.drop_table("paper_decision")
    op.drop_table("paper_account")
