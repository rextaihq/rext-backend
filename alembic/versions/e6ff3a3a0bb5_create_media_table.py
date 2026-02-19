"""create_media_table

Create media table for file upload management with support for:
- Multiple file types (images, documents, videos)
- Multiple storage backends (S3, local)
- Image processing (thumbnails, optimization)
- Metadata and organization (folders, tags)
- Access control (public, private, workspace)

Revision ID: e6ff3a3a0bb5
Revises: cc3fe534b293
Create Date: 2025-10-12 23:30:40.594577

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e6ff3a3a0bb5'
down_revision: Union[str, Sequence[str], None] = 'cc3fe534b293'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create media table and indexes."""
    op.create_table(
        'media',
        # Primary key
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),

        # Foreign keys
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),

        # File information
        sa.Column('filename', sa.String(length=255), nullable=False, comment='Generated unique filename'),
        sa.Column('original_filename', sa.String(length=255), nullable=False, comment='Original upload filename'),
        sa.Column('file_type', sa.String(length=100), nullable=False, comment='MIME type (e.g., image/jpeg)'),
        sa.Column('file_size', sa.BigInteger(), nullable=False, comment='File size in bytes'),
        sa.Column('file_extension', sa.String(length=10), nullable=True, comment='File extension (e.g., .jpg)'),

        # Storage
        sa.Column('storage_backend', sa.String(length=20), server_default='r2', comment='Storage backend: r2 (Cloudflare), local'),
        sa.Column('storage_path', sa.String(length=500), nullable=False, comment='R2 key or local path'),
        sa.Column('storage_bucket', sa.String(length=100), nullable=True, comment='R2 bucket name'),
        sa.Column('cdn_url', sa.String(length=500), nullable=True, comment='CDN URL if available'),
        sa.Column('public_url', sa.String(length=500), nullable=True, comment='Public access URL'),

        # Metadata
        sa.Column('title', sa.String(length=255), nullable=True, comment='User-provided title'),
        sa.Column('description', sa.Text(), nullable=True, comment='User-provided description'),
        sa.Column('alt_text', sa.String(length=500), nullable=True, comment='Alt text for images (accessibility)'),
        sa.Column('file_metadata', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', comment='Additional metadata: {width, height, duration, format, etc.}'),

        # Organization
        sa.Column('folder', sa.String(length=255), nullable=True, comment='Virtual folder path (e.g., /images/products)'),
        sa.Column('tags', postgresql.ARRAY(sa.String()), server_default='{}', comment='Tags for search and organization'),

        # Access control
        sa.Column('is_public', sa.Boolean(), server_default='false', comment='Whether file is publicly accessible'),
        sa.Column('access_level', sa.String(length=20), server_default='private', comment='Access level: public, private, workspace'),

        # Image-specific fields (nullable for non-images)
        sa.Column('thumbnail_path', sa.String(length=500), nullable=True, comment='Thumbnail storage path'),
        sa.Column('thumbnail_url', sa.String(length=500), nullable=True, comment='Thumbnail public URL'),
        sa.Column('width', sa.Integer(), nullable=True, comment='Image width in pixels'),
        sa.Column('height', sa.Integer(), nullable=True, comment='Image height in pixels'),

        # Processing status
        sa.Column('processing_status', sa.String(length=20), server_default='pending', comment='Processing status: pending, processing, completed, failed'),
        sa.Column('processing_error', sa.Text(), nullable=True, comment='Error message if processing failed'),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, onupdate=sa.text('NOW()')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, comment='Soft delete timestamp'),

        # Foreign key constraints
        sa.ForeignKeyConstraint(['workspace_id'], ['workspace.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )

    # Create indexes for performance
    op.create_index('ix_media_workspace_id', 'media', ['workspace_id'])
    op.create_index('ix_media_user_id', 'media', ['user_id'])
    op.create_index('ix_media_file_type', 'media', ['file_type'])
    op.create_index('ix_media_folder', 'media', ['folder'])
    op.create_index('ix_media_created_at', 'media', ['created_at'])
    op.create_index('ix_media_processing_status', 'media', ['processing_status'])

    # Full-text search index on title and description (PostgreSQL)
    op.execute("""
        CREATE INDEX ix_media_search ON media
        USING gin(to_tsvector('english', coalesce(title, '') || ' ' || coalesce(description, '')))
    """)


def downgrade() -> None:
    """Drop media table and indexes."""
    # Drop full-text search index
    op.execute("DROP INDEX IF EXISTS ix_media_search")

    # Drop other indexes
    op.drop_index('ix_media_processing_status', table_name='media')
    op.drop_index('ix_media_created_at', table_name='media')
    op.drop_index('ix_media_folder', table_name='media')
    op.drop_index('ix_media_file_type', table_name='media')
    op.drop_index('ix_media_user_id', table_name='media')
    op.drop_index('ix_media_workspace_id', table_name='media')

    # Drop table
    op.drop_table('media')
