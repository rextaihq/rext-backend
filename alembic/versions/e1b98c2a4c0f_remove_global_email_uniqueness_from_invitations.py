"""remove_global_email_uniqueness_from_invitations

Revision ID: e1b98c2a4c0f
Revises: 4883f6e4c3f5
Create Date: 2025-10-02 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = 'e1b98c2a4c0f'
down_revision: Union[str, Sequence[str], None] = '4883f6e4c3f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Drop the global unique constraint on email column in user_invitations table.
    The composite constraint (email, workspace_id) will remain to ensure per-workspace uniqueness.
    
    Made idempotent: Only drops constraint if it exists.
    """
    # Check if constraint exists before dropping
    conn = op.get_bind()
    inspector = inspect(conn)
    
    # Get all unique constraints for the table
    constraints = inspector.get_unique_constraints('user_invitations')
    constraint_names = [c['name'] for c in constraints]
    
    # Only drop if it exists
    if 'user_invitations_email_key' in constraint_names:
        op.drop_constraint('user_invitations_email_key', 'user_invitations', type_='unique')


def downgrade() -> None:
    """
    Re-add the global unique constraint on email column (for rollback).
    
    Made idempotent: Only creates constraint if it doesn't exist.
    """
    # Check if constraint exists before creating
    conn = op.get_bind()
    inspector = inspect(conn)
    
    # Get all unique constraints for the table
    constraints = inspector.get_unique_constraints('user_invitations')
    constraint_names = [c['name'] for c in constraints]
    
    # Only create if it doesn't exist
    if 'user_invitations_email_key' not in constraint_names:
        op.create_unique_constraint('user_invitations_email_key', 'user_invitations', ['email'])
