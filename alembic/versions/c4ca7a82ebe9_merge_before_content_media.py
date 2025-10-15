"""merge_before_content_media

Revision ID: c4ca7a82ebe9
Revises: 922ec422fb19, d65a9a2bae28
Create Date: 2025-10-15 08:28:31.675205

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4ca7a82ebe9'
down_revision: Union[str, Sequence[str], None] = ('922ec422fb19', 'd65a9a2bae28')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
