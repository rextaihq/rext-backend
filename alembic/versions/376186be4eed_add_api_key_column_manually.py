"""Add api_key column manually

Revision ID: 376186be4eed
Revises: db3ec3e2889e
Create Date: 2026-01-16 16:50:25.815438

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '376186be4eed'
down_revision: Union[str, Sequence[str], None] = 'db3ec3e2889e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('connected_sites', sa.Column('api_key', sa.Text(), nullable=True, comment='WordPress Rext-AI API Key (Bearer Token)'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('connected_sites', 'api_key')
