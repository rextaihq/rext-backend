"""merge_schema_and_seeds

Revision ID: 36ef85f33af2
Revises: seed002, g1h2i3j4k5l6
Create Date: 2025-10-03 12:31:13.685181

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '36ef85f33af2'
down_revision: Union[str, Sequence[str], None] = ('seed002', 'g1h2i3j4k5l6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
