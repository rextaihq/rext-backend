"""merge_seed_and_main_heads

Revision ID: 168db6d8bec3
Revises: 26ad95072497, seed006
Create Date: 2025-10-07 14:48:20.395253

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '168db6d8bec3'
down_revision: Union[str, Sequence[str], None] = ('26ad95072497', 'seed006')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
