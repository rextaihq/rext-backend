"""add product-led content fields to brand_voice

Revision ID: 20260622plcbrand
Revises: 20260618plans
Create Date: 2026-06-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = '20260622plcbrand'
down_revision: Union[str, Sequence[str], None] = '20260618plans'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('brand_voice', sa.Column('product_name', sa.String(255), nullable=True))
    op.add_column('brand_voice', sa.Column('product_vocabulary', JSONB(), nullable=True))
    op.add_column('brand_voice', sa.Column('forbidden_words', JSONB(), nullable=True))
    op.add_column('brand_voice', sa.Column('brand_ctas', JSONB(), nullable=True))
    op.add_column('brand_voice', sa.Column('key_differentiators', JSONB(), nullable=True))
    op.add_column('brand_voice', sa.Column('tone_examples', JSONB(), nullable=True))
    op.add_column('brand_voice', sa.Column('use_cases', JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column('brand_voice', 'use_cases')
    op.drop_column('brand_voice', 'tone_examples')
    op.drop_column('brand_voice', 'key_differentiators')
    op.drop_column('brand_voice', 'brand_ctas')
    op.drop_column('brand_voice', 'forbidden_words')
    op.drop_column('brand_voice', 'product_vocabulary')
    op.drop_column('brand_voice', 'product_name')
