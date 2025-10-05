"""add_workspace_id_to_topics

Revision ID: h2i3j4k5l6m7
Revises: 433637d4726c
Create Date: 2025-10-03 20:15:00.000000

Adds workspace_id column to topics table and deletes existing topics
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'h2i3j4k5l6m7'
down_revision: Union[str, Sequence[str], None] = '433637d4726c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - add workspace_id to topics table."""

    # First, delete all existing topics since they're not workspace-scoped
    # This is safe as per user confirmation
    op.execute("DELETE FROM topics")

    # Add workspace_id column
    op.add_column(
        'topics',
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False)
    )

    # Add foreign key constraint
    op.create_foreign_key(
        'fk_topics_workspace_id',
        'topics',
        'workspace',
        ['workspace_id'],
        ['id'],
        ondelete='CASCADE'
    )

    # Add index for better query performance
    op.create_index('ix_topics_workspace_id', 'topics', ['workspace_id'])


def downgrade() -> None:
    """Downgrade schema - remove workspace_id from topics table."""

    # Drop index
    op.drop_index('ix_topics_workspace_id', table_name='topics')

    # Drop foreign key constraint
    op.drop_constraint('fk_topics_workspace_id', 'topics', type_='foreignkey')

    # Drop workspace_id column
    op.drop_column('topics', 'workspace_id')
