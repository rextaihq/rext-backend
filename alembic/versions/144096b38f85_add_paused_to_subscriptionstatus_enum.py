"""Add PAUSED to subscriptionstatus enum

Revision ID: 144096b38f85
Revises: 53acedc53444
Create Date: 2026-03-25 21:31:30.684191

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '144096b38f85'
down_revision: Union[str, Sequence[str], None] = '53acedc53444'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TYPE subscriptionstatus ADD VALUE 'PAUSED'")


def downgrade() -> None:
    """Downgrade schema."""
    pass
