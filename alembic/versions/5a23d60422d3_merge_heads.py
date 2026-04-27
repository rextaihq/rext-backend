"""merge heads

Revision ID: 5a23d60422d3
Revises: inv003, update_ls_ids_2026
Create Date: 2026-04-02 21:49:34.033612

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5a23d60422d3'
down_revision: Union[str, Sequence[str], None] = ('inv003', 'update_ls_ids_2026')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
