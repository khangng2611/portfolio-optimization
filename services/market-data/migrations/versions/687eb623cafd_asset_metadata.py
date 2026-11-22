"""Market-owned reference metadata; existing prices and asset identities are preserved."""

from alembic import op
import sqlalchemy as sa

revision = '687eb623cafd'
down_revision = 'd2a71c630b91'
branch_labels = None
depends_on = None


def upgrade():
    for column in (
        sa.Column('display_name', sa.String(500), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('metadata_source', sa.String(100), nullable=True),
        sa.Column('metadata_source_symbol', sa.String(100), nullable=True),
        sa.Column('metadata_fetched_at', sa.DateTime(timezone=True), nullable=True),
    ):
        op.add_column('asset', column)


def downgrade():
    for name in ('metadata_fetched_at', 'metadata_source_symbol', 'metadata_source', 'description', 'display_name'):
        op.drop_column('asset', name)
