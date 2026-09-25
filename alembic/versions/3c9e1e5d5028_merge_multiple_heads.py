"""Merge multiple heads

Revision ID: 3c9e1e5d5028
Revises: 20260924dashact, 20260925eddel
Create Date: 2026-09-25 15:20:06.258778

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3c9e1e5d5028'
down_revision: Union[str, Sequence[str], None] = ('20260924dashact', '20260925eddel')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
