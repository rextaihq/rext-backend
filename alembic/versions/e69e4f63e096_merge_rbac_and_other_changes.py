"""merge_rbac_and_other_changes

Revision ID: e69e4f63e096
Revises: b2870ecb3e5a, seed009
Create Date: 2025-10-23 23:48:01.248793

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e69e4f63e096'
down_revision: Union[str, Sequence[str], None] = ('b2870ecb3e5a', 'seed009')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
