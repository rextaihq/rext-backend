"""merge alembic heads

Revision ID: c83afba99b68
Revises: 1ce340a722d6, f23456789abc
Create Date: 2026-02-09 15:40:30.565911

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c83afba99b68'
down_revision: Union[str, Sequence[str], None] = ('1ce340a722d6', 'f23456789abc')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
