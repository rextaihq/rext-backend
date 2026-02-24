"""admin_invitation_pending_unique

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-02-24 13:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop existing global unique constraint
    op.drop_constraint(
        "uq_admin_invitation_email",
        "platform_admin_invitations",
        type_="unique",
    )

    # Drop existing non-unique index if it exists (from da4bb03ed311)
    op.execute("DROP INDEX IF EXISTS idx_admin_invitations_email_status_pending")

    # Create new partial unique index for pending invitations
    op.execute(
        """
        CREATE UNIQUE INDEX uq_admin_invitation_email_pending
        ON platform_admin_invitations (email)
        WHERE status = 'pending'
        """
    )


def downgrade() -> None:
    # Drop partial unique index
    op.execute("DROP INDEX IF EXISTS uq_admin_invitation_email_pending")

    # Re-create global unique constraint
    op.create_unique_constraint(
        "uq_admin_invitation_email",
        "platform_admin_invitations",
        ["email"],
    )

    # Re-create original non-unique index
    op.execute(
        """
        CREATE INDEX idx_admin_invitations_email_status_pending
        ON platform_admin_invitations (email, status)
        WHERE status = 'pending'
        """
    )
