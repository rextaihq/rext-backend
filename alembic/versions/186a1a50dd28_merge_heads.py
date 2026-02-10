"""merge_heads

Revision ID: 186a1a50dd28
Revises: 012aa355603f, 41401d60f98f
Create Date: 2026-02-10 13:06:07.465219

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '186a1a50dd28'
down_revision: Union[str, Sequence[str], None] = ('012aa355603f', '41401d60f98f')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
