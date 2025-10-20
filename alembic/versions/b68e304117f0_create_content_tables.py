"""create_content_tables

Revision ID: b68e304117f0
Revises: 36ef85f33af2
Create Date: 2025-10-03 15:54:38.304477

Note: Originally revised c47862f79eae (seed003 - test data with workspace auto-creation).
      seed003 has been removed. Now depends on 36ef85f33af2 (merge_schema_and_seeds).

Creates all 10 content-related tables:
- content (main table)
- content_progress
- content_metadata
- content_seo_data
- content_ai_config
- content_structure
- content_research_config
- content_tracking
- content_review
- content_versions
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b68e304117f0'
down_revision: Union[str, Sequence[str], None] = '36ef85f33af2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - create all content tables."""

    # Create content table (main table - must be first)
    op.create_table(
        'content',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('topic_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_by_user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('assigned_to_user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('author_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('slug', sa.Text(), nullable=False, unique=True),
        sa.Column('body_markdown', sa.Text(), nullable=True),
        sa.Column('body_html', sa.Text(), nullable=True),
        sa.Column('content_format', sa.Text(), nullable=True, server_default='Markdown'),
        sa.Column('status', sa.Text(), nullable=True, server_default='draft'),
        sa.Column('content_language', sa.Text(), nullable=True, server_default='English'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('deleted_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspace.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['topic_id'], ['topics.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['assigned_to_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['author_id'], ['users.id'], ondelete='SET NULL'),
    )
    # Create indexes for content table
    op.create_index('ix_content_workspace_id', 'content', ['workspace_id'])
    op.create_index('ix_content_topic_id', 'content', ['topic_id'])
    op.create_index('ix_content_slug', 'content', ['slug'])
    op.create_index('ix_content_status', 'content', ['status'])
    op.create_index('ix_content_created_by_user_id', 'content', ['created_by_user_id'])

    # Create content_progress table
    op.create_table(
        'content_progress',
        sa.Column('content_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('current_step', sa.Text(), nullable=False),
        sa.Column('progress_percent', sa.Integer(), server_default='0'),
        sa.Column('status_message', sa.Text(), nullable=True),
        sa.Column('step_details', postgresql.JSONB(), nullable=True),
        sa.Column('estimated_time_remaining', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['content_id'], ['content.id'], ondelete='CASCADE'),
    )

    # Create content_metadata table
    op.create_table(
        'content_metadata',
        sa.Column('content_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('content_summary', sa.Text(), nullable=True),
        sa.Column('content_type', sa.Text(), nullable=True),
        sa.Column('target_platform', sa.Text(), nullable=True),
        sa.Column('target_industry', sa.Text(), nullable=True),
        sa.Column('target_audience', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('audience_size', sa.Text(), nullable=True),
        sa.Column('complexity_level', sa.Text(), nullable=True),
        sa.Column('content_tone', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('target_region', sa.Text(), nullable=True),
        sa.Column('content_objectives', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('source_references', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('content_word_count', sa.Integer(), nullable=True),
        sa.Column('reading_time_minutes', sa.Integer(), nullable=True),
        sa.Column('content_quality_scores', postgresql.JSONB(), nullable=True),
        sa.Column('featured_image_prompt', sa.Text(), nullable=True),
        sa.Column('featured_image_alt_text', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['content_id'], ['content.id'], ondelete='CASCADE'),
    )

    # Create content_seo_data table
    op.create_table(
        'content_seo_data',
        sa.Column('content_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('content_primary_keywords', postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column('content_secondary_keywords', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('content_meta_description', sa.Text(), nullable=False),
        sa.Column('content_search_intent', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('content_seo_score', sa.Float(), nullable=True),
        sa.Column('content_readability_score', sa.Float(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['content_id'], ['content.id'], ondelete='CASCADE'),
    )

    # Create content_ai_config table
    op.create_table(
        'content_ai_config',
        sa.Column('content_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('ai_model', sa.Text(), nullable=False),
        sa.Column('temperature', sa.Numeric(3, 2), nullable=True),
        sa.Column('max_output_tokens', sa.Integer(), nullable=True),
        sa.Column('top_p', sa.Numeric(3, 2), nullable=True),
        sa.Column('frequency_penalty', sa.Numeric(3, 2), nullable=True),
        sa.Column('generation_params', postgresql.JSONB(), nullable=True),
        sa.Column('context_sources', postgresql.JSONB(), nullable=True),
        sa.Column('generation_errors', postgresql.JSONB(), nullable=True),
        sa.Column('generation_warnings', postgresql.JSONB(), nullable=True),
        sa.Column('structured_output', postgresql.JSONB(), nullable=True),
        sa.Column('generated_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['content_id'], ['content.id'], ondelete='CASCADE'),
    )

    # Create content_structure table
    op.create_table(
        'content_structure',
        sa.Column('content_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('content_length', postgresql.JSONB(), nullable=True),
        sa.Column('include_toc', sa.Boolean(), server_default='false'),
        sa.Column('include_summary', sa.Boolean(), server_default='false'),
        sa.Column('include_cta', sa.Boolean(), server_default='false'),
        sa.Column('include_key_takeaways', sa.Boolean(), server_default='false'),
        sa.Column('include_latest_info', sa.Boolean(), server_default='false'),
        sa.Column('include_examples', sa.Boolean(), server_default='false'),
        sa.Column('include_statistics', sa.Boolean(), server_default='false'),
        sa.Column('include_quotes', sa.Boolean(), server_default='false'),
        sa.Column('competitor_analysis', sa.Boolean(), server_default='false'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['content_id'], ['content.id'], ondelete='CASCADE'),
    )

    # Create content_research_config table
    op.create_table(
        'content_research_config',
        sa.Column('content_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('research_level', sa.Text(), nullable=True),
        sa.Column('fact_checking', sa.Text(), nullable=True),
        sa.Column('content_freshness', sa.Text(), nullable=True),
        sa.Column('research_context', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['content_id'], ['content.id'], ondelete='CASCADE'),
    )

    # Create content_tracking table
    op.create_table(
        'content_tracking',
        sa.Column('content_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('request_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('flow_execution_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('request_payload', postgresql.JSONB(), nullable=True),
        sa.Column('topic_snapshot', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['content_id'], ['content.id'], ondelete='CASCADE'),
    )

    # Create content_review table
    op.create_table(
        'content_review',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('content_id', postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column('content_type', sa.String(50), nullable=False),
        sa.Column('assigned_reviewers', postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=True),
        sa.Column('status', sa.String(20), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['content_id'], ['content.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    )

    # Create content_versions table
    op.create_table(
        'content_versions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('content_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('content_data', postgresql.JSONB(), nullable=False),
        sa.Column('is_current', sa.Boolean(), server_default='false'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['content_id'], ['content.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_content_versions_content_id', 'content_versions', ['content_id'])


def downgrade() -> None:
    """Downgrade schema - drop all content tables in reverse order."""

    # Drop tables in reverse order (child tables first, parent table last)
    op.drop_index('ix_content_versions_content_id', table_name='content_versions')
    op.drop_table('content_versions')
    op.drop_table('content_review')
    op.drop_table('content_tracking')
    op.drop_table('content_research_config')
    op.drop_table('content_structure')
    op.drop_table('content_ai_config')
    op.drop_table('content_seo_data')
    op.drop_table('content_metadata')
    op.drop_table('content_progress')

    # Drop indexes before dropping content table
    op.drop_index('ix_content_created_by_user_id', table_name='content')
    op.drop_index('ix_content_status', table_name='content')
    op.drop_index('ix_content_slug', table_name='content')
    op.drop_index('ix_content_topic_id', table_name='content')
    op.drop_index('ix_content_workspace_id', table_name='content')

    # Drop main content table last
    op.drop_table('content')
