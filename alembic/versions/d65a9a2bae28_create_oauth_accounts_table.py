"""create_oauth_accounts_table

Revision ID: d65a9a2bae28
Revises: 054a0d5772f0
Create Date: 2025-10-14 19:59:00.820272

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd65a9a2bae28'
down_revision: Union[str, Sequence[str], None] = '054a0d5772f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create oauth_accounts table for OAuth provider account linking."""
    op.create_table(
        'oauth_accounts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('provider', sa.String(50), nullable=False),
        sa.Column('provider_account_id', sa.String(255), nullable=False),
        sa.Column('provider_account_email', sa.String(255), nullable=True),
        sa.Column('access_token', sa.Text, nullable=True),
        sa.Column('refresh_token', sa.Text, nullable=True),
        sa.Column('token_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('provider_username', sa.String(255), nullable=True),
        sa.Column('provider_profile_url', sa.String(500), nullable=True),
        sa.Column('provider_avatar_url', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, onupdate=sa.text('NOW()')),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),

        # Foreign key to users table
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),

        # Unique constraint: each provider account can only be linked once
        sa.UniqueConstraint('provider', 'provider_account_id', name='uq_provider_account'),
    )

    # Create index on user_id for faster lookups
    op.create_index('ix_oauth_accounts_user_id', 'oauth_accounts', ['user_id'])


def downgrade() -> None:
    """Drop oauth_accounts table."""
    op.drop_index('ix_oauth_accounts_user_id', table_name='oauth_accounts')
    op.drop_table('oauth_accounts')
