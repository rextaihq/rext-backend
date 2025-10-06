"""add_file_security_fields

Revision ID: 26ad95072497
Revises: c3d4e5f6g7h8
Create Date: 2025-10-06 09:20:12.349777

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '26ad95072497'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6g7h8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add file security fields to knowledge_files table."""
    # Add new security columns
    op.add_column('knowledge_files', sa.Column('file_hash', sa.String(64), nullable=True))
    op.add_column('knowledge_files', sa.Column('mime_type', sa.String(100), nullable=True))
    op.add_column('knowledge_files', sa.Column('chunk_count', sa.Integer(), nullable=True))

    # Add index on hash for duplicate detection
    op.create_index('ix_knowledge_files_hash', 'knowledge_files', ['file_hash'])


def downgrade() -> None:
    """Remove file security fields from knowledge_files table."""
    # Drop index
    op.drop_index('ix_knowledge_files_hash', 'knowledge_files')

    # Drop columns
    op.drop_column('knowledge_files', 'chunk_count')
    op.drop_column('knowledge_files', 'mime_type')
    op.drop_column('knowledge_files', 'file_hash')
