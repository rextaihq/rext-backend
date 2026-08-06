"""add competitor_analysis to brand_voice

Revision ID: 20260806_compana
Revises: f0c503357612
Create Date: 2026-08-06

Adds brand_voice.competitor_analysis (JSONB, nullable) — stores SERP-verified,
scored/tiered competitor discovery results. Separate from the existing
brand_voice.competitors column (a manually user-edited list of brand names),
which is left untouched.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20260806_compana'
down_revision: Union[str, Sequence[str], None] = 'f0c503357612'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns_bv = [c['name'] for c in inspector.get_columns('brand_voice')]
    if 'competitor_analysis' not in columns_bv:
        op.add_column(
            'brand_voice',
            sa.Column('competitor_analysis', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('brand_voice', 'competitor_analysis')
