"""merge_heads_sessions_and_super_admin

Revision ID: 23f9c33e0f62
Revises: 23b403658069, 6a35a3742a53
Create Date: 2025-10-14 17:56:17.787821

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '23f9c33e0f62'
down_revision: Union[str, Sequence[str], None] = ('23b403658069', '6a35a3742a53')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
