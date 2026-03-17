"""add brand_voice pillars and content topic_id

Revision ID: 20260317_pillars
Revises: 
Create Date: 2026-03-17

Adds columns that exist in the SQLAlchemy models but were missing from the DB:
  - brand_voice.content_pillar  (Text, nullable)
  - brand_voice.secondary_pillars  (JSONB, nullable)
  - content.topic_id  (UUID FK → topics.id SET NULL, nullable)
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision = '20260317_pillars'
down_revision = '263449deebd4'   # previous head
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── topics (recreate if missing) ─────────────────────────────────────────
    # We check if it exists because it might have been dropped in a previous migration
    # but the models still depend on it.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    
    if 'topics' not in tables:
        op.create_table(
            'topics',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column('workspace_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('workspace.id', ondelete='CASCADE'), nullable=False),
            sa.Column('generated_by_user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
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
        )
        op.create_index('ix_topics_workspace_id', 'topics', ['workspace_id'], unique=False)

    # ── brand_voice ──────────────────────────────────────────────────────────
    # Check if columns exist before adding
    columns_bv = [c['name'] for c in inspector.get_columns('brand_voice')]
    if 'content_pillar' not in columns_bv:
        op.add_column(
            'brand_voice',
            sa.Column('content_pillar', sa.Text(), nullable=True)
        )
    if 'secondary_pillars' not in columns_bv:
        op.add_column(
            'brand_voice',
            sa.Column('secondary_pillars', postgresql.JSONB(astext_type=sa.Text()), nullable=True)
        )

    # ── content ───────────────────────────────────────────────────────────────
    columns_content = [c['name'] for c in inspector.get_columns('content')]
    if 'topic_id' not in columns_content:
        op.add_column(
            'content',
            sa.Column(
                'topic_id',
                postgresql.UUID(as_uuid=True),
                nullable=True
            )
        )
    
    # Check if FK exists
    fks = inspector.get_foreign_keys('content')
    fk_names = [fk['name'] for fk in fks]
    if 'fk_content_topic_id' not in fk_names:
        op.create_foreign_key(
            'fk_content_topic_id',
            'content', 'topics',
            ['topic_id'], ['id'],
            ondelete='SET NULL'
        )
    
    # Check if index exists
    indexes = inspector.get_indexes('content')
    index_names = [idx['name'] for idx in indexes]
    if 'ix_content_topic_id' not in index_names:
        op.create_index(
            'ix_content_topic_id',
            'content', ['topic_id'],
            unique=False
        )


def downgrade() -> None:
    # ── content ───────────────────────────────────────────────────────────────
    op.drop_index('ix_content_topic_id', table_name='content')
    op.drop_constraint('fk_content_topic_id', 'content', type_='foreignkey')
    op.drop_column('content', 'topic_id')

    # ── brand_voice ──────────────────────────────────────────────────────────
    op.drop_column('brand_voice', 'secondary_pillars')
    op.drop_column('brand_voice', 'content_pillar')

    # ── topics ───────────────────────────────────────────────────────────────
    # Typically we dont drop the table in a downgrade if it might have had data,
    # but for symmetry with this fix:
    op.drop_table('topics')
