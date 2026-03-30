"""merge heads

Revision ID: 0f311ba88a7d
Revises: 2a18e6a49dbf, 3c187ecaf50f, 3e5436b911ac, cb4411f82bc5
Create Date: 2026-03-30 16:03:56.335095

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0f311ba88a7d'
down_revision: Union[str, Sequence[str], None] = ('2a18e6a49dbf', '3c187ecaf50f', '3e5436b911ac', 'cb4411f82bc5')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
