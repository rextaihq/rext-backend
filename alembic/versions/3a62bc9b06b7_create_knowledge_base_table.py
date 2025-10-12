"""create knowledge base table

Revision ID: 3a62bc9b06b7
Revises: 48016a71eb87
Create Date: 2025-10-12 03:23:34.850497

Creates knowledge_base table to group knowledge items (web, file, text).
This enables hierarchical organization: Workspace -> Knowledge Bases -> Knowledge Items.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
import uuid


# revision identifiers, used by Alembic.
revision: str = '3a62bc9b06b7'
down_revision: Union[str, Sequence[str], None] = '48016a71eb87'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create knowledge_base table."""
    # Create knowledge_base table
    op.create_table(
        'knowledge_base',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False),
        sa.Column('workspace_id', UUID(as_uuid=True), sa.ForeignKey('workspace.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('type', sa.String(50), nullable=False, comment='Type: default, custom'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now(), nullable=True),
    )

    # Add indexes for performance
    op.create_index('ix_knowledge_base_workspace_id', 'knowledge_base', ['workspace_id'])
    op.create_index('ix_knowledge_base_type', 'knowledge_base', ['type'])

    # Create a default knowledge base for each existing workspace
    # This ensures backward compatibility
    op.execute("""
        INSERT INTO knowledge_base (id, workspace_id, name, description, type, created_at)
        SELECT
            gen_random_uuid(),
            id,
            'Default Knowledge Base',
            'Automatically created default knowledge base for existing workspace',
            'default',
            NOW()
        FROM workspace
    """)


def downgrade() -> None:
    """Drop knowledge_base table."""
    # Drop indexes first
    op.drop_index('ix_knowledge_base_type', table_name='knowledge_base')
    op.drop_index('ix_knowledge_base_workspace_id', table_name='knowledge_base')

    # Drop the table (CASCADE will handle dependent rows)
    op.drop_table('knowledge_base')
