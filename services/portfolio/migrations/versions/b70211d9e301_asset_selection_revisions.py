"""Add append-only asset selections; preserve all legacy JSON and pointers."""
from alembic import op
import sqlalchemy as sa

revision = 'b70211d9e301'
down_revision = 'a410c7e9d201'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('portfolio_asset_selection',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('portfolio_id', sa.String(36), sa.ForeignKey('portfolio.id'), nullable=False),
        sa.Column('owner_user_id', sa.String(36), sa.ForeignKey('app_user.id'), nullable=False),
        sa.Column('portfolio_version', sa.Integer(), nullable=False),
        sa.Column('candidate_asset_ids', sa.JSON(), nullable=False),
        sa.Column('candidate_hash', sa.String(64), nullable=False),
        sa.Column('selection_policy_id', sa.String(64), nullable=False),
        sa.Column('risk_policy_id', sa.String(64), nullable=False),
        sa.Column('actor', sa.String(64), nullable=False),
        sa.Column('idempotency_key', sa.String(128), nullable=True),
        sa.Column('body_hash', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('portfolio_id', 'portfolio_version'),
        sa.UniqueConstraint('portfolio_id', 'id'),
        sa.UniqueConstraint('owner_user_id', 'portfolio_id', 'idempotency_key'),
    )
    op.create_index('ix_portfolio_asset_selection_portfolio_id', 'portfolio_asset_selection', ['portfolio_id'])
    op.create_index('ix_portfolio_asset_selection_owner_user_id', 'portfolio_asset_selection', ['owner_user_id'])
    with op.batch_alter_table('portfolio') as batch:
        batch.add_column(sa.Column('asset_selection_revision_id', sa.String(36), nullable=True))
        batch.create_foreign_key('fk_portfolio_owned_asset_selection', 'portfolio_asset_selection',
                                 ['id', 'asset_selection_revision_id'], ['portfolio_id', 'id'])


def downgrade():
    with op.batch_alter_table('portfolio') as batch:
        batch.drop_constraint('fk_portfolio_owned_asset_selection', type_='foreignkey')
        batch.drop_column('asset_selection_revision_id')
    op.drop_table('portfolio_asset_selection')
