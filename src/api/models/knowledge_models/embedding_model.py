"""
Knowledge Embedding Model for pgvector Storage

This model stores vector embeddings for knowledge items (files, text, web content)
using PostgreSQL's pgvector extension.

Replaces the previous FAISS-based vector store with database-native storage,
providing ACID transactions, SQL filtering, and CASCADE deletes.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional, List
from uuid import uuid4

from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from src.api.database.base import Base
from src.api.models.base import SerializableMixin


class KnowledgeEmbedding(Base, SerializableMixin):
    """
    Vector embedding for knowledge items (file, text, web).

    Each knowledge item can have multiple embeddings (one per chunk).
    The embedding column stores a 1536-dimensional vector from
    OpenAI's text-embedding-3-small model.

    Attributes:
        id: Unique identifier for the embedding
        workspace_id: Foreign key to workspace (CASCADE delete)
        knowledge_base_id: Foreign key to knowledge base (CASCADE delete)
        knowledge_id: UUID of the source knowledge item (file/text/web)
        knowledge_type: Type of knowledge ('file', 'text', 'web')
        chunk_index: Zero-based index of this chunk within the source
        chunk_text: The actual text content of this chunk
        embedding: 1536-dimensional vector from text-embedding-3-small
        metadata: Additional metadata (chunk_id, total_chunks, length, etc.)
        created_at: Timestamp when embedding was created
    """

    __tablename__ = "knowledge_embeddings"
    __table_args__ = (
        UniqueConstraint("knowledge_id", "chunk_index", name="uq_knowledge_chunk"),
    )

    # Primary key
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        unique=True,
        nullable=False,
    )

    # Foreign keys with CASCADE delete
    workspace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspace.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    knowledge_base_id = Column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_base.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Knowledge item reference (not a FK since it could be file/text/web)
    knowledge_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    knowledge_type = Column(
        String(20), nullable=False
    )  # 'file', 'text', 'web'

    # Chunk data
    chunk_index = Column(Integer, nullable=False)
    chunk_text = Column(Text, nullable=False)

    # Vector embedding - 1536 dimensions for text-embedding-3-small
    embedding = Column(Vector(1536), nullable=False)

    # Metadata (chunk_id, total_chunks, length, source-specific data)
    metadata = Column(JSONB, nullable=True)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    workspace = relationship("WorkspaceModel", back_populates="knowledge_embeddings")
    knowledge_base = relationship("KnowledgeBase", back_populates="knowledge_embeddings")

    def to_dict(
        self,
        include_embedding: bool = False,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Custom serialization that excludes embedding by default.

        The embedding vector is large (1536 floats) and usually not needed
        in API responses. Set include_embedding=True to include it.

        Args:
            include_embedding: Whether to include the embedding vector
            **kwargs: Additional arguments passed to parent to_dict()

        Returns:
            Dictionary with embedding data (embedding excluded by default)
        """
        # Exclude embedding by default (it's large and rarely needed in responses)
        exclude = kwargs.pop("exclude", [])
        if not include_embedding and "embedding" not in exclude:
            exclude.append("embedding")

        data = super().to_dict(exclude=exclude, **kwargs)

        # Add computed fields
        data["embedding_dimensions"] = 1536
        data["has_embedding"] = self.embedding is not None

        return data

    @property
    def content_preview(self) -> str:
        """Return first 200 characters of chunk text for debugging."""
        if not self.chunk_text:
            return ""
        return self.chunk_text[:200] + ("..." if len(self.chunk_text) > 200 else "")
