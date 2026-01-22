"""drop_topics_table_and_content_topic_id

Revision ID: c17f9a62e019
Revises: 4cce8d51f13c
Create Date: 2026-01-16 00:04:52.197446

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c17f9a62e019'
down_revision: Union[str, Sequence[str], None] = '4cce8d51f13c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop topics table and remove topic_id from content."""
    # Drop topic_id foreign key constraint and column from content table
    op.drop_constraint('content_topic_id_fkey', 'content', type_='foreignkey')
    op.drop_column('content', 'topic_id')
    
    # Drop topics table
    op.drop_table('topics')


def downgrade() -> None:
    """Recreate topics table and content.topic_id (not recommended)."""
    # Note: This will recreate the table structure but data will be lost
    # Recreate topics table with all original columns
    op.create_table(
        'topics',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('generated_by_user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('generated_by_first_name', sa.String(), nullable=True),
        sa.Column('generated_by_last_name', sa.String(), nullable=True),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('angle', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=False),
        sa.Column('channel_fit', postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column('audience_fit', postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column('why_it_works', sa.String(), nullable=True),
        sa.Column('scores', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('tags', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('suggested_defaults', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('goal_alignment', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('content_guidance', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('audience_insights', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('internal_research_config', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('approved', sa.Boolean(), server_default='false', nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('user_settings', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspace.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['generated_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_topics_workspace_id', 'topics', ['workspace_id'])
    
    # Recreate topic_id column in content table
    op.add_column('content', sa.Column('topic_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('content_topic_id_fkey', 'content', 'topics', ['topic_id'], ['id'], ondelete='SET NULL')
    op.create_index('ix_content_topic_id', 'content', ['topic_id'])
