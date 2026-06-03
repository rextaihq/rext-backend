"""add_scheduled_publish_at_to_publishing_results

Revision ID: c1d2e3f4a5b6
Revises: b6dca73a7412
Create Date: 2026-06-01

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, Sequence[str], None] = 'b6dca73a7412'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'content_publishing_results',
        sa.Column('scheduled_publish_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(
        'ix_content_publishing_results_scheduled_publish_at',
        'content_publishing_results',
        ['scheduled_publish_at'],
    )
    print("  ✓ Added scheduled_publish_at to content_publishing_results")


def downgrade() -> None:
    op.drop_index(
        'ix_content_publishing_results_scheduled_publish_at',
        table_name='content_publishing_results',
    )
    op.drop_column('content_publishing_results', 'scheduled_publish_at')
    print("  ✓ Removed scheduled_publish_at from content_publishing_results")
