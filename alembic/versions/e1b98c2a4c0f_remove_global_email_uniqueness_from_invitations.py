"""remove_global_email_uniqueness_from_invitations

Revision ID: e1b98c2a4c0f
Revises: 4883f6e4c3f5
Create Date: 2025-10-02 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e1b98c2a4c0f'
down_revision: Union[str, Sequence[str], None] = '4883f6e4c3f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Drop the global unique constraint on email column in user_invitations table.
    The composite constraint (email, workspace_id) will remain to ensure per-workspace uniqueness.
    """
    # Drop the unique constraint on email column only
    # Note: The constraint name might vary depending on the database
    # PostgreSQL typically names it as '<table>_<column>_key'
    op.drop_constraint('user_invitations_email_key', 'user_invitations', type_='unique')


def downgrade() -> None:
    """
    Re-add the global unique constraint on email column (for rollback).
    """
    op.create_unique_constraint('user_invitations_email_key', 'user_invitations', ['email'])
