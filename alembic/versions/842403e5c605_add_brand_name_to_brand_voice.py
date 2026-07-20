"""add_brand_name_to_brand_voice

Revision ID: 842403e5c605
Revises: d9d2755b7f91
Create Date: 2026-07-20 00:00:00.000000

Adds an explicit brand_name column to brand_voice. Previously the workspace
name (an internal, user-chosen label with no guaranteed relation to the
actual brand/product) was used as a stand-in for the brand name throughout
content generation, which produced meaningless or wrong brand mentions.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '842403e5c605'
down_revision: Union[str, Sequence[str], None] = 'd9d2755b7f91'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add brand_name column to brand_voice table."""
    op.add_column(
        'brand_voice',
        sa.Column('brand_name', sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    """Remove brand_name column from brand_voice table."""
    op.drop_column('brand_voice', 'brand_name')
