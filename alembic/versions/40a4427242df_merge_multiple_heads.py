"""Merge multiple heads

Revision ID: 40a4427242df
Revises: 20260904rbacfloor, 20260907emailresend
Create Date: 2026-09-08 10:03:38.989171

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '40a4427242df'
down_revision: Union[str, Sequence[str], None] = ('20260904rbacfloor', '20260907emailresend')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
