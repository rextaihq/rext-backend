"""Create knowledge_embeddings table for pgvector storage

Revision ID: pgv002
Revises: pgv001
Create Date: 2026-02-05

This migration creates the knowledge_embeddings table to store vector embeddings
for knowledge items (files, text, web content) using pgvector.

Replaces the FAISS-based vector store with PostgreSQL-native storage.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision: str = "pgv002"
down_revision: Union[str, Sequence[str], None] = "pgv001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create knowledge_embeddings table with pgvector column and indexes."""
    # Create the table
    op.create_table(
        "knowledge_embeddings",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "workspace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workspace.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "knowledge_base_id",
            UUID(as_uuid=True),
            sa.ForeignKey("knowledge_base.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("knowledge_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "knowledge_type", sa.String(20), nullable=False
        ),  # 'file', 'text', 'web'
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("chunk_text", sa.Text, nullable=False),
        # pgvector column - 1536 dimensions for text-embedding-3-small
        # We'll use raw SQL to create this column since alembic doesn't natively support vector
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.UniqueConstraint("knowledge_id", "chunk_index", name="uq_knowledge_chunk"),
    )

    # Add the vector column using raw SQL (pgvector type)
    op.execute(
        "ALTER TABLE knowledge_embeddings ADD COLUMN embedding vector(1536) NOT NULL"
    )

    # Create HNSW index for fast similarity search
    # m=16: number of bi-directional links (higher = better recall, more memory)
    # ef_construction=64: size of dynamic candidate list during construction
    op.execute(
        """
        CREATE INDEX ix_knowledge_embeddings_hnsw
        ON knowledge_embeddings
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )

    # Create B-tree indexes for filtering
    op.create_index(
        "ix_knowledge_embeddings_workspace_id",
        "knowledge_embeddings",
        ["workspace_id"],
    )
    op.create_index(
        "ix_knowledge_embeddings_knowledge_base_id",
        "knowledge_embeddings",
        ["knowledge_base_id"],
    )
    op.create_index(
        "ix_knowledge_embeddings_knowledge_id",
        "knowledge_embeddings",
        ["knowledge_id"],
    )
    op.create_index(
        "ix_knowledge_embeddings_knowledge_type",
        "knowledge_embeddings",
        ["knowledge_type"],
    )

    # Composite index for common query pattern (workspace + type filtering)
    op.create_index(
        "ix_knowledge_embeddings_workspace_type",
        "knowledge_embeddings",
        ["workspace_id", "knowledge_type"],
    )


def downgrade() -> None:
    """Drop knowledge_embeddings table and indexes."""
    op.drop_index(
        "ix_knowledge_embeddings_workspace_type", table_name="knowledge_embeddings"
    )
    op.drop_index(
        "ix_knowledge_embeddings_knowledge_type", table_name="knowledge_embeddings"
    )
    op.drop_index(
        "ix_knowledge_embeddings_knowledge_id", table_name="knowledge_embeddings"
    )
    op.drop_index(
        "ix_knowledge_embeddings_knowledge_base_id", table_name="knowledge_embeddings"
    )
    op.drop_index(
        "ix_knowledge_embeddings_workspace_id", table_name="knowledge_embeddings"
    )
    op.execute("DROP INDEX IF EXISTS ix_knowledge_embeddings_hnsw")
    op.drop_table("knowledge_embeddings")
