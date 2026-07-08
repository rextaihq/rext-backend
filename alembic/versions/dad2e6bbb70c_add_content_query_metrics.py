"""add_content_query_metrics

Revision ID: dad2e6bbb70c
Revises: a67d0b4cb9a9
Create Date: 2026-07-07 16:36:06.673251

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dad2e6bbb70c'
down_revision: Union[str, Sequence[str], None] = 'a67d0b4cb9a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'content_query_metrics',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('content_id', sa.UUID(), nullable=False),
        sa.Column('publishing_result_id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('query', sa.Text(), nullable=False),
        sa.Column('clicks', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('impressions', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('ctr', sa.Float(), nullable=False, server_default='0'),
        sa.Column('position', sa.Float(), nullable=False, server_default='0'),
        sa.Column('window_days', sa.Integer(), nullable=False),
        sa.Column('synced_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['content_id'], ['content.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['publishing_result_id'], ['content_publishing_results.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspace.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('publishing_result_id', 'query', name='uq_content_query_metric_result_query'),
    )
    op.create_index(
        op.f('ix_content_query_metrics_content_id'), 'content_query_metrics', ['content_id'], unique=False
    )
    op.create_index(
        op.f('ix_content_query_metrics_publishing_result_id'),
        'content_query_metrics', ['publishing_result_id'], unique=False,
    )
    op.create_index(
        op.f('ix_content_query_metrics_workspace_id'), 'content_query_metrics', ['workspace_id'], unique=False
    )
    print("  ✓ Created content_query_metrics")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('content_query_metrics')
    print("  ✓ Dropped content_query_metrics")
