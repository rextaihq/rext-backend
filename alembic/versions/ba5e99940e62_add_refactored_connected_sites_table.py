"""Add refactored connected sites table

Revision ID: ba5e99940e62
Revises: f87a4a7e84e5
Create Date: 2026-01-16 15:09:03.646824

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'ba5e99940e62'
down_revision: Union[str, Sequence[str], None] = 'f87a4a7e84e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'connected_sites',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('integration_type', sa.String(length=50), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('site_url', sa.String(length=500), nullable=True, comment='WordPress site URL'),
        sa.Column('username', sa.String(length=255), nullable=True, comment='WordPress username'),
        sa.Column('app_password', sa.Text(), nullable=True, comment='WordPress application password'),
        sa.Column('shop_domain', sa.String(length=500), nullable=True, comment='Shopify shop domain'),
        sa.Column('access_token', sa.Text(), nullable=True, comment='Shopify access token'),
        sa.Column('config_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Additional integration configuration and settings'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspace.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('id')
    )
    op.create_index(op.f('ix_connected_sites_integration_type'), 'connected_sites', ['integration_type'], unique=False)
    op.create_index(op.f('ix_connected_sites_workspace_id'), 'connected_sites', ['workspace_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_connected_sites_workspace_id'), table_name='connected_sites')
    op.drop_index(op.f('ix_connected_sites_integration_type'), table_name='connected_sites')
    op.drop_table('connected_sites')
