"""add_media_relationships_to_content

Adds media relationship support to content:
1. featured_image_id column in content table (for hero/thumbnail images)
2. content_media junction table (for tracking all media used in content body)

This enables:
- Setting a featured image for content
- Tracking which media files are used in content
- Preventing deletion of media that's in use
- Finding content that uses specific media

Revision ID: f0102d372d26
Revises: c4ca7a82ebe9
Create Date: 2025-10-15 08:30:18.763514

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f0102d372d26'
down_revision: Union[str, Sequence[str], None] = 'c4ca7a82ebe9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add media relationships to content."""

    # Add featured_image_id to content table
    op.add_column(
        'content',
        sa.Column(
            'featured_image_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('media.id', ondelete='SET NULL'),
            nullable=True,
            comment='Featured/hero image for the content (thumbnail, social share, etc.)'
        )
    )

    # Create index on featured_image_id for faster lookups
    op.create_index(
        'ix_content_featured_image_id',
        'content',
        ['featured_image_id']
    )

    # Create content_media junction table
    op.create_table(
        'content_media',
        sa.Column(
            'id',
            postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'),
            primary_key=True,
            nullable=False
        ),
        sa.Column(
            'content_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('content.id', ondelete='CASCADE'),
            nullable=False,
            index=True,
            comment='Content that uses this media'
        ),
        sa.Column(
            'media_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('media.id', ondelete='CASCADE'),
            nullable=False,
            index=True,
            comment='Media file used in content'
        ),
        sa.Column(
            'usage_type',
            sa.String(50),
            nullable=True,
            comment='How media is used: inline, gallery, attachment, etc.'
        ),
        sa.Column(
            'position',
            sa.Integer,
            nullable=True,
            comment='Position in content (for ordering)'
        ),
        sa.Column(
            'created_at',
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text('now()'),
            nullable=False
        ),
        # Composite unique constraint - same media can't be added to same content twice
        sa.UniqueConstraint('content_id', 'media_id', name='uq_content_media')
    )

    # Create index for reverse lookup (find all content using a media file)
    op.create_index(
        'ix_content_media_media_id_content_id',
        'content_media',
        ['media_id', 'content_id']
    )


def downgrade() -> None:
    """Remove media relationships from content."""

    # Drop junction table
    op.drop_index('ix_content_media_media_id_content_id', table_name='content_media')
    op.drop_table('content_media')

    # Drop featured_image_id column
    op.drop_index('ix_content_featured_image_id', table_name='content')
    op.drop_column('content', 'featured_image_id')
