"""merge heads

Revision ID: 41a6d104b66f
Revises: 4a1c6a76f9b8, 728fa56dd145
Create Date: 2026-02-11 15:36:12.444313

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '41a6d104b66f'
down_revision: Union[str, Sequence[str], None] = ('4a1c6a76f9b8', '728fa56dd145')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
