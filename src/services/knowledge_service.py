"""
Knowledge Service - Business Logic for Knowledge Operations

This service encapsulates all business logic related to knowledge management,
including file uploads, text knowledge, and web scraping.

Responsibilities:
- File knowledge operations (upload, delete, update)
- Text knowledge operations
- Web knowledge operations
- Vector store integration
- Duplicate detection

Does NOT:
- Handle HTTP requests/responses (that's routes)
- Commit transactions (that's decorators/routes)
- Authentication/authorization (that's decorators)
"""

from typing import List, Optional, Dict, Any
from uuid import UUID
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import UploadFile

from src.api.models.knowledge_models.knowledge_model import KnowledgeFiles, TextKnowledge, Website
from src.utils.logger import logger
from src.utils.file_upload_utils import validate_and_store_file, delete_file
from src.utils.utils import load_split_file_data
from src.utils.vector_store import add_to_vector_store, delete_vectors
from src.utils.helper import web_page_scraper
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    WrextValidationException,
    DuplicateResourceException,
    WrextExternalServiceException
)


class KnowledgeService:
    """Service for knowledge business logic"""

    def __init__(self, db: AsyncSession):
        """
        Initialize KnowledgeService.

        Args:
            db: Async database session
        """
        self.db = db

    async def add_file_knowledge(
        self,
        workspace_id: UUID,
        file: UploadFile,
        allowed_types: List[str],
        max_size_mb: int = 10
    ) -> KnowledgeFiles:
        """
        Add file knowledge to workspace.

        Business Rules:
        - Files are validated for type, size, and content
        - Duplicate detection by file hash
        - File content is extracted and split into chunks
        - Chunks are added to vector store for retrieval

        Args:
            workspace_id: Workspace UUID
            file: Uploaded file
            allowed_types: List of allowed MIME types
            max_size_mb: Maximum file size in MB

        Returns:
            Created KnowledgeFiles object

        Raises:
            DuplicateResourceException: If file already exists (by hash)
            WrextValidationException: If file validation fails
            WrextExternalServiceException: If vector store fails
        """
        # Validate and store file securely
        file_metadata = await validate_and_store_file(
            file=file,
            workspace_id=str(workspace_id),
            allowed_types=allowed_types,
            max_size_mb=max_size_mb,
            enable_virus_scan=False
        )

        # Check for duplicate by hash
        result = await self.db.execute(
            select(KnowledgeFiles).where(
                KnowledgeFiles.file_hash == file_metadata["hash"],
                KnowledgeFiles.workspace_id == workspace_id
            )
        )
        existing_knowledge = result.scalar_one_or_none()
        if existing_knowledge:
            # Delete uploaded file (duplicate)
            await delete_file(file_metadata["secure_path"])
            raise DuplicateResourceException(
                resource_type="FileKnowledge",
                conflicting_field="file_hash",
                conflicting_value=file_metadata["hash"],
                message="File already exists in knowledge base (duplicate content detected)"
            )

        # Extract text from file
        chunks = load_split_file_data(file_metadata["secure_path"])

        if len(chunks) == 0:
            raise WrextValidationException(
                message="Failed to extract content from the file",
                field_errors={"file": ["No content could be extracted from file"]}
            )

        # Save metadata in DB
        new_knowledge = KnowledgeFiles(
            workspace_id=workspace_id,
            file_name=file_metadata["safe_filename"],
            file_type=file_metadata["mime_type"],
            file_size=file_metadata["size"],
            file_path=file_metadata["secure_path"],
            file_hash=file_metadata["hash"],
            mime_type=file_metadata["mime_type"],
            chunk_count=len(chunks)
        )
        self.db.add(new_knowledge)
        await self.db.flush()
        await self.db.refresh(new_knowledge)

        # Add to vector store
        try:
            logger.info(f"Inserting {len(chunks)} chunks into vector store")
            success_status = add_to_vector_store(
                blog_context=chunks,
                doc_id=f"{str(workspace_id)}_{str(new_knowledge.id)}"
            )
            if not success_status:
                raise WrextExternalServiceException(
                    message="Failed to insert chunks into vector store",
                    service_name="vector_store",
                    service_error="Insertion returned False"
                )
        except WrextExternalServiceException:
            raise
        except Exception as e:
            logger.error(f"Error building vector store: {e}")
            raise WrextExternalServiceException(
                message="Failed to build vector store from file content",
                service_name="vector_store",
                service_error=str(e)
            )

        logger.info(
            f"File knowledge created: {new_knowledge.id}",
            extra={"workspace_id": str(workspace_id), "filename": file_metadata["safe_filename"]}
        )

        return new_knowledge

    async def delete_file_knowledge(
        self,
        file_id: UUID,
        workspace_id: UUID
    ) -> None:
        """
        Delete file knowledge from workspace.

        Args:
            file_id: File knowledge UUID
            workspace_id: Workspace UUID (for verification)

        Raises:
            ResourceNotFoundException: If file knowledge not found
        """
        knowledge = await self._get_file_knowledge_or_404(file_id, workspace_id)

        # Delete from vector store
        success_status = delete_vectors(vector_id=f"{str(workspace_id)}_{str(file_id)}")
        if not success_status:
            logger.warning(f"Failed to delete vectors for file {file_id}")

        # Delete the physical file from storage
        if knowledge.file_path:
            try:
                await delete_file(knowledge.file_path)
                logger.info(f"Deleted physical file: {knowledge.file_path}")
            except Exception as e:
                logger.warning(f"Failed to delete physical file {knowledge.file_path}: {e}")

        # Delete from database
        await self.db.delete(knowledge)

        logger.info(
            f"File knowledge deleted: {file_id}",
            extra={"workspace_id": str(workspace_id)}
        )

    async def add_text_knowledge(
        self,
        workspace_id: UUID,
        title: str,
        content: str
    ) -> TextKnowledge:
        """
        Add text knowledge to workspace.

        Args:
            workspace_id: Workspace UUID
            title: Knowledge title
            content: Knowledge content

        Returns:
            Created TextKnowledge object
        """
        # Split content into chunks
        chunks = [content]  # Simplified - should use proper chunking

        # Save to database
        new_knowledge = TextKnowledge(
            workspace_id=workspace_id,
            title=title,
            content=content
        )
        self.db.add(new_knowledge)
        await self.db.flush()
        await self.db.refresh(new_knowledge)

        # Add to vector store
        add_to_vector_store(
            blog_context=chunks,
            doc_id=f"{str(workspace_id)}_{str(new_knowledge.id)}"
        )

        logger.info(
            f"Text knowledge created: {new_knowledge.id}",
            extra={"workspace_id": str(workspace_id), "title": title}
        )

        return new_knowledge

    async def delete_text_knowledge(
        self,
        knowledge_id: UUID,
        workspace_id: UUID
    ) -> None:
        """
        Delete text knowledge from workspace.

        Args:
            knowledge_id: Text knowledge UUID
            workspace_id: Workspace UUID (for verification)

        Raises:
            ResourceNotFoundException: If text knowledge not found
        """
        result = await self.db.execute(
            select(TextKnowledge).where(
                TextKnowledge.id == knowledge_id,
                TextKnowledge.workspace_id == workspace_id
            )
        )
        knowledge = result.scalar_one_or_none()

        if not knowledge:
            raise ResourceNotFoundException(
                resource_type="TextKnowledge",
                resource_id=str(knowledge_id)
            )

        # Delete from vector store
        delete_vectors(vector_id=f"{str(workspace_id)}_{str(knowledge_id)}")

        # Delete from database
        await self.db.delete(knowledge)

        logger.info(
            f"Text knowledge deleted: {knowledge_id}",
            extra={"workspace_id": str(workspace_id)}
        )

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    async def _get_file_knowledge_or_404(
        self,
        file_id: UUID,
        workspace_id: UUID
    ) -> KnowledgeFiles:
        """
        Get file knowledge by ID or raise 404.

        Args:
            file_id: File knowledge UUID
            workspace_id: Workspace UUID (for verification)

        Returns:
            KnowledgeFiles object

        Raises:
            ResourceNotFoundException: If file knowledge not found
        """
        result = await self.db.execute(
            select(KnowledgeFiles).where(
                KnowledgeFiles.id == file_id,
                KnowledgeFiles.workspace_id == workspace_id
            )
        )
        knowledge = result.scalar_one_or_none()

        if not knowledge:
            raise ResourceNotFoundException(
                resource_type="FileKnowledge",
                resource_id=str(file_id)
            )

        return knowledge
