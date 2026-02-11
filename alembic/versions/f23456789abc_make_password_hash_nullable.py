"""make password_hash nullable for oauth users

Revision ID: f23456789abc
Revises: d499a5520245
Create Date: 2026-02-04 20:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f23456789abc'
down_revision: Union[str, Sequence[str], None] = 'd499a5520245'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Alter column to be nullable
    op.alter_column('users', 'password_hash',
               existing_type=sa.String(length=255),
               nullable=True)
    
    # Update existing OAuth-only users who have the placeholder
    op.execute("UPDATE users SET password_hash = NULL WHERE password_hash = 'oauth_no_password'")


def downgrade() -> None:
    # Set a placeholder back for any NULL password_hash before making non-nullable
    op.execute("UPDATE users SET password_hash = 'oauth_no_password' WHERE password_hash IS NULL")
    
    # Revert column to be non-nullable
    op.alter_column('users', 'password_hash',
               existing_type=sa.String(length=255),
               nullable=False)
