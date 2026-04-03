"""merge heads

Revision ID: 7cd201b6324d
Revises: 0f311ba88a7d, 5a23d60422d3
Create Date: 2026-04-03 14:42:34.639368

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7cd201b6324d'
down_revision: Union[str, Sequence[str], None] = ('0f311ba88a7d', '5a23d60422d3')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
