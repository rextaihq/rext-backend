"""update_workspace_roles_to_non_system

Revision ID: b2870ecb3e5a
Revises: da4bb03ed311
Create Date: 2025-10-23 17:45:05.607988

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2870ecb3e5a'
down_revision: Union[str, Sequence[str], None] = 'da4bb03ed311'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Update workspace-specific roles to be non-system roles.

    This allows these roles to appear in workspace invitation dialogs.
    System roles (super_admin, admin, user) remain as system roles.
    """
    # Update workspace-specific roles to is_system_role = False
    op.execute("""
        UPDATE roles
        SET is_system_role = FALSE
        WHERE name IN ('workspace_owner', 'workspace_admin', 'editor', 'viewer')
    """)


def downgrade() -> None:
    """Revert workspace roles back to system roles."""
    op.execute("""
        UPDATE roles
        SET is_system_role = TRUE
        WHERE name IN ('workspace_owner', 'workspace_admin', 'editor', 'viewer')
    """)
