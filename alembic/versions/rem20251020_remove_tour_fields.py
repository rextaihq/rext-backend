"""remove tour fields from onboarding

Revision ID: rem20251020
Revises: onb20251020
Create Date: 2025-10-20 17:45:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'rem20251020'
down_revision = 'onb20251020'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Remove product tour tracking columns
    op.drop_column('user_onboarding', 'tour_completed_at')
    op.drop_column('user_onboarding', 'tour_started_at')
    op.drop_column('user_onboarding', 'tour_skipped')
    op.drop_column('user_onboarding', 'tour_completed')


def downgrade() -> None:
    # Add product tour tracking columns back
    op.add_column('user_onboarding', sa.Column('tour_completed', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('user_onboarding', sa.Column('tour_skipped', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('user_onboarding', sa.Column('tour_started_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('user_onboarding', sa.Column('tour_completed_at', sa.DateTime(timezone=True), nullable=True))
