"""add_is_workspace_role_to_roles

Revision ID: 3dbd19e83367
Revises: 41596bee276b
Create Date: 2025-10-20 12:26:16.085692

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3dbd19e83367'
down_revision: Union[str, Sequence[str], None] = '41596bee276b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add is_workspace_role column to roles table to distinguish platform vs workspace roles."""
    # Add is_workspace_role column (nullable initially)
    op.add_column('roles', sa.Column('is_workspace_role', sa.Boolean(), nullable=True))

    # Set values for workspace roles
    # Workspace roles: workspace_owner, workspace_admin, editor, viewer
    op.execute("""
        UPDATE roles
        SET is_workspace_role = TRUE
        WHERE name IN ('workspace_owner', 'workspace_admin', 'editor', 'viewer')
    """)

    # Set values for platform/global roles
    # Platform roles: super_admin, admin, user
    op.execute("""
        UPDATE roles
        SET is_workspace_role = FALSE
        WHERE name IN ('super_admin', 'admin', 'user')
    """)

    # Set default FALSE for any other roles that might exist (e.g., content_reviewer)
    # This ensures no NULL values remain before making the column non-nullable
    op.execute("""
        UPDATE roles
        SET is_workspace_role = FALSE
        WHERE is_workspace_role IS NULL
    """)

    # Make column non-nullable now that all existing rows have values
    op.alter_column('roles', 'is_workspace_role', nullable=False)


def downgrade() -> None:
    """Remove is_workspace_role column."""
    op.drop_column('roles', 'is_workspace_role')
