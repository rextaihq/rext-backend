"""merge google analytics integration and trial heads

Revision ID: c65bd2578278
Revises: 20260622trial, 20260706_ga_integration
Create Date: 2026-07-06 18:49:50.910789

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c65bd2578278'
down_revision: Union[str, Sequence[str], None] = ('20260622trial', '20260706_ga_integration')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
