"""add_soft_delete_to_workspaces

Revision ID: 922ec422fb19
Revises: 054a0d5772f0
Create Date: 2025-10-15

Adds soft delete capability to workspaces table:
- deleted_at: Timestamp when workspace was soft-deleted (NULL = active)
- deleted_by: User ID who deleted the workspace

This enables 30-day recovery period for deleted workspaces.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '922ec422fb19'
down_revision: Union[str, Sequence[str], None] = '054a0d5772f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add deleted_at column (nullable)
    op.add_column('workspace',
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True)
    )

    # Add deleted_by column (nullable, FK to users)
    op.add_column('workspace',
        sa.Column('deleted_by', postgresql.UUID(as_uuid=True), nullable=True)
    )

    # Add foreign key constraint
    op.create_foreign_key(
        'fk_workspace_deleted_by_users',
        'workspace', 'users',
        ['deleted_by'], ['id'],
        ondelete='SET NULL'
    )

    # Add index on deleted_at for faster queries
    op.create_index(
        'ix_workspace_deleted_at',
        'workspace',
        ['deleted_at']
    )


def downgrade() -> None:
    # Remove index
    op.drop_index('ix_workspace_deleted_at', table_name='workspace')

    # Remove foreign key
    op.drop_constraint('fk_workspace_deleted_by_users', 'workspace', type_='foreignkey')

    # Remove columns
    op.drop_column('workspace', 'deleted_by')
    op.drop_column('workspace', 'deleted_at')
