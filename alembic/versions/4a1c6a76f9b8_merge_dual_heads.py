"""merge dual heads

Revision ID: 4a1c6a76f9b8
Revises: 846d0a7f1a3e, a77fcf3d85c5
Create Date: 2026-02-11 13:02:08.652201

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4a1c6a76f9b8'
down_revision: Union[str, Sequence[str], None] = ('846d0a7f1a3e', 'a77fcf3d85c5')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
