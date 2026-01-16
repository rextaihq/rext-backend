"""Add api_endpoint manually

Revision ID: 19120fd8a2ba
Revises: 376186be4eed
Create Date: 2026-01-16 17:08:21.276257

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '19120fd8a2ba'
down_revision: Union[str, Sequence[str], None] = '376186be4eed'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('connected_sites', sa.Column('api_endpoint', sa.String(length=500), nullable=True, comment='Rext-AI Plugin Base Endpoint'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('connected_sites', 'api_endpoint')
