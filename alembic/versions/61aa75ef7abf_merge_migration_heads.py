"""merge migration heads

Revision ID: 61aa75ef7abf
Revises: c7a4e9b2d8f1, 6594f0648a61, a1e2c3d4b5f6
Create Date: 2026-07-29 10:24:07.474223

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '61aa75ef7abf'
down_revision: Union[str, Sequence[str], None] = ('c7a4e9b2d8f1', '6594f0648a61', 'a1e2c3d4b5f6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
