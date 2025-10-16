"""consolidate_content_tables

Revision ID: 40fd95ca1e8d
Revises: 4903202d53ae
Create Date: 2025-10-16 07:59:39.764602

Consolidates content-related tables into JSONB columns for improved query performance.

Migration consolidates 5 rarely-accessed tables into the main content table:
- content_metadata → content.metadata_json
- content_tracking → content.tracking_json
- content_ai_config → content.ai_config_json
- content_structure → content.structure_json
- content_research_config → content.research_config_json

Keeps separate:
- content_progress (real-time updates during generation)
- content_seo_data (searchable SEO fields)
- content_review (separate workflow)
- content_version (history tracking)
- content_media (separate entity)

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = '40fd95ca1e8d'
down_revision: Union[str, Sequence[str], None] = '4903202d53ae'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Upgrade schema: Consolidate 5 content tables into JSONB columns.

    This migration:
    1. Adds 5 JSONB columns to content table
    2. Migrates all data from related tables to JSONB
    3. Drops the old tables
    4. Adds GIN indexes on JSONB for performance
    """

    # Step 1: Add JSONB columns to content table
    print("Adding JSONB columns to content table...")
    op.add_column('content', sa.Column('metadata_json', JSONB, nullable=True))
    op.add_column('content', sa.Column('tracking_json', JSONB, nullable=True))
    op.add_column('content', sa.Column('ai_config_json', JSONB, nullable=True))
    op.add_column('content', sa.Column('structure_json', JSONB, nullable=True))
    op.add_column('content', sa.Column('research_config_json', JSONB, nullable=True))

    # Step 2: Migrate data from content_metadata
    print("Migrating content_metadata data...")
    op.execute("""
        UPDATE content c
        SET metadata_json = (
            SELECT jsonb_build_object(
                'content_summary', cm.content_summary,
                'content_type', cm.content_type,
                'target_platform', cm.target_platform,
                'target_industry', cm.target_industry,
                'target_audience', cm.target_audience,
                'audience_size', cm.audience_size,
                'complexity_level', cm.complexity_level,
                'content_tone', cm.content_tone,
                'target_region', cm.target_region,
                'content_objectives', cm.content_objectives,
                'source_references', cm.source_references,
                'content_word_count', cm.content_word_count,
                'reading_time_minutes', cm.reading_time_minutes,
                'content_quality_scores', cm.content_quality_scores,
                'featured_image_prompt', cm.featured_image_prompt,
                'featured_image_alt_text', cm.featured_image_alt_text,
                'created_at', cm.created_at::text,
                'updated_at', cm.updated_at::text
            )
            FROM content_metadata cm
            WHERE cm.content_id = c.id
        )
        WHERE EXISTS (SELECT 1 FROM content_metadata cm WHERE cm.content_id = c.id)
    """)

    # Step 3: Migrate data from content_tracking
    print("Migrating content_tracking data...")
    op.execute("""
        UPDATE content c
        SET tracking_json = (
            SELECT jsonb_build_object(
                'request_id', ct.request_id::text,
                'flow_execution_id', ct.flow_execution_id::text,
                'request_payload', ct.request_payload,
                'topic_snapshot', ct.topic_snapshot,
                'created_at', ct.created_at::text,
                'updated_at', ct.updated_at::text
            )
            FROM content_tracking ct
            WHERE ct.content_id = c.id
        )
        WHERE EXISTS (SELECT 1 FROM content_tracking ct WHERE ct.content_id = c.id)
    """)

    # Step 4: Migrate data from content_ai_config
    print("Migrating content_ai_config data...")
    op.execute("""
        UPDATE content c
        SET ai_config_json = (
            SELECT jsonb_build_object(
                'ai_model', cac.ai_model,
                'temperature', cac.temperature,
                'max_output_tokens', cac.max_output_tokens,
                'top_p', cac.top_p,
                'frequency_penalty', cac.frequency_penalty,
                'generation_params', cac.generation_params,
                'context_sources', cac.context_sources,
                'generation_errors', cac.generation_errors,
                'generation_warnings', cac.generation_warnings,
                'structured_output', cac.structured_output,
                'generated_at', cac.generated_at::text,
                'created_at', cac.created_at::text,
                'updated_at', cac.updated_at::text
            )
            FROM content_ai_config cac
            WHERE cac.content_id = c.id
        )
        WHERE EXISTS (SELECT 1 FROM content_ai_config cac WHERE cac.content_id = c.id)
    """)

    # Step 5: Migrate data from content_structure
    print("Migrating content_structure data...")
    op.execute("""
        UPDATE content c
        SET structure_json = (
            SELECT jsonb_build_object(
                'content_length', cs.content_length,
                'include_toc', cs.include_toc,
                'include_summary', cs.include_summary,
                'include_cta', cs.include_cta,
                'include_key_takeaways', cs.include_key_takeaways,
                'include_latest_info', cs.include_latest_info,
                'include_examples', cs.include_examples,
                'include_statistics', cs.include_statistics,
                'include_quotes', cs.include_quotes,
                'competitor_analysis', cs.competitor_analysis,
                'created_at', cs.created_at::text,
                'updated_at', cs.updated_at::text
            )
            FROM content_structure cs
            WHERE cs.content_id = c.id
        )
        WHERE EXISTS (SELECT 1 FROM content_structure cs WHERE cs.content_id = c.id)
    """)

    # Step 6: Migrate data from content_research_config
    print("Migrating content_research_config data...")
    op.execute("""
        UPDATE content c
        SET research_config_json = (
            SELECT jsonb_build_object(
                'research_level', crc.research_level,
                'fact_checking', crc.fact_checking,
                'content_freshness', crc.content_freshness,
                'research_context', crc.research_context,
                'created_at', crc.created_at::text,
                'updated_at', crc.updated_at::text
            )
            FROM content_research_config crc
            WHERE crc.content_id = c.id
        )
        WHERE EXISTS (SELECT 1 FROM content_research_config crc WHERE crc.content_id = c.id)
    """)

    # Step 7: Add GIN indexes on JSONB columns for better query performance
    print("Creating GIN indexes on JSONB columns...")
    op.create_index(
        'ix_content_metadata_json_gin',
        'content',
        ['metadata_json'],
        postgresql_using='gin'
    )
    op.create_index(
        'ix_content_ai_config_json_gin',
        'content',
        ['ai_config_json'],
        postgresql_using='gin'
    )

    # Step 8: Drop old tables
    print("Dropping consolidated tables...")
    op.drop_table('content_research_config')
    op.drop_table('content_structure')
    op.drop_table('content_ai_config')
    op.drop_table('content_tracking')
    op.drop_table('content_metadata')

    print("✅ Content table consolidation completed successfully!")


