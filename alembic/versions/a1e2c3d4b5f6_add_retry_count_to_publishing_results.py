"""add_retry_count_to_publishing_results

Revision ID: a1e2c3d4b5f6
Revises: 842403e5c605
Create Date: 2026-07-28

Adds retry_count to content_publishing_results so the scheduled-publish
background task can cap automatic retries and transition to a FAILED
status once attempts are exhausted, instead of retrying a broken
schedule forever.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a1e2c3d4b5f6'
down_revision: Union[str, Sequence[str], None] = '842403e5c605'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'content_publishing_results',
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
    )
    print("  ✓ Added retry_count to content_publishing_results")


def downgrade() -> None:
    op.drop_column('content_publishing_results', 'retry_count')
    print("  ✓ Removed retry_count from content_publishing_results")
