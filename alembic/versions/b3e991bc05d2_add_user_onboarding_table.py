"""add_user_onboarding_table

Revision ID: b3e991bc05d2
Revises: a12f791bdf77
Create Date: 2025-10-15 09:42:11.483503

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3e991bc05d2'
down_revision: Union[str, Sequence[str], None] = 'a12f791bdf77'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
