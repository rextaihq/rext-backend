"""merge_shopify_and_internal_links

Revision ID: b6dca73a7412
Revises: 5f6b92f0a1c3, d1e70992e366
Create Date: 2026-05-25 11:12:43.725260

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b6dca73a7412'
down_revision: Union[str, Sequence[str], None] = ('5f6b92f0a1c3', 'd1e70992e366')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
