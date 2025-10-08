"""merge heads

Revision ID: 50f4c516677d
Revises: 3845ad0207e9, ca05d74bd19c
Create Date: 2025-10-08 15:49:55.962184

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '50f4c516677d'
down_revision: Union[str, Sequence[str], None] = ('3845ad0207e9', 'ca05d74bd19c')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
