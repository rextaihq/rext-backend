"""add_workspace_integrations_and_simplify_content

Revision ID: c9e6ed3c63fa
Revises: f87a4a7e84e5
Create Date: 2026-01-16 14:52:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c9e6ed3c63fa'
down_revision: Union[str, Sequence[str], None] = 'f87a4a7e84e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema"""
    
    # 1. Create workspace_integrations table
    op.create_table('workspace_integrations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('integration_type', sa.String(length=50), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('site_url', sa.String(length=500), nullable=True),
        sa.Column('username', sa.String(length=255), nullable=True),
       sa.Column('app_password', sa.Text(), nullable=True),
        sa.Column('shop_domain', sa.String(length=500), nullable=True),
        sa.Column('access_token', sa.Text(), nullable=True),
        sa.Column('config_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspace.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('id')
    )
    op.create_index(op.f('ix_workspace_integrations_integration_type'), 'workspace_integrations', ['integration_type'], unique=False)
    op.create_index(op.f('ix_workspace_integrations_workspace_id'), 'workspace_integrations', ['workspace_id'], unique=False)
    
    # 2. Add new columns to content table
    op.add_column('content', sa.Column('meta_title', sa.Text(), nullable=True, comment='Meta title for SEO (50-60 chars)'))
    op.add_column('content', sa.Column('meta_description', sa.Text(), nullable=True, comment='Meta description for SEO (150-160 chars)'))
    op.add_column('content', sa.Column('introduction', sa.Text(), nullable=True, comment='Opening paragraph (150-300 words)'))
    op.add_column('content', sa.Column('focus_keyphrase', sa.Text(), nullable=True, comment='Primary focus keyphrase'))
    op.add_column('content', sa.Column('keyphrase_density', sa.Float(), nullable=True, comment='Keyphrase density percentage'))
    op.add_column('content', sa.Column('tags', postgresql.ARRAY(sa.Text()), nullable=True, comment='Article tags'))
    op.add_column('content', sa.Column('secondary_keywords', postgresql.ARRAY(sa.Text()), nullable=True, comment='Secondary keywords'))
    op.add_column('content', sa.Column('images_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Image alt text suggestions and placements'))
    op.add_column('content', sa.Column('links_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Internal and outbound links'))
    op.add_column('content', sa.Column('schema_markup', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Structured data/schema markup'))
    op.add_column('content', sa.Column('seo_score', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='On-page SEO scoring details'))
    op.add_column('content', sa.Column('readability_score', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Readability analysis'))
    op.add_column('content', sa.Column('wordpress_post_id', sa.Integer(), nullable=True, comment='WordPress post ID after publishing'))
    op.add_column('content', sa.Column('wordpress_url', sa.Text(), nullable=True, comment='Published WordPress post URL'))
    op.add_column('content', sa.Column('wordpress_published_at', sa.DateTime(timezone=True), nullable=True, comment='When published to WordPress'))
    
    # 3. Update title and slug columns with comments
    op.alter_column('content', 'title', comment='SEO-optimized article title')
    op.alter_column('content', 'slug', comment='URL-friendly slug')
    op.alter_column('content', 'body_markdown', comment='Main article body in Markdown')
    op.alter_column('content', 'body_html', comment='Main article body in HTML (converted from markdown)')
    op.alter_column('content', 'status', comment='draft, ready, published')
    
    # 4. Drop columns that are no longer needed
    op.drop_column('content', 'assigned_to_user_id')
    op.drop_column('content', 'author_id')
    op.drop_column('content', 'featured_image_id')
    op.drop_column('content', 'content_format')
    op.drop_column('content', 'metadata_json')
    op.drop_column('content', 'tracking_json')
    op.drop_column('content', 'ai_config_json')
    op.drop_column('content', 'structure_json')
    op.drop_column('content', 'research_config_json')
    op.drop_column('content', 'published_at')
    op.drop_column('content', 'submitted_for_review_at')
    op.drop_column('content', 'reviewed_at')
    op.drop_column('content', 'reviewed_by_user_id')
    op.drop_column('content', 'review_notes')


def downgrade() -> None:
    """Downgrade schema"""
    
    # Reverse: Add back dropped columns
    op.add_column('content', sa.Column('review_notes', sa.Text(), nullable=True))
    op.add_column('content', sa.Column('reviewed_by_user_id', sa.UUID(), nullable=True))
    op.add_column('content', sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('content', sa.Column('submitted_for_review_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('content', sa.Column('published_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('content', sa.Column('research_config_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('content', sa.Column('structure_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('content', sa.Column('ai_config_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('content', sa.Column('tracking_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('content', sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('content', sa.Column('content_format', sa.Text(), nullable=True, server_default='Markdown'))
    op.add_column('content', sa.Column('featured_image_id', sa.UUID(), nullable=True))
    op.add_column('content', sa.Column('author_id', sa.UUID(), nullable=True))
    op.add_column('content', sa.Column('assigned_to_user_id', sa.UUID(), nullable=True))
    
    # Remove new columns
    op.drop_column('content', 'wordpress_published_at')
    op.drop_column('content', 'wordpress_url')
    op.drop_column('content', 'wordpress_post_id')
    op.drop_column('content', 'readability_score')
    op.drop_column('content', 'seo_score')
    op.drop_column('content', 'schema_markup')
    op.drop_column('content', 'links_data')
    op.drop_column('content', 'images_data')
    op.drop_column('content', 'secondary_keywords')
    op.drop_column('content', 'tags')
    op.drop_column('content', 'keyphrase_density')
    op.drop_column('content', 'focus_keyphrase')
    op.drop_column('content', 'introduction')
    op.drop_column('content', 'meta_description')
    op.drop_column('content', 'meta_title')
    
    # Drop workspace_integrations table
    op.drop_index(op.f('ix_workspace_integrations_workspace_id'), table_name='workspace_integrations')
    op.drop_index(op.f('ix_workspace_integrations_integration_type'), table_name='workspace_integrations')
    op.drop_table('workspace_integrations')
