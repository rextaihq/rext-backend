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
    """Add file security fields to knowledge_files table (idempotent)."""
    from sqlalchemy import inspect
    
    bind = op.get_bind()
    inspector = inspect(bind)
    
    # Check if table exists
    tables = inspector.get_table_names()
    if 'knowledge_files' not in tables:
        print("⚠️  knowledge_files table doesn't exist yet, skipping security fields migration")
        return
    
    # Get existing columns
    columns = [c['name'] for c in inspector.get_columns('knowledge_files')]
    
    # Add new security columns only if they don't exist
    if 'file_hash' not in columns:
        op.add_column('knowledge_files', sa.Column('file_hash', sa.String(64), nullable=True))
    if 'mime_type' not in columns:
        op.add_column('knowledge_files', sa.Column('mime_type', sa.String(100), nullable=True))
    if 'chunk_count' not in columns:
        op.add_column('knowledge_files', sa.Column('chunk_count', sa.Integer(), nullable=True))

    # Check if index exists before adding
    indexes = [idx['name'] for idx in inspector.get_indexes('knowledge_files')]
    if 'ix_knowledge_files_hash' not in indexes:
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
