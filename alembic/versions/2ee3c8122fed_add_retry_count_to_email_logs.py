"""add_retry_count_to_email_logs

Revision ID: 2ee3c8122fed
Revises: b3e991bc05d2
Create Date: 2025-10-15 22:42:23.064807

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2ee3c8122fed'
down_revision: Union[str, Sequence[str], None] = 'b3e991bc05d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add retry_count column to email_logs table."""
    # Add retry_count column with default value 0
    op.add_column('email_logs', sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    """Remove retry_count column from email_logs table."""
    op.drop_column('email_logs', 'retry_count')
