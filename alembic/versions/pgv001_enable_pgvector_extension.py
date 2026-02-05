"""Enable pgvector extension for vector storage

Revision ID: pgv001
Revises: 1ce340a722d6
Create Date: 2026-02-05

This migration enables the pgvector extension in PostgreSQL 17
to support vector similarity search for knowledge embeddings.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "pgv001"
down_revision: Union[str, Sequence[str], None] = "1ce340a722d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Enable pgvector extension."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    """Disable pgvector extension."""
    op.execute("DROP EXTENSION IF EXISTS vector")
