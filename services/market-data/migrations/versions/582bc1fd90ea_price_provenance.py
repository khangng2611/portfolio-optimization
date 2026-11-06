"""Preserve source attestation without relabeling historical imported data."""

from alembic import op
import sqlalchemy as sa

revision = "582bc1fd90ea"
down_revision = "30cfeec6786b"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "price_revision",
        sa.Column(
            "data_origin", sa.String(16), nullable=False, server_default="unverified"
        ),
    )
    op.add_column(
        "price_revision",
        sa.Column(
            "price_basis", sa.String(32), nullable=False, server_default="unverified"
        ),
    )


def downgrade():
    op.drop_column("price_revision", "price_basis")
    op.drop_column("price_revision", "data_origin")
