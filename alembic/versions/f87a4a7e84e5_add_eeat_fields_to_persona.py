"""add_eeat_fields_to_persona

Revision ID: f87a4a7e84e5
Revises: c17f9a62e019
Create Date: 2026-01-16 00:37:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f87a4a7e84e5'
down_revision: Union[str, Sequence[str], None] = 'c17f9a62e019'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add E-E-A-T professional fields to persona table."""
    # Add professional fields for E-E-A-T personas
    op.add_column('persona', sa.Column('full_name', sa.String(length=255), nullable=True))
    op.add_column('persona', sa.Column('professional_title', sa.String(length=255), nullable=True))
    op.add_column('persona', sa.Column('areas_of_expertise', sa.Text(), nullable=True))
    op.add_column('persona', sa.Column('tone_of_voice', sa.String(length=255), nullable=True))
    op.add_column('persona', sa.Column('bio', sa.Text(), nullable=True))
    op.add_column('persona', sa.Column('linkedin_url', sa.String(length=500), nullable=True))


def downgrade() -> None:
    """Remove E-E-A-T professional fields from persona table."""
    op.drop_column('persona', 'linkedin_url')
    op.drop_column('persona', 'bio')
    op.drop_column('persona', 'tone_of_voice')
    op.drop_column('persona', 'areas_of_expertise')
    op.drop_column('persona', 'professional_title')
    op.drop_column('persona', 'full_name')
