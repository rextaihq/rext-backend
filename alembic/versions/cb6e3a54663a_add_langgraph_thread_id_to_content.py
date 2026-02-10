"""add_langgraph_thread_id_to_content

Revision ID: cb6e3a54663a
Revises: 7aac1cc25fa7
Create Date: 2025-10-10 21:11:55.361472

Adds langgraph_thread_id column to content table for tracking LangGraph workflow execution threads.
This allows rerunning the same thread to maintain context and enables thread-based analytics.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'cb6e3a54663a'
down_revision: Union[str, Sequence[str], None] = '7aac1cc25fa7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add langgraph_thread_id column to content table."""
    op.add_column(
        'content',
        sa.Column(
            'langgraph_thread_id',
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment='LangGraph workflow thread ID for content generation tracking'
        )
    )

    # Create index for efficient thread lookups
    op.create_index(
        'ix_content_langgraph_thread_id',
        'content',
        ['langgraph_thread_id'],
        unique=False
    )


def downgrade() -> None:
    """Remove langgraph_thread_id column from content table."""
    # Drop the index first
    op.drop_index('ix_content_langgraph_thread_id', table_name='content')

    # Then drop the column
    op.drop_column('content', 'langgraph_thread_id')
