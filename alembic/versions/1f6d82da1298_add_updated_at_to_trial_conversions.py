"""add updated_at to trial_conversions

Revision ID: 1f6d82da1298
Revises: b93247c8350c
Create Date: 2026-02-16 16:00:48.617767

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1f6d82da1298'
down_revision: Union[str, Sequence[str], None] = 'b93247c8350c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('trial_conversions', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('trial_conversions', 'updated_at')
