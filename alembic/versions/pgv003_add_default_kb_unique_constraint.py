"""Add unique constraint for default knowledge base per workspace

Revision ID: pgv003
Revises: pgv002
Create Date: 2026-02-05

This migration adds a partial unique constraint to prevent race conditions
when creating the default knowledge base for a workspace.

The constraint ensures only one knowledge base with type='default' can exist
per workspace.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "pgv003"
down_revision: Union[str, Sequence[str], None] = "pgv002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add partial unique constraint on (workspace_id, type) where type='default'."""
    # Create a partial unique index (PostgreSQL-specific)
    # This is more efficient than a constraint for this use case
    op.execute(
        """
        CREATE UNIQUE INDEX uq_workspace_default_kb
        ON knowledge_base (workspace_id)
        WHERE type = 'default'
        """
    )


def downgrade() -> None:
    """Remove the partial unique index."""
    op.execute("DROP INDEX IF EXISTS uq_workspace_default_kb")
