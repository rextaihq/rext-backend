"""add knowledge_base_id to knowledge tables

Revision ID: 907fbc89eca2
Revises: 3a62bc9b06b7
Create Date: 2025-10-12 03:28:03.193310

Adds knowledge_base_id foreign key to website, knowledge_files, and text_knowledge tables.
Links existing knowledge items to the default knowledge base created in the previous migration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = '907fbc89eca2'
down_revision: Union[str, Sequence[str], None] = '3a62bc9b06b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add knowledge_base_id to knowledge tables."""

    # Add knowledge_base_id column to website table
    op.add_column(
        'website',
        sa.Column('knowledge_base_id', UUID(as_uuid=True), nullable=True)
    )

    # Add knowledge_base_id column to knowledge_files table
    op.add_column(
        'knowledge_files',
        sa.Column('knowledge_base_id', UUID(as_uuid=True), nullable=True)
    )

    # Add knowledge_base_id column to text_knowledge table
    op.add_column(
        'text_knowledge',
        sa.Column('knowledge_base_id', UUID(as_uuid=True), nullable=True)
    )

    # Link existing knowledge items to default knowledge base
    # Website
    op.execute("""
        UPDATE website w
        SET knowledge_base_id = kb.id
        FROM knowledge_base kb
        WHERE w.workspace_id = kb.workspace_id
        AND kb.type = 'default'
        AND w.knowledge_base_id IS NULL
    """)

    # Knowledge Files
    op.execute("""
        UPDATE knowledge_files kf
        SET knowledge_base_id = kb.id
        FROM knowledge_base kb
        WHERE kf.workspace_id = kb.workspace_id
        AND kb.type = 'default'
        AND kf.knowledge_base_id IS NULL
    """)

    # Text Knowledge
    op.execute("""
        UPDATE text_knowledge tk
        SET knowledge_base_id = kb.id
        FROM knowledge_base kb
        WHERE tk.workspace_id = kb.workspace_id
        AND kb.type = 'default'
        AND tk.knowledge_base_id IS NULL
    """)

    # Now make knowledge_base_id NOT NULL
    op.alter_column('website', 'knowledge_base_id', nullable=False)
    op.alter_column('knowledge_files', 'knowledge_base_id', nullable=False)
    op.alter_column('text_knowledge', 'knowledge_base_id', nullable=False)

    # Add foreign key constraints
    op.create_foreign_key(
        'fk_website_knowledge_base',
        'website',
        'knowledge_base',
        ['knowledge_base_id'],
        ['id'],
        ondelete='CASCADE'
    )

    op.create_foreign_key(
        'fk_knowledge_files_knowledge_base',
        'knowledge_files',
        'knowledge_base',
        ['knowledge_base_id'],
        ['id'],
        ondelete='CASCADE'
    )

    op.create_foreign_key(
        'fk_text_knowledge_knowledge_base',
        'text_knowledge',
        'knowledge_base',
        ['knowledge_base_id'],
        ['id'],
        ondelete='CASCADE'
    )

    # Add indexes for performance
    op.create_index('ix_website_knowledge_base_id', 'website', ['knowledge_base_id'])
    op.create_index('ix_knowledge_files_knowledge_base_id', 'knowledge_files', ['knowledge_base_id'])
    op.create_index('ix_text_knowledge_knowledge_base_id', 'text_knowledge', ['knowledge_base_id'])


def downgrade() -> None:
    """Remove knowledge_base_id from knowledge tables."""

    # Drop indexes
    op.drop_index('ix_text_knowledge_knowledge_base_id', table_name='text_knowledge')
    op.drop_index('ix_knowledge_files_knowledge_base_id', table_name='knowledge_files')
    op.drop_index('ix_website_knowledge_base_id', table_name='website')

    # Drop foreign key constraints
    op.drop_constraint('fk_text_knowledge_knowledge_base', 'text_knowledge', type_='foreignkey')
    op.drop_constraint('fk_knowledge_files_knowledge_base', 'knowledge_files', type_='foreignkey')
    op.drop_constraint('fk_website_knowledge_base', 'website', type_='foreignkey')

    # Drop columns
    op.drop_column('text_knowledge', 'knowledge_base_id')
    op.drop_column('knowledge_files', 'knowledge_base_id')
    op.drop_column('website', 'knowledge_base_id')
