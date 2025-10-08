"""Merge seed and main heads

Revision ID: 1f31518bcc11
Revises: 26ad95072497, seed006
Create Date: 2025-10-07 14:22:53.972933

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1f31518bcc11'
down_revision: Union[str, Sequence[str], None] = ('26ad95072497', 'seed006')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
