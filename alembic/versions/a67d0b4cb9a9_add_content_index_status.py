"""add_content_index_status

Revision ID: a67d0b4cb9a9
Revises: 9e10ee847769
Create Date: 2026-07-06 17:45:15.612299

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a67d0b4cb9a9'
down_revision: Union[str, Sequence[str], None] = '9e10ee847769'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'content_index_status',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('content_id', sa.UUID(), nullable=False),
        sa.Column('publishing_result_id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('verdict', sa.String(length=30), nullable=True, comment='PASS, NEUTRAL, FAIL, or VERDICT_UNSPECIFIED'),
        sa.Column('coverage_state', sa.Text(), nullable=True),
        sa.Column('robots_txt_state', sa.String(length=30), nullable=True),
        sa.Column('indexing_state', sa.String(length=30), nullable=True),
        sa.Column('page_fetch_state', sa.String(length=30), nullable=True),
        sa.Column('last_crawl_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('inspected_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('raw_response', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['content_id'], ['content.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['publishing_result_id'], ['content_publishing_results.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspace.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('publishing_result_id', name='uq_content_index_status_publishing_result_id'),
    )
    op.create_index(op.f('ix_content_index_status_content_id'), 'content_index_status', ['content_id'], unique=False)
    op.create_index(op.f('ix_content_index_status_publishing_result_id'), 'content_index_status', ['publishing_result_id'], unique=True)
    op.create_index(op.f('ix_content_index_status_workspace_id'), 'content_index_status', ['workspace_id'], unique=False)
    op.create_index(op.f('ix_content_index_status_verdict'), 'content_index_status', ['verdict'], unique=False)

    print("  ✓ Created content_index_status")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('content_index_status')
    print("  ✓ Dropped content_index_status")
