"""Short-lived owner-validated Chat delegation; additive, no legacy changes."""

from alembic import op
import sqlalchemy as sa

revision = "a410c7e9d201"
down_revision = "f3c79d041b22"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "delegation_grant",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_user_id", sa.String(36), sa.ForeignKey("app_user.id"), nullable=False
        ),
        sa.Column("actor", sa.String(64), nullable=False),
        sa.Column("conversation_id", sa.String(36), nullable=False),
        sa.Column("chat_job_id", sa.String(36), nullable=False),
        sa.Column("authorization_id", sa.String(36), nullable=False),
        sa.Column("portfolio_id", sa.String(36), nullable=True),
        sa.Column("tools", sa.JSON(), nullable=False),
        sa.Column("body_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("owner_user_id", "chat_job_id", "authorization_id"),
    )
    op.create_index(
        "ix_delegation_grant_owner_user_id", "delegation_grant", ["owner_user_id"]
    )


def downgrade():
    op.drop_table("delegation_grant")
