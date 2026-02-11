"""merge_heads_250209

Revision ID: 2903f7581f46
Revises: 1ce340a722d6, f23456789abc
Create Date: 2026-02-09 17:56:06.013428

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2903f7581f46'
down_revision: Union[str, Sequence[str], None] = ('1ce340a722d6', 'f23456789abc')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
