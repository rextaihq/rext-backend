"""add_publish_retry_fields_to_publishing_results

Revision ID: d4e5f6a7b8c9
Revises: c7a4e9b2d8f1
Create Date: 2026-07-28

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c7a4e9b2d8f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'content_publishing_results',
        sa.Column('publish_attempts', sa.Integer(), nullable=False, server_default='0')
    )
    op.add_column(
        'content_publishing_results',
        sa.Column('next_publish_attempt_at', sa.DateTime(timezone=True), nullable=True)
    )
    print("  ✓ Added publish_attempts and next_publish_attempt_at to content_publishing_results")


def downgrade() -> None:
    op.drop_column('content_publishing_results', 'next_publish_attempt_at')
    op.drop_column('content_publishing_results', 'publish_attempts')
    print("  ✓ Removed publish_attempts and next_publish_attempt_at from content_publishing_results")
