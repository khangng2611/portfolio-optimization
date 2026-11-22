"""Create local accounts and refresh sessions."""

import sqlalchemy as sa
from alembic import op

revision = "a10000000001"
down_revision = None


def upgrade():
    op.create_table(
        "account",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("username", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "refresh_session",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "account_id", sa.String(36), sa.ForeignKey("account.id"), nullable=False
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=False),
    )
    op.create_index("ix_refresh_session_account_id", "refresh_session", ["account_id"])


def downgrade():
    op.drop_table("refresh_session")
    op.drop_table("account")
