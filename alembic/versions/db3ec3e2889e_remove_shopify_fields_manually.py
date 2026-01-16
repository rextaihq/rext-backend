"""Remove shopify fields manually

Revision ID: db3ec3e2889e
Revises: ba5e99940e62
Create Date: 2026-01-16 15:48:05.885111

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'db3ec3e2889e'
down_revision: Union[str, Sequence[str], None] = 'ba5e99940e62'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column('connected_sites', 'shop_domain')
    op.drop_column('connected_sites', 'access_token')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('connected_sites', sa.Column('shop_domain', sa.String(length=500), nullable=True))
    op.add_column('connected_sites', sa.Column('access_token', sa.Text(), nullable=True))
