"""Merge multiple heads

Revision ID: 263449deebd4
Revises: 00e8d55969e9, 035abe7fd909, 36d18c584625, c3d4e5f6a7b8, dd7ac82b3cb0
Create Date: 2026-02-24 13:39:20.206805

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '263449deebd4'
down_revision: Union[str, Sequence[str], None] = ('00e8d55969e9', '035abe7fd909', '36d18c584625', 'c3d4e5f6a7b8', 'dd7ac82b3cb0')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
