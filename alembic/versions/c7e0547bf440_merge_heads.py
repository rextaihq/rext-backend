"""merge heads

Revision ID: c7e0547bf440
Revises: 19120fd8a2ba, c9e6ed3c63fa
Create Date: 2026-01-16 17:50:48.586568

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7e0547bf440'
down_revision: Union[str, Sequence[str], None] = ('19120fd8a2ba', 'c9e6ed3c63fa')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
