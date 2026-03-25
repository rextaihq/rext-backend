"""merge all heads

Revision ID: 1ff9280add01
Revises: 2a18e6a49dbf, 3c187ecaf50f, 3e5436b911ac
Create Date: 2026-03-25 20:59:34.100983

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1ff9280add01'
down_revision: Union[str, Sequence[str], None] = ('2a18e6a49dbf', '3c187ecaf50f', '3e5436b911ac')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
