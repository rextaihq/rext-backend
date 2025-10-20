"""add onboarding marketing fields

Revision ID: onb20251020
Revises: 3dbd19e83367
Create Date: 2025-10-20 17:17:28.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'onb20251020'
down_revision = '3dbd19e83367'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add marketing data columns
    op.add_column('user_onboarding', sa.Column('user_industry', sa.String(length=100), nullable=True))
    op.add_column('user_onboarding', sa.Column('user_role', sa.String(length=100), nullable=True))
    op.add_column('user_onboarding', sa.Column('user_goal', sa.Text(), nullable=True))
    op.add_column('user_onboarding', sa.Column('heard_from', sa.String(length=100), nullable=True))

    # Add product tour tracking columns
    op.add_column('user_onboarding', sa.Column('tour_completed', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('user_onboarding', sa.Column('tour_skipped', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('user_onboarding', sa.Column('tour_started_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('user_onboarding', sa.Column('tour_completed_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    # Remove tour tracking columns
    op.drop_column('user_onboarding', 'tour_completed_at')
    op.drop_column('user_onboarding', 'tour_started_at')
    op.drop_column('user_onboarding', 'tour_skipped')
    op.drop_column('user_onboarding', 'tour_completed')

    # Remove marketing data columns
    op.drop_column('user_onboarding', 'heard_from')
    op.drop_column('user_onboarding', 'user_goal')
    op.drop_column('user_onboarding', 'user_role')
    op.drop_column('user_onboarding', 'user_industry')
