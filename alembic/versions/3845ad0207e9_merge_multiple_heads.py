"""merge multiple heads

Revision ID: 3845ad0207e9
Revises: 168db6d8bec3, 1f31518bcc11
Create Date: 2025-10-07 14:54:00.651994

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3845ad0207e9'
down_revision: Union[str, Sequence[str], None] = ('168db6d8bec3', '1f31518bcc11')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
