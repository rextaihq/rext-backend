"""remove_notification_archive_columns_and_is_deleted_boolean

Revision ID: 00e8d55969e9
Revises: 572a638e2089
Create Date: 2026-02-23 16:59:58.429792

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '00e8d55969e9'
down_revision: Union[str, Sequence[str], None] = '572a638e2089'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Drop archive-related index
    op.drop_index('ix_notifications_is_archived', table_name='notifications')

    # Drop archive columns
    op.drop_column('notifications', 'is_archived')
    op.drop_column('notifications', 'archived_at')


def downgrade() -> None:
    """Downgrade schema."""
    # Recreate archive columns
    op.add_column('notifications', sa.Column('is_archived', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('notifications', sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_notifications_is_archived', 'notifications', ['is_archived'])
