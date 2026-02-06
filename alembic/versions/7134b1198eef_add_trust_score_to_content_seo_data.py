"""add trust_score to content_seo_data

Revision ID: 7134b1198eef
Revises: 625b40a3c6ba
Create Date: 2026-02-02 20:13:59.596250

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7134b1198eef'
down_revision: Union[str, Sequence[str], None] = '625b40a3c6ba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
