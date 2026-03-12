"""Merge migration heads

Revision ID: 9632397df534
Revises: 428689ad2535, 86049af81ad3
Create Date: 2026-02-10 20:07:28.029234

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9632397df534'
down_revision: Union[str, Sequence[str], None] = ('428689ad2535', '86049af81ad3')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
