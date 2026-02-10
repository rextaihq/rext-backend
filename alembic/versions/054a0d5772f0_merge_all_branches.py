"""merge_all_branches

Revision ID: 054a0d5772f0
Revises: b2c3d4e5f6g7, 23f9c33e0f62
Create Date: 2025-10-14 18:12:30.309779

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '054a0d5772f0'
down_revision: Union[str, Sequence[str], None] = ('b2c3d4e5f6g7', '23f9c33e0f62')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
