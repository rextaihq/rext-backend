"""add deactivated_at to users table

Revision ID: a1f2e3d4c5b6
Revises: d28b3fe4efb9
Create Date: 2025-10-02 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1f2e3d4c5b6'
down_revision: Union[str, Sequence[str], None] = 'd28b3fe4efb9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add deactivated_at column to users table."""
    op.add_column('users', sa.Column('deactivated_at', sa.TIMESTAMP(), nullable=True))

    # Create index for efficient querying of deactivated accounts
    op.create_index(
        'idx_users_deactivated_at',
        'users',
        ['deactivated_at'],
        unique=False
    )


def downgrade() -> None:
    """Remove deactivated_at column from users table."""
    op.drop_index('idx_users_deactivated_at', table_name='users')
    op.drop_column('users', 'deactivated_at')
