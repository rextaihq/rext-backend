"""merge_invitation_indexes

Revision ID: b374b93eb04b
Revises: admin001, inv002
Create Date: 2025-10-23 17:02:08.635254

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b374b93eb04b'
down_revision: Union[str, Sequence[str], None] = ('admin001', 'inv002')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
