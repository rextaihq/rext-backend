"""merge_device_fingerprint_and_publish_retry_heads

Revision ID: 7d01bdf5009c
Revises: 6594f0648a61, d4e5f6a7b8c9
Create Date: 2026-07-28 19:26:56.910325

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7d01bdf5009c'
down_revision: Union[str, Sequence[str], None] = ('6594f0648a61', 'd4e5f6a7b8c9')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
