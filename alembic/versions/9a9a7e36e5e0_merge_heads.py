"""merge heads

Revision ID: 9a9a7e36e5e0
Revises: 5701c27278fe, e2e8b871381e
Create Date: 2026-05-04 16:33:22.794954

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9a9a7e36e5e0'
down_revision: Union[str, Sequence[str], None] = ('5701c27278fe', 'e2e8b871381e')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
