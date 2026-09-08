"""merge_all_heads

Revision ID: 6f99c7701ed0
Revises: 20260904rbacfloor, 20260907emailresend, rr20260903
Create Date: 2026-09-08 12:03:05.773846

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6f99c7701ed0'
down_revision: Union[str, Sequence[str], None] = ('20260904rbacfloor', '20260907emailresend', 'rr20260903')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
