"""fix_content_table_missing_indexes

Revision ID: a1b2c3d4e5f6
Revises: 9c89a3cc8f58
Create Date: 2025-10-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '9c89a3cc8f58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add missing indexes on content table foreign key columns."""
    # Add index for assigned_to_user_id (currently missing)
    op.create_index('ix_content_assigned_to_user_id', 'content', ['assigned_to_user_id'])

    # Add index for author_id (currently missing)
    op.create_index('ix_content_author_id', 'content', ['author_id'])


def downgrade() -> None:
    """Remove indexes on content table foreign key columns."""
    # Drop indexes
    op.drop_index('ix_content_author_id', table_name='content')
    op.drop_index('ix_content_assigned_to_user_id', table_name='content')
