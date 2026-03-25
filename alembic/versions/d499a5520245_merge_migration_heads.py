"""merge migration heads

Revision ID: d499a5520245
Revises: 4ad3dc4bea19, ae5e9d012125
Create Date: 2026-01-29 16:01:34.333919

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd499a5520245'
down_revision: Union[str, Sequence[str], None] = ('4ad3dc4bea19', 'ae5e9d012125')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
