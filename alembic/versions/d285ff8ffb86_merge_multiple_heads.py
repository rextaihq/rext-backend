"""merge multiple heads

Revision ID: d285ff8ffb86
Revises: 1ce340a722d6, standardize_timestamps
Create Date: 2026-02-09 21:15:28.317970

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd285ff8ffb86'
down_revision: Union[str, Sequence[str], None] = ('1ce340a722d6', 'standardize_timestamps')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
