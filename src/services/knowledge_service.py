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

    async def list_web_knowledge(self, workspace_id: UUID) -> List[Dict[str, Any]]:
        """Return all web knowledge entries for the workspace."""
        result = await self.db.execute(
            select(Website).where(Website.workspace_id == workspace_id)
        )
        return [knowledge.to_dict() for knowledge in result.scalars().all()]

    async def get_web_knowledge(self, workspace_id: UUID, web_id: UUID) -> Dict[str, Any]:
        """Return a single web knowledge entry."""
        knowledge = await self._get_website_or_404(web_id, workspace_id)
        return knowledge.to_dict()

    async def add_web_knowledge(self, workspace_id: UUID, url: str) -> Dict[str, Any]:
        """Create a new web knowledge entry by scraping the provided URL."""
        result = await self.db.execute(
            select(Website).where(
                Website.workspace_id == workspace_id,
                Website.url == url,
            )
        )
        if result.scalar_one_or_none():
            raise DuplicateResourceException(
                resource_type="web_knowledge",
                conflicting_field="url",
                conflicting_value=url,
                message=f"Knowledge for URL {url} already exists in the workspace",
            )

        chunks, results = await web_page_scraper(urls=[url])
        result_entry = results[0] if results else None

        if not result_entry or not getattr(result_entry, "success", False):
            raise WrextValidationException(
                message="Failed to scrape the provided URL",
                field_errors={"url": ["URL could not be scraped or is inaccessible"]},
            )

        content = result_entry.markdown or ""

        knowledge = Website(
            workspace_id=workspace_id,
            url=result_entry.url,
            status="trained",
            char_count=len(content),
            word_count=len(content.split()),
        )
        self.db.add(knowledge)
        await self.db.flush()
        await self.db.refresh(knowledge)

        try:
            logger.info(
                "Adding web knowledge chunks to vector store",
                extra={"workspace_id": str(workspace_id), "url": result_entry.url, "chunks": len(chunks)},
            )
            success_status = add_to_vector_store(
                blog_context=chunks,
                doc_id=f"{str(workspace_id)}_{str(knowledge.id)}",
            )
            if not success_status:
                raise WrextExternalServiceException(
                    message="Failed to insert chunks into vector store",
                    service_name="vector_store",
                    service_error="Insertion returned False",
                )
        except WrextExternalServiceException:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Vector store insertion failed", exc_info=exc)
            raise WrextExternalServiceException(
                message="Failed to process content in vector store",
                service_name="vector_store",
                service_error=str(exc),
            )

        logger.info(
            "Web knowledge created",
            extra={"workspace_id": str(workspace_id), "knowledge_id": str(knowledge.id)},
        )

        return knowledge.to_dict()

    async def update_web_knowledge_title(self, workspace_id: UUID, web_id: UUID, title: str) -> Dict[str, Any]:
        """Update the title for a web knowledge entry."""
        knowledge = await self._get_website_or_404(web_id, workspace_id)
        knowledge.title = title
        await self.db.flush()
        await self.db.refresh(knowledge)
        return knowledge.to_dict()

    async def delete_web_knowledge(self, workspace_id: UUID, web_id: UUID) -> None:
        """Delete web knowledge entry and cleanup vector store."""
        knowledge = await self._get_website_or_404(web_id, workspace_id)

        success_status = delete_vectors(vector_id=f"{str(workspace_id)}_{str(web_id)}")
        if not success_status:
            logger.warning(
                "Failed to delete vectors for web knowledge",
                extra={"workspace_id": str(workspace_id), "knowledge_id": str(web_id)},
            )

        await self.db.delete(knowledge)

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

    async def _get_website_or_404(
        self,
        web_id: UUID,
        workspace_id: UUID
    ) -> Website:
        result = await self.db.execute(
            select(Website).where(Website.id == web_id, Website.workspace_id == workspace_id)
        )
        knowledge = result.scalar_one_or_none()

        if not knowledge:
            raise ResourceNotFoundException(
                resource_type="web_knowledge",
                resource_id=str(web_id),
                context={"workspace_id": str(workspace_id)}
            )

        return knowledge
