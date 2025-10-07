"""enhance_topics_table_schema

Revision ID: ca05d74bd19c
Revises: 168db6d8bec3
Create Date: 2025-10-07 17:45:27.562567

Enhances topics table with full schema to match TopicsModel:
- Renames topic_name -> title
- Adds enhanced fields: angle, channel_fit, audience_fit, why_it_works, scores, tags
- Adds enrichment fields: suggested_defaults, goal_alignment, content_guidance, audience_insights, internal_research_config
- Adds approval fields: approved, approved_at
- Adds user_settings field
- Makes workspace_id NOT NULL
- Updates updated_at default
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'ca05d74bd19c'
down_revision: Union[str, Sequence[str], None] = '168db6d8bec3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - enhance topics table."""
    from sqlalchemy import inspect

    bind = op.get_bind()
    inspector = inspect(bind)

    # Get current columns
    columns = [c['name'] for c in inspector.get_columns('topics')]

    # Step 1: Rename topic_name to title (if topic_name exists)
    if 'topic_name' in columns and 'title' not in columns:
        op.alter_column('topics', 'topic_name', new_column_name='title')

    # Step 2: Add new columns (check each one individually)
    if 'angle' not in columns:
        op.add_column('topics', sa.Column('angle', sa.String(), nullable=True))

    if 'channel_fit' not in columns:
        op.add_column('topics', sa.Column('channel_fit', postgresql.ARRAY(sa.String()), nullable=True))

    if 'audience_fit' not in columns:
        op.add_column('topics', sa.Column('audience_fit', postgresql.ARRAY(sa.String()), nullable=True))

    if 'why_it_works' not in columns:
        op.add_column('topics', sa.Column('why_it_works', sa.String(), nullable=True))

    if 'scores' not in columns:
        op.add_column('topics', sa.Column('scores', postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    if 'tags' not in columns:
        op.add_column('topics', sa.Column('tags', postgresql.ARRAY(sa.String()), nullable=True))

    if 'suggested_defaults' not in columns:
        op.add_column('topics', sa.Column('suggested_defaults', postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    if 'goal_alignment' not in columns:
        op.add_column('topics', sa.Column('goal_alignment', postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    if 'content_guidance' not in columns:
        op.add_column('topics', sa.Column('content_guidance', postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    if 'audience_insights' not in columns:
        op.add_column('topics', sa.Column('audience_insights', postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    if 'internal_research_config' not in columns:
        op.add_column('topics', sa.Column('internal_research_config', postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    if 'approved' not in columns:
        op.add_column('topics', sa.Column('approved', sa.Boolean(), nullable=True, server_default='false'))

    if 'approved_at' not in columns:
        op.add_column('topics', sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True))

    if 'user_settings' not in columns:
        op.add_column('topics', sa.Column('user_settings', postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    # Step 3: Update existing data with default values for required JSONB fields
    op.execute("""
        UPDATE topics
        SET
            scores = COALESCE(scores, '{}'::jsonb),
            suggested_defaults = COALESCE(suggested_defaults, '{}'::jsonb),
            goal_alignment = COALESCE(goal_alignment, '{}'::jsonb),
            content_guidance = COALESCE(content_guidance, '{}'::jsonb),
            audience_insights = COALESCE(audience_insights, '{}'::jsonb),
            internal_research_config = COALESCE(internal_research_config, '{}'::jsonb),
            user_settings = COALESCE(user_settings, '{}'::jsonb),
            channel_fit = COALESCE(channel_fit, ARRAY[]::text[]),
            audience_fit = COALESCE(audience_fit, ARRAY[]::text[]),
            angle = COALESCE(angle, ''),
            title = COALESCE(title, 'Untitled')
        WHERE id IS NOT NULL
    """)

    # Step 4: Make required columns NOT NULL
    op.alter_column('topics', 'title', nullable=False)
    op.alter_column('topics', 'angle', nullable=False)
    op.alter_column('topics', 'channel_fit', nullable=False)
    op.alter_column('topics', 'audience_fit', nullable=False)
    op.alter_column('topics', 'scores', nullable=False)
    op.alter_column('topics', 'suggested_defaults', nullable=False)
    op.alter_column('topics', 'goal_alignment', nullable=False)
    op.alter_column('topics', 'content_guidance', nullable=False)
    op.alter_column('topics', 'audience_insights', nullable=False)
    op.alter_column('topics', 'internal_research_config', nullable=False)
    op.alter_column('topics', 'user_settings', nullable=False)
    op.alter_column('topics', 'workspace_id', nullable=False)

    # Step 5: Update description to be NOT NULL (it was Text, now String with nullable=False)
    op.execute("UPDATE topics SET description = COALESCE(description, '') WHERE description IS NULL")
    op.alter_column('topics', 'description', type_=sa.String(), nullable=False)

    # Step 6: Ensure created_at has proper default if not set
    op.alter_column('topics', 'created_at',
                    server_default=sa.func.now(),
                    nullable=False)


def downgrade() -> None:
    """Downgrade schema - revert to simple topics table."""

    # Revert column constraints
    op.alter_column('topics', 'workspace_id', nullable=True)
    op.alter_column('topics', 'description', type_=sa.Text(), nullable=True)
    op.alter_column('topics', 'created_at', server_default=None, nullable=True)

    # Drop added columns
    op.drop_column('topics', 'user_settings')
    op.drop_column('topics', 'approved_at')
    op.drop_column('topics', 'approved')
    op.drop_column('topics', 'internal_research_config')
    op.drop_column('topics', 'audience_insights')
    op.drop_column('topics', 'content_guidance')
    op.drop_column('topics', 'goal_alignment')
    op.drop_column('topics', 'suggested_defaults')
    op.drop_column('topics', 'tags')
    op.drop_column('topics', 'scores')
    op.drop_column('topics', 'why_it_works')
    op.drop_column('topics', 'audience_fit')
    op.drop_column('topics', 'channel_fit')
    op.drop_column('topics', 'angle')

    # Rename title back to topic_name
    op.alter_column('topics', 'title', new_column_name='topic_name')
