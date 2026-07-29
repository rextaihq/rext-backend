"""merge heads f1bcd5754b07 and 7c044255e03f

Revision ID: a584ac4e355c
Revises: f1bcd5754b07, 7c044255e03f
Create Date: 2026-07-29 15:27:37.143066

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a584ac4e355c'
down_revision: Union[str, Sequence[str], None] = ('f1bcd5754b07', '7c044255e03f')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
