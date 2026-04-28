"""remove secondary_pillars from brand_voice

Revision ID: e2e8b871381e
Revises: 20260317_pillars
Create Date: 2026-03-17 20:42:19.403237

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e2e8b871381e'
down_revision: Union[str, Sequence[str], None] = '20260317_pillars'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── brand_voice ──────────────────────────────────────────────────────────
    op.drop_column('brand_voice', 'secondary_pillars')


def downgrade() -> None:
    # ── brand_voice ──────────────────────────────────────────────────────────
    op.add_column(
        'brand_voice',
        sa.Column('secondary_pillars', postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )
