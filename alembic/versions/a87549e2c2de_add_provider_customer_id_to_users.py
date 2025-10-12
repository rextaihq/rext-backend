"""add_provider_customer_id_to_users

Revision ID: a87549e2c2de
Revises: 2f08b3178c5d
Create Date: 2025-10-12 21:07:55.086632

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a87549e2c2de'
down_revision: Union[str, Sequence[str], None] = '2f08b3178c5d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add provider_customer_id to users table."""
    op.add_column(
        'users',
        sa.Column('provider_customer_id', sa.String(length=255), nullable=True)
    )
    op.create_index(
        'ix_users_provider_customer_id',
        'users',
        ['provider_customer_id'],
        unique=True
    )


def downgrade() -> None:
    """Remove provider_customer_id from users table."""
    op.drop_index('ix_users_provider_customer_id', table_name='users')
    op.drop_column('users', 'provider_customer_id')
