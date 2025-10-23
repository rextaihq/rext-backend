"""add_missing_admin_invitation_index

Revision ID: da4bb03ed311
Revises: b374b93eb04b
Create Date: 2025-10-23 17:28:19.916333

Description: Add the missing composite index on platform_admin_invitations
that may not have been created if inv002 ran before admin001.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'da4bb03ed311'
down_revision: Union[str, Sequence[str], None] = 'b374b93eb04b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add missing composite index on platform_admin_invitations."""
    # This index may have been skipped if inv002 ran before admin001
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_admin_invitations_email_status_pending
        ON platform_admin_invitations(email, status)
        WHERE status = 'pending'
    """)


def downgrade() -> None:
    """Remove the composite index."""
    op.execute("DROP INDEX IF EXISTS idx_admin_invitations_email_status_pending")