def downgrade() -> None:
    """
    Downgrade schema: Restore 5 content tables from JSONB columns.

    This migration:
    1. Recreates the dropped tables
    2. Migrates data back from JSONB to tables
    3. Drops the JSONB columns
    """

    # Step 1: Recreate content_metadata table
    print("Recreating content_metadata table...")
    op.create_table(
        'content_metadata',
        sa.Column('content_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('content_summary', sa.Text, nullable=True),
        sa.Column('content_type', sa.Text, nullable=True),
        sa.Column('target_platform', sa.Text, nullable=True),
        sa.Column('target_industry', sa.Text, nullable=True),
        sa.Column('target_audience', sa.dialects.postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column('audience_size', sa.Text, nullable=True),
        sa.Column('complexity_level', sa.Text, nullable=True),
        sa.Column('content_tone', sa.dialects.postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column('target_region', sa.Text, nullable=True),
        sa.Column('content_objectives', sa.dialects.postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column('source_references', sa.dialects.postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column('content_word_count', sa.Integer, nullable=True),
        sa.Column('reading_time_minutes', sa.Integer, nullable=True),
        sa.Column('content_quality_scores', JSONB, nullable=True),
        sa.Column('featured_image_prompt', sa.Text, nullable=True),
        sa.Column('featured_image_alt_text', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['content_id'], ['content.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('content_id')
    )

    # Step 2: Recreate content_tracking table
    print("Recreating content_tracking table...")
    op.create_table(
        'content_tracking',
        sa.Column('content_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('request_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('flow_execution_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('request_payload', JSONB, nullable=True),
        sa.Column('topic_snapshot', JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['content_id'], ['content.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('content_id')
    )

    # Step 3: Recreate content_ai_config table
    print("Recreating content_ai_config table...")
    op.create_table(
        'content_ai_config',
        sa.Column('content_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('ai_model', sa.Text, nullable=False),
        sa.Column('temperature', sa.Numeric(3, 2), nullable=True),
        sa.Column('max_output_tokens', sa.Integer, nullable=True),
        sa.Column('top_p', sa.Numeric(3, 2), nullable=True),
        sa.Column('frequency_penalty', sa.Numeric(3, 2), nullable=True),
        sa.Column('generation_params', JSONB, nullable=True),
        sa.Column('context_sources', JSONB, nullable=True),
        sa.Column('generation_errors', JSONB, nullable=True),
        sa.Column('generation_warnings', JSONB, nullable=True),
        sa.Column('structured_output', JSONB, nullable=True),
        sa.Column('generated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['content_id'], ['content.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('content_id')
    )

    # Step 4: Recreate content_structure table
    print("Recreating content_structure table...")
    op.create_table(
        'content_structure',
        sa.Column('content_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('content_length', JSONB, nullable=True),
        sa.Column('include_toc', sa.Boolean, default=False),
        sa.Column('include_summary', sa.Boolean, default=False),
        sa.Column('include_cta', sa.Boolean, default=False),
        sa.Column('include_key_takeaways', sa.Boolean, default=False),
        sa.Column('include_latest_info', sa.Boolean, default=False),
        sa.Column('include_examples', sa.Boolean, default=False),
        sa.Column('include_statistics', sa.Boolean, default=False),
        sa.Column('include_quotes', sa.Boolean, default=False),
        sa.Column('competitor_analysis', sa.Boolean, default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['content_id'], ['content.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('content_id')
    )

    # Step 5: Recreate content_research_config table
    print("Recreating content_research_config table...")
    op.create_table(
        'content_research_config',
        sa.Column('content_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('research_level', sa.Text, nullable=True),
        sa.Column('fact_checking', sa.Text, nullable=True),
        sa.Column('content_freshness', sa.Text, nullable=True),
        sa.Column('research_context', JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['content_id'], ['content.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('content_id')
    )

    # Step 6-10: Migrate data back from JSONB to tables
    print("Migrating data back from JSONB to tables...")

    op.execute("""
        INSERT INTO content_metadata (
            content_id, content_summary, content_type, target_platform, target_industry,
            target_audience, audience_size, complexity_level, content_tone, target_region,
            content_objectives, source_references, content_word_count, reading_time_minutes,
            content_quality_scores, featured_image_prompt, featured_image_alt_text,
            created_at, updated_at
        )
        SELECT
            c.id,
            (c.metadata_json->>'content_summary'),
            (c.metadata_json->>'content_type'),
            (c.metadata_json->>'target_platform'),
            (c.metadata_json->>'target_industry'),
            ARRAY(SELECT jsonb_array_elements_text(c.metadata_json->'target_audience')),
            (c.metadata_json->>'audience_size'),
            (c.metadata_json->>'complexity_level'),
            ARRAY(SELECT jsonb_array_elements_text(c.metadata_json->'content_tone')),
            (c.metadata_json->>'target_region'),
            ARRAY(SELECT jsonb_array_elements_text(c.metadata_json->'content_objectives')),
            ARRAY(SELECT jsonb_array_elements_text(c.metadata_json->'source_references')),
            (c.metadata_json->>'content_word_count')::integer,
            (c.metadata_json->>'reading_time_minutes')::integer,
            c.metadata_json->'content_quality_scores',
            (c.metadata_json->>'featured_image_prompt'),
            (c.metadata_json->>'featured_image_alt_text'),
            (c.metadata_json->>'created_at')::timestamp with time zone,
            (c.metadata_json->>'updated_at')::timestamp with time zone
        FROM content c
        WHERE c.metadata_json IS NOT NULL
    """)

    op.execute("""
        INSERT INTO content_tracking (
            content_id, request_id, flow_execution_id, request_payload,
            topic_snapshot, created_at, updated_at
        )
        SELECT
            c.id,
            (c.tracking_json->>'request_id')::uuid,
            (c.tracking_json->>'flow_execution_id')::uuid,
            c.tracking_json->'request_payload',
            c.tracking_json->'topic_snapshot',
            (c.tracking_json->>'created_at')::timestamp with time zone,
            (c.tracking_json->>'updated_at')::timestamp with time zone
        FROM content c
        WHERE c.tracking_json IS NOT NULL
    """)

    op.execute("""
        INSERT INTO content_ai_config (
            content_id, ai_model, temperature, max_output_tokens, top_p,
            frequency_penalty, generation_params, context_sources, generation_errors,
            generation_warnings, structured_output, generated_at, created_at, updated_at
        )
        SELECT
            c.id,
            (c.ai_config_json->>'ai_model'),
            (c.ai_config_json->>'temperature')::numeric(3,2),
            (c.ai_config_json->>'max_output_tokens')::integer,
            (c.ai_config_json->>'top_p')::numeric(3,2),
            (c.ai_config_json->>'frequency_penalty')::numeric(3,2),
            c.ai_config_json->'generation_params',
            c.ai_config_json->'context_sources',
            c.ai_config_json->'generation_errors',
            c.ai_config_json->'generation_warnings',
            c.ai_config_json->'structured_output',
            (c.ai_config_json->>'generated_at')::timestamp with time zone,
            (c.ai_config_json->>'created_at')::timestamp with time zone,
            (c.ai_config_json->>'updated_at')::timestamp with time zone
        FROM content c
        WHERE c.ai_config_json IS NOT NULL
    """)

    op.execute("""
        INSERT INTO content_structure (
            content_id, content_length, include_toc, include_summary, include_cta,
            include_key_takeaways, include_latest_info, include_examples,
            include_statistics, include_quotes, competitor_analysis, created_at, updated_at
        )
        SELECT
            c.id,
            c.structure_json->'content_length',
            (c.structure_json->>'include_toc')::boolean,
            (c.structure_json->>'include_summary')::boolean,
            (c.structure_json->>'include_cta')::boolean,
            (c.structure_json->>'include_key_takeaways')::boolean,
            (c.structure_json->>'include_latest_info')::boolean,
            (c.structure_json->>'include_examples')::boolean,
            (c.structure_json->>'include_statistics')::boolean,
            (c.structure_json->>'include_quotes')::boolean,
            (c.structure_json->>'competitor_analysis')::boolean,
            (c.structure_json->>'created_at')::timestamp with time zone,
            (c.structure_json->>'updated_at')::timestamp with time zone
        FROM content c
        WHERE c.structure_json IS NOT NULL
    """)

    op.execute("""
        INSERT INTO content_research_config (
            content_id, research_level, fact_checking, content_freshness,
            research_context, created_at, updated_at
        )
        SELECT
            c.id,
            (c.research_config_json->>'research_level'),
            (c.research_config_json->>'fact_checking'),
            (c.research_config_json->>'content_freshness'),
            c.research_config_json->'research_context',
            (c.research_config_json->>'created_at')::timestamp with time zone,
            (c.research_config_json->>'updated_at')::timestamp with time zone
        FROM content c
        WHERE c.research_config_json IS NOT NULL
    """)

    # Step 11: Drop indexes on JSONB columns
    print("Dropping JSONB indexes...")
    op.drop_index('ix_content_ai_config_json_gin', table_name='content')
    op.drop_index('ix_content_metadata_json_gin', table_name='content')

    # Step 12: Drop JSONB columns from content table
    print("Dropping JSONB columns...")
    op.drop_column('content', 'research_config_json')
    op.drop_column('content', 'structure_json')
    op.drop_column('content', 'ai_config_json')
    op.drop_column('content', 'tracking_json')
    op.drop_column('content', 'metadata_json')

    print("✅ Downgrade completed successfully!")
