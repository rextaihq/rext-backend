"""add shopify publish fields to content

Revision ID: cb4411f82bc5
Revises: inv003
Create Date: 2026-03-27 15:22:52.075577

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cb4411f82bc5'
down_revision: Union[str, Sequence[str], None] = 'inv003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('content', sa.Column('shopify_article_id', sa.BigInteger(), nullable=True))
    op.add_column('content', sa.Column('shopify_article_url', sa.Text(), nullable=True))
    op.add_column('content', sa.Column('shopify_published_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('content', 'shopify_published_at')
    op.drop_column('content', 'shopify_article_url')
    op.drop_column('content', 'shopify_article_id')
