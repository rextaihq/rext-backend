"""add_registration_device_fingerprint_to_users

Revision ID: 6594f0648a61
Revises: 842403e5c605
Create Date: 2026-07-28 00:00:00.000000

Persists the device fingerprint (hash of IP + User-Agent, see
get_device_fingerprint in src/api/middleware/rate_limiter.py) captured at
registration time, so the number of non-paid accounts tied to a device can be
counted permanently rather than via a time-windowed rate limiter.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6594f0648a61'
down_revision: Union[str, Sequence[str], None] = '842403e5c605'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add registration_device_fingerprint to users table."""
    op.add_column(
        'users',
        sa.Column('registration_device_fingerprint', sa.String(length=16), nullable=True)
    )
    op.create_index(
        'ix_users_registration_device_fingerprint',
        'users',
        ['registration_device_fingerprint']
    )


def downgrade() -> None:
    """Remove registration_device_fingerprint from users table."""
    op.drop_index('ix_users_registration_device_fingerprint', table_name='users')
    op.drop_column('users', 'registration_device_fingerprint')
