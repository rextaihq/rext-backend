"""add site_compliance to brand_voice

Revision ID: f0c503357612
Revises: 21a1eeaa7527
Create Date: 2026-07-31 14:22:36.147088

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f0c503357612'
down_revision: Union[str, Sequence[str], None] = '21a1eeaa7527'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
