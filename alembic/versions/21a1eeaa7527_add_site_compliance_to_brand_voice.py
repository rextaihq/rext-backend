"""add site_compliance to brand_voice

Revision ID: 21a1eeaa7527
Revises: a584ac4e355c
Create Date: 2026-07-31 13:31:30.859271

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '21a1eeaa7527'
down_revision: Union[str, Sequence[str], None] = 'a584ac4e355c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column(
        'brand_voice',
        sa.Column('site_compliance', postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )

def downgrade() -> None:
    op.drop_column('brand_voice', 'site_compliance')
