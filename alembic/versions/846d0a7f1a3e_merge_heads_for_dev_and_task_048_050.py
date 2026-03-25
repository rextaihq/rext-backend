"""merge heads for dev and task-048-050

Revision ID: 846d0a7f1a3e
Revises: 9632397df534, dd1491b13c9a
Create Date: 2026-02-10 20:40:06.748487

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '846d0a7f1a3e'
down_revision: Union[str, Sequence[str], None] = ('9632397df534', 'dd1491b13c9a')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
