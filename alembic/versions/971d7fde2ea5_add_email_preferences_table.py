"""add_email_preferences_table

Revision ID: 971d7fde2ea5
Revises: 907fbc89eca2
Create Date: 2025-10-12 16:19:06.185158

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '971d7fde2ea5'
down_revision: Union[str, Sequence[str], None] = '907fbc89eca2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'email_preferences',
        sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('user_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('workspace_invitation', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('invitation_accepted', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('role_changed', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('member_removed', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('marketing', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('unsubscribe_token', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('user_id'),
        sa.UniqueConstraint('unsubscribe_token')
    )
    op.create_index('ix_email_preferences_user_id', 'email_preferences', ['user_id'])
    op.create_index('ix_email_preferences_unsubscribe_token', 'email_preferences', ['unsubscribe_token'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_email_preferences_unsubscribe_token', 'email_preferences')
    op.drop_index('ix_email_preferences_user_id', 'email_preferences')
    op.drop_table('email_preferences')
