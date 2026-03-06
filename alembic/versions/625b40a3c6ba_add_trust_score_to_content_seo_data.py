"""add trust_score to content_seo_data

Revision ID: 625b40a3c6ba
Revises: d499a5520245
Create Date: 2026-02-02 20:11:54.085124

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '625b40a3c6ba'
down_revision: Union[str, Sequence[str], None] = 'd499a5520245'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('content_seo_data', sa.Column('trust_score', sa.Float(), nullable=True, comment='Trust score of the content'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('content_seo_data', 'trust_score')
