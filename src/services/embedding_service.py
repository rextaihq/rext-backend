"""
Async Embedding Service using pgvector

This service handles all vector embedding operations for knowledge items:
- Adding embeddings (chunk content, generate vectors, store in pgvector)
- Deleting embeddings (by knowledge_id, workspace_id, etc.)
- Refreshing embeddings (delete old, add new - for content updates)
- Similarity search (find most relevant chunks for RAG)

Replaces the FAISS-based vector_store.py with PostgreSQL-native operations
via pgvector, providing ACID transactions and async support.
"""

from typing import List, Optional, Dict, Any
from uuid import UUID

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.knowledge_models.embedding_model import KnowledgeEmbedding
from src.utils.embedding import get_embedding
from src.utils.splitter import split_data
from src.utils.logger import logger


class EmbeddingService:
    """
    Service for vector embeddings with pgvector.

    All operations are async and work within SQLAlchemy transactions.
    The service handles chunking, embedding generation, and storage.

    Usage:
        embedding_service = EmbeddingService(db_session)
        chunk_count = await embedding_service.add_embeddings(
            content="Long text to embed...",
            workspace_id=workspace_id,
            knowledge_id=knowledge_id,
            knowledge_type="text"
        )
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize EmbeddingService with database session.

        Args:
            db: SQLAlchemy async session for database operations
        """
        self.db = db
        self._embedding_model = None

    @property
    def embedding_model(self):
        """Lazy-load embedding model (singleton pattern)."""
        if self._embedding_model is None:
            self._embedding_model = get_embedding()
        return self._embedding_model

    async def add_embeddings(
        self,
        content: str,
        workspace_id: UUID,
        knowledge_id: UUID,
        knowledge_type: str,
        knowledge_base_id: Optional[UUID] = None,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Chunk content, generate embeddings, and store in pgvector.

        This method:
        1. Splits content into chunks using RecursiveCharacterTextSplitter
        2. Generates embeddings for all chunks using OpenAI text-embedding-3-small
        3. Stores each chunk + embedding in the knowledge_embeddings table

        Args:
            content: Text content to embed (will be chunked)
            workspace_id: Workspace UUID for multi-tenant isolation
            knowledge_id: Knowledge item UUID (file/text/web)
            knowledge_type: Type of knowledge ('file', 'text', 'web')
            knowledge_base_id: Optional knowledge base UUID
            chunk_size: Maximum characters per chunk (default: 1000)
            chunk_overlap: Overlapping characters between chunks (default: 200)
            metadata: Additional metadata to store with each embedding

        Returns:
            Number of chunks/embeddings created

        Raises:
            Exception: If embedding generation or database operation fails
        """
        if not content or not content.strip():
            logger.warning(
                "Empty content provided for embedding",
                extra={"knowledge_id": str(knowledge_id)},
            )
            return 0

        # Split content into chunks
        chunks = split_data(
            documents=content, chunk_size=chunk_size, overlap=chunk_overlap
        )

        if not chunks:
            logger.warning(
                "No chunks generated from content",
                extra={"knowledge_id": str(knowledge_id), "content_length": len(content)},
            )
            return 0

        # Generate embeddings for all chunks (batch operation)
        chunk_texts = [chunk.page_content for chunk in chunks]

        try:
            embeddings = self.embedding_model.embed_documents(chunk_texts)
        except Exception as e:
            logger.error(
                f"Failed to generate embeddings: {e}",
                extra={"knowledge_id": str(knowledge_id), "chunk_count": len(chunks)},
                exc_info=True,
            )
            raise

        # Create embedding records
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            record = KnowledgeEmbedding(
                workspace_id=workspace_id,
                knowledge_base_id=knowledge_base_id,
                knowledge_id=knowledge_id,
                knowledge_type=knowledge_type,
                chunk_index=i,
                chunk_text=chunk.page_content,
                embedding=embedding,
                metadata={
                    **(metadata or {}),
                    "chunk_id": chunk.metadata.get("chunk_id", i),
                    "total_chunks": len(chunks),
                    "length": len(chunk.page_content),
                },
            )
            self.db.add(record)

        await self.db.flush()

        logger.info(
            f"Added {len(chunks)} embeddings for knowledge item",
            extra={
                "knowledge_id": str(knowledge_id),
                "knowledge_type": knowledge_type,
                "chunk_count": len(chunks),
                "workspace_id": str(workspace_id),
            },
        )
        return len(chunks)

    async def add_embeddings_from_documents(
        self,
        documents: List[Any],
        workspace_id: UUID,
        knowledge_id: UUID,
        knowledge_type: str,
        knowledge_base_id: Optional[UUID] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Generate embeddings from pre-chunked Document objects and store in pgvector.

        Use this method when content has already been chunked (e.g., by
        load_split_file_data for files or web_page_scraper for web content).

        Args:
            documents: List of LangChain Document objects with page_content
            workspace_id: Workspace UUID for multi-tenant isolation
            knowledge_id: Knowledge item UUID (file/text/web)
            knowledge_type: Type of knowledge ('file', 'text', 'web')
            knowledge_base_id: Optional knowledge base UUID
            metadata: Additional metadata to store with each embedding

        Returns:
            Number of embeddings created

        Raises:
            Exception: If embedding generation or database operation fails
        """
        if not documents:
            logger.warning(
                "Empty documents list provided for embedding",
                extra={"knowledge_id": str(knowledge_id)},
            )
            return 0

        # Extract text from Document objects
        chunk_texts = [doc.page_content for doc in documents]

        try:
            embeddings = self.embedding_model.embed_documents(chunk_texts)
        except Exception as e:
            logger.error(
                f"Failed to generate embeddings: {e}",
                extra={"knowledge_id": str(knowledge_id), "chunk_count": len(documents)},
                exc_info=True,
            )
            raise

        # Create embedding records
        for i, (doc, embedding) in enumerate(zip(documents, embeddings)):
            record = KnowledgeEmbedding(
                workspace_id=workspace_id,
                knowledge_base_id=knowledge_base_id,
                knowledge_id=knowledge_id,
                knowledge_type=knowledge_type,
                chunk_index=i,
                chunk_text=doc.page_content,
                embedding=embedding,
                metadata={
                    **(metadata or {}),
                    **(doc.metadata if hasattr(doc, 'metadata') and doc.metadata else {}),
                    "chunk_id": doc.metadata.get("chunk_id", i) if hasattr(doc, 'metadata') and doc.metadata else i,
                    "total_chunks": len(documents),
                    "length": len(doc.page_content),
                },
            )
            self.db.add(record)

        await self.db.flush()

        logger.info(
            f"Added {len(documents)} embeddings from documents for knowledge item",
            extra={
                "knowledge_id": str(knowledge_id),
                "knowledge_type": knowledge_type,
                "chunk_count": len(documents),
                "workspace_id": str(workspace_id),
            },
        )
        return len(documents)

    async def delete_embeddings(
        self,
        knowledge_id: UUID,
        workspace_id: Optional[UUID] = None,
    ) -> int:
        """
        Delete all embeddings for a knowledge item.

        Args:
            knowledge_id: Knowledge item UUID to delete embeddings for
            workspace_id: Optional workspace UUID for additional filtering

        Returns:
            Number of embeddings deleted
        """
        stmt = delete(KnowledgeEmbedding).where(
            KnowledgeEmbedding.knowledge_id == knowledge_id
        )

        if workspace_id:
            stmt = stmt.where(KnowledgeEmbedding.workspace_id == workspace_id)

        result = await self.db.execute(stmt)
        await self.db.flush()

        deleted_count = result.rowcount
        logger.info(
            f"Deleted {deleted_count} embeddings",
            extra={
                "knowledge_id": str(knowledge_id),
                "workspace_id": str(workspace_id) if workspace_id else None,
            },
        )
        return deleted_count

    async def delete_embeddings_by_workspace(
        self,
        workspace_id: UUID,
    ) -> int:
        """
        Delete all embeddings for a workspace.

        Used when deleting a workspace (CASCADE should handle this,
        but this method can be used for explicit cleanup).

        Args:
            workspace_id: Workspace UUID

        Returns:
            Number of embeddings deleted
        """
        stmt = delete(KnowledgeEmbedding).where(
            KnowledgeEmbedding.workspace_id == workspace_id
        )

        result = await self.db.execute(stmt)
        await self.db.flush()

        deleted_count = result.rowcount
        logger.info(
            f"Deleted {deleted_count} embeddings for workspace",
            extra={"workspace_id": str(workspace_id)},
        )
        return deleted_count

    async def delete_embeddings_by_knowledge_base(
        self,
        knowledge_base_id: UUID,
        workspace_id: Optional[UUID] = None,
    ) -> int:
        """
        Delete all embeddings for a knowledge base.

        Args:
            knowledge_base_id: Knowledge base UUID
            workspace_id: Optional workspace UUID for additional filtering

        Returns:
            Number of embeddings deleted
        """
        stmt = delete(KnowledgeEmbedding).where(
            KnowledgeEmbedding.knowledge_base_id == knowledge_base_id
        )

        if workspace_id:
            stmt = stmt.where(KnowledgeEmbedding.workspace_id == workspace_id)

        result = await self.db.execute(stmt)
        await self.db.flush()

        deleted_count = result.rowcount
        logger.info(
            f"Deleted {deleted_count} embeddings for knowledge base",
            extra={
                "knowledge_base_id": str(knowledge_base_id),
                "workspace_id": str(workspace_id) if workspace_id else None,
            },
        )
        return deleted_count

    async def refresh_embeddings(
        self,
        content: str,
        workspace_id: UUID,
        knowledge_id: UUID,
        knowledge_type: str,
        knowledge_base_id: Optional[UUID] = None,
        **kwargs,
    ) -> int:
        """
        Delete existing and re-add embeddings for content updates.

        This ensures the vector store stays in sync when knowledge
        content is updated. Performs delete + add in same transaction.

        Args:
            content: New text content to embed
            workspace_id: Workspace UUID
            knowledge_id: Knowledge item UUID
            knowledge_type: Type of knowledge ('file', 'text', 'web')
            knowledge_base_id: Optional knowledge base UUID
            **kwargs: Additional arguments passed to add_embeddings

        Returns:
            Number of new chunks/embeddings created
        """
        # Delete existing embeddings
        await self.delete_embeddings(
            knowledge_id=knowledge_id, workspace_id=workspace_id
        )

        # Add new embeddings
        return await self.add_embeddings(
            content=content,
            workspace_id=workspace_id,
            knowledge_id=knowledge_id,
            knowledge_type=knowledge_type,
            knowledge_base_id=knowledge_base_id,
            **kwargs,
        )

    async def similarity_search(
        self,
        query: str,
        workspace_id: UUID,
        knowledge_base_id: Optional[UUID] = None,
        knowledge_type: Optional[str] = None,
        knowledge_ids: Optional[List[UUID]] = None,
        limit: int = 10,
        score_threshold: Optional[float] = None,
    ) -> List[KnowledgeEmbedding]:
        """
        Find most similar embeddings to query using cosine distance.

        Uses pgvector's <=> operator for cosine distance (0 = identical, 2 = opposite).

        Args:
            query: Text query to find similar embeddings for
            workspace_id: Workspace UUID (required for multi-tenant isolation)
            knowledge_base_id: Optional filter by knowledge base
            knowledge_type: Optional filter by type ('file', 'text', 'web')
            knowledge_ids: Optional list of specific knowledge IDs to search within
            limit: Maximum number of results (default: 10)
            score_threshold: Optional maximum distance threshold (lower = more similar)

        Returns:
            List of KnowledgeEmbedding objects ordered by similarity (most similar first)
        """
        # Generate query embedding
        try:
            query_embedding = self.embedding_model.embed_query(query)
        except Exception as e:
            logger.error(f"Failed to generate query embedding: {e}", exc_info=True)
            raise

        # Build query with filters
        stmt = select(KnowledgeEmbedding).where(
            KnowledgeEmbedding.workspace_id == workspace_id
        )

        if knowledge_base_id:
            stmt = stmt.where(KnowledgeEmbedding.knowledge_base_id == knowledge_base_id)

        if knowledge_type:
            stmt = stmt.where(KnowledgeEmbedding.knowledge_type == knowledge_type)

        if knowledge_ids:
            stmt = stmt.where(KnowledgeEmbedding.knowledge_id.in_(knowledge_ids))

        # Order by cosine distance (ascending = most similar first)
        stmt = stmt.order_by(
            KnowledgeEmbedding.embedding.cosine_distance(query_embedding)
        ).limit(limit)

        result = await self.db.execute(stmt)
        embeddings = result.scalars().all()

        logger.debug(
            f"Similarity search returned {len(embeddings)} results",
            extra={
                "workspace_id": str(workspace_id),
                "knowledge_base_id": str(knowledge_base_id) if knowledge_base_id else None,
                "knowledge_type": knowledge_type,
                "limit": limit,
            },
        )

        return embeddings

    async def get_embedding_count(
        self,
        workspace_id: UUID,
        knowledge_id: Optional[UUID] = None,
        knowledge_base_id: Optional[UUID] = None,
    ) -> int:
        """
        Get count of embeddings for filtering purposes.

        Args:
            workspace_id: Workspace UUID
            knowledge_id: Optional filter by specific knowledge item
            knowledge_base_id: Optional filter by knowledge base

        Returns:
            Number of embeddings matching the filters
        """
        stmt = select(func.count(KnowledgeEmbedding.id)).where(
            KnowledgeEmbedding.workspace_id == workspace_id
        )

        if knowledge_id:
            stmt = stmt.where(KnowledgeEmbedding.knowledge_id == knowledge_id)

        if knowledge_base_id:
            stmt = stmt.where(KnowledgeEmbedding.knowledge_base_id == knowledge_base_id)

        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def get_embeddings_for_knowledge(
        self,
        knowledge_id: UUID,
        workspace_id: Optional[UUID] = None,
    ) -> List[KnowledgeEmbedding]:
        """
        Get all embeddings for a specific knowledge item.

        Useful for debugging or reconstructing chunked content.

        Args:
            knowledge_id: Knowledge item UUID
            workspace_id: Optional workspace UUID for additional filtering

        Returns:
            List of embeddings ordered by chunk_index
        """
        stmt = select(KnowledgeEmbedding).where(
            KnowledgeEmbedding.knowledge_id == knowledge_id
        )

        if workspace_id:
            stmt = stmt.where(KnowledgeEmbedding.workspace_id == workspace_id)

        stmt = stmt.order_by(KnowledgeEmbedding.chunk_index)

        result = await self.db.execute(stmt)
        return result.scalars().all()
