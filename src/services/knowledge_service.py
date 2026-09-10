"""
Knowledge Service - Business Logic for Knowledge Operations

This service encapsulates all business logic related to knowledge management,
including file uploads, text knowledge, and web scraping with vector embeddings.

Following LangChain v1.0 and LangGraph v1.0 Best Practices (Released Oct 2025):
- Uses RecursiveCharacterTextSplitter for semantic text chunking (LCEL pattern)
- BAAI/bge-small-en embeddings (384-dim, optimized for retrieval)
- FAISS IndexFlatL2 for exact similarity search
- Document objects with metadata for multi-tenant isolation
- Batch processing with async operations for efficiency
- Robust error handling with try/except blocks

Vector Store Integration (Supports Multiple KBs per Workspace):
- Text is split into 1000-char chunks with 200-char overlap
- Each chunk becomes a Document with workspace_id + knowledge_id metadata
- Documents are embedded and stored in FAISS index
- Multi-level isolation: workspace → knowledge_base → knowledge_item
- UUID-based document IDs prevent collisions

Responsibilities:
- File knowledge operations (upload, delete, update)
- Text knowledge operations (create, update, delete)
- Web knowledge operations (scrape, process, index)
- Vector store integration (add, delete, query)
- Duplicate detection (file hash, URL uniqueness)
- Text chunking and embedding generation

Does NOT:
- Handle HTTP requests/responses (that's routes)
- Commit transactions (that's decorators/routes)
- Authentication/authorization (that's decorators)
- Direct vector search (that's RAG/content generation services)
"""

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.config import get_settings
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    ResourceNotFoundException,
    RextExternalServiceException,
    RextValidationException,
)
from src.api.models.knowledge_models.knowledge_model import (
    KnowledgeBase,
    KnowledgeFiles,
    TextKnowledge,
    Website,
)
from src.services.knowledge_base_service import KnowledgeBaseService
from src.utils.file_upload_utils import delete_file, validate_and_store_file
from src.utils.helper import web_page_scraper
from src.utils.logger import logger
from src.utils.splitter import split_data
from src.utils.utils import load_split_file_data
from src.utils.vector_store import add_to_vector_store, delete_vectors

# Get settings instance
settings = get_settings()


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
        max_size_mb: int = 10,
        knowledge_base_id: Optional[UUID] = None,
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
            knowledge_base_id: Optional knowledge base UUID (uses default if None)

        Returns:
            Created KnowledgeFiles object

        Raises:
            DuplicateResourceException: If file already exists (by hash)
            RextValidationException: If file validation fails
            RextExternalServiceException: If vector store fails
        """
        # Get or use default knowledge base
        if knowledge_base_id is None:
            kb_service = KnowledgeBaseService(self.db)
            kb = await kb_service.get_default_knowledge_base(workspace_id)
            knowledge_base_id = kb.id
        # Validate and store file securely
        file_metadata = await validate_and_store_file(
            file=file,
            workspace_id=str(workspace_id),
            allowed_types=allowed_types,
            max_size_mb=max_size_mb,
            enable_virus_scan=False,
        )

        # Check for duplicate by hash
        result = await self.db.execute(
            select(KnowledgeFiles).where(
                KnowledgeFiles.file_hash == file_metadata["hash"],
                KnowledgeFiles.workspace_id == workspace_id,
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
                message="File already exists in knowledge base (duplicate content detected)",
            )

        # Extract text from file
        chunks = load_split_file_data(file_metadata["secure_path"])

        if len(chunks) == 0:
            raise RextValidationException(
                message="Failed to extract content from the file",
                field_errors={"file": ["No content could be extracted from file"]},
            )

        # Save metadata in DB
        new_knowledge = KnowledgeFiles(
            workspace_id=workspace_id,
            knowledge_base_id=knowledge_base_id,
            file_name=file_metadata["safe_filename"],
            file_type=file_metadata["mime_type"],
            file_size=file_metadata["size"],
            file_path=file_metadata["secure_path"],
            file_hash=file_metadata["hash"],
            mime_type=file_metadata["mime_type"],
            chunk_count=len(chunks),
        )
        self.db.add(new_knowledge)
        await self.db.flush()
        await self.db.refresh(new_knowledge)

        # Add to vector store with knowledge item metadata
        try:
            logger.info(f"Inserting {len(chunks)} chunks into vector store")
            success_status = add_to_vector_store(
                blog_context=chunks,
                workspace_id=str(workspace_id),
                knowledge_base_id=str(knowledge_base_id) if knowledge_base_id else None,
                knowledge_id=str(new_knowledge.id),
                knowledge_type="file",
            )
            if not success_status:
                raise RextExternalServiceException(
                    message="Failed to insert chunks into vector store",
                    service_name="vector_store",
                    service_error="Insertion returned False",
                )
        except RextExternalServiceException:
            raise
        except Exception as e:
            logger.error(f"Error building vector store: {e}")
            raise RextExternalServiceException(
                message="Failed to build vector store from file content",
                service_name="vector_store",
                service_error=str(e),
            )

        logger.info(
            f"File knowledge created: {new_knowledge.id}",
            extra={"workspace_id": str(workspace_id), "filename": file_metadata["safe_filename"]},
        )

        # Send knowledge base processing completed email (async, don't block)
        try:
            await self._send_kb_processing_completed_email(
                workspace_id=workspace_id,
                knowledge_base_id=knowledge_base_id,
                file_name=file_metadata["safe_filename"],
                chunks_count=len(chunks),
            )
        except Exception as e:
            logger.error(f"Failed to send KB processing completed email: {str(e)}")
            # Don't fail the upload if email fails

        return new_knowledge

    async def delete_file_knowledge(self, file_id: UUID, workspace_id: UUID) -> None:
        """
        Delete file knowledge from workspace.

        Args:
            file_id: File knowledge UUID
            workspace_id: Workspace UUID (for verification)

        Raises:
            ResourceNotFoundException: If file knowledge not found
        """
        knowledge = await self._get_file_knowledge_or_404(file_id, workspace_id)

        # Delete from vector store using granular knowledge_id filter
        success_status = delete_vectors(workspace_id=str(workspace_id), knowledge_id=str(file_id))
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

        logger.info(f"File knowledge deleted: {file_id}", extra={"workspace_id": str(workspace_id)})

    async def list_file_knowledge(
        self,
        workspace_id: UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[List[Dict[str, Any]], int]:
        """
        Return paginated file knowledge entries for a workspace.

        Args:
            workspace_id: Workspace UUID
            limit: Maximum number of items to return (default 20)
            offset: Number of items to skip (default 0)

        Returns:
            Tuple of (list of file knowledge dicts, total count)
        """
        from sqlalchemy import func

        # Get total count
        count_result = await self.db.execute(
            select(func.count())
            .select_from(KnowledgeFiles)
            .where(KnowledgeFiles.workspace_id == workspace_id)
        )
        total_count = count_result.scalar()

        # Get paginated results
        result = await self.db.execute(
            select(KnowledgeFiles)
            .where(KnowledgeFiles.workspace_id == workspace_id)
            .order_by(KnowledgeFiles.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        items = [knowledge.to_dict() for knowledge in result.scalars().all()]

        return items, total_count

    async def get_file_knowledge(self, workspace_id: UUID, file_id: UUID) -> Dict[str, Any]:
        """Return a single file knowledge entry."""
        knowledge = await self._get_file_knowledge_or_404(file_id, workspace_id)
        return knowledge.to_dict()

    async def update_file_knowledge_name(
        self,
        workspace_id: UUID,
        file_id: UUID,
        name: str,
    ) -> Dict[str, Any]:
        """
        Update the display name for a file knowledge entry.

        Args:
            workspace_id: Workspace UUID
            file_id: Knowledge file UUID
            name: New display name
        """
        knowledge = await self._get_file_knowledge_or_404(file_id, workspace_id)
        knowledge.file_name = name
        await self.db.flush()
        await self.db.refresh(knowledge)

        logger.info(
            "File knowledge name updated",
            extra={
                "workspace_id": str(workspace_id),
                "file_id": str(file_id),
                "name": name,
            },
        )

        return knowledge.to_dict()

    async def add_text_knowledge(
        self,
        workspace_id: UUID,
        title: str,
        content: str,
        knowledge_base_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
    ) -> TextKnowledge:
        """
        Add text knowledge to workspace.

        Args:
            workspace_id: Workspace UUID
            title: Knowledge title
            content: Knowledge content
            knowledge_base_id: Optional knowledge base UUID (uses default if None)
            tags: Optional list of tags
        """
        # Get or use default knowledge base
        if knowledge_base_id is None:
            kb_service = KnowledgeBaseService(self.db)
            kb = await kb_service.get_default_knowledge_base(workspace_id)
            knowledge_base_id = kb.id

        # Split content into chunks
        chunks = split_data(documents=content, chunk_size=1000, overlap=200)

        # Save to database
        new_knowledge = TextKnowledge(
            workspace_id=workspace_id,
            knowledge_base_id=knowledge_base_id,
            title=title,
            content=content,
            tags=tags,
        )
        self.db.add(new_knowledge)
        await self.db.flush()
        await self.db.refresh(new_knowledge)

        # Add to vector store
        add_to_vector_store(
            blog_context=chunks,
            workspace_id=str(workspace_id),
            knowledge_base_id=str(knowledge_base_id) if knowledge_base_id else None,
            knowledge_id=str(new_knowledge.id),
            knowledge_type="text",
        )

        logger.info(
            f"Text knowledge created: {new_knowledge.id}",
            extra={"workspace_id": str(workspace_id), "title": title},
        )

        return new_knowledge

    async def list_text_knowledge(
        self,
        workspace_id: UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[List[Dict[str, Any]], int]:
        """Return paginated text knowledge entries for a workspace."""
        from sqlalchemy import func

        # Get total count
        count_result = await self.db.execute(
            select(func.count())
            .select_from(TextKnowledge)
            .where(TextKnowledge.workspace_id == workspace_id)
        )
        total_count = count_result.scalar()

        # Get paginated results
        result = await self.db.execute(
            select(TextKnowledge)
            .where(TextKnowledge.workspace_id == workspace_id)
            .order_by(TextKnowledge.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        items = [knowledge.to_dict() for knowledge in result.scalars().all()]

        return items, total_count

    async def get_text_knowledge(self, workspace_id: UUID, knowledge_id: UUID) -> Dict[str, Any]:
        """Return a single text knowledge entry."""
        result = await self.db.execute(
            select(TextKnowledge).where(
                TextKnowledge.id == knowledge_id,
                TextKnowledge.workspace_id == workspace_id,
            )
        )
        knowledge = result.scalar_one_or_none()

        if not knowledge:
            raise ResourceNotFoundException(
                resource_type="TextKnowledge",
                resource_id=str(knowledge_id),
            )

        return knowledge.to_dict()

    async def update_text_knowledge(
        self,
        knowledge_id: UUID,
        workspace_id: UUID,
        *,
        title: Optional[str] = None,
        content: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Update metadata for a text knowledge entry.

        Args:
            knowledge_id: Text knowledge UUID
            workspace_id: Workspace UUID
            title: Optional new title
            content: Optional new content
            tags: Optional new tags list (replaces existing tags)
        """
        result = await self.db.execute(
            select(TextKnowledge).where(
                TextKnowledge.id == knowledge_id,
                TextKnowledge.workspace_id == workspace_id,
            )
        )
        knowledge = result.scalar_one_or_none()

        if not knowledge:
            raise ResourceNotFoundException(
                resource_type="TextKnowledge",
                resource_id=str(knowledge_id),
            )

        if title:
            knowledge.title = title

        if content:
            knowledge.content = content

        if tags is not None:
            knowledge.tags = tags

        await self.db.flush()
        await self.db.refresh(knowledge)

        logger.info(
            "Text knowledge updated",
            extra={
                "workspace_id": str(workspace_id),
                "knowledge_id": str(knowledge_id),
            },
        )

        return knowledge.to_dict()

    async def delete_text_knowledge(self, knowledge_id: UUID, workspace_id: UUID) -> None:
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
                TextKnowledge.id == knowledge_id, TextKnowledge.workspace_id == workspace_id
            )
        )
        knowledge = result.scalar_one_or_none()

        if not knowledge:
            raise ResourceNotFoundException(
                resource_type="TextKnowledge", resource_id=str(knowledge_id)
            )

        # Delete from vector store using granular knowledge_id filter
        delete_vectors(workspace_id=str(workspace_id), knowledge_id=str(knowledge_id))

        # Delete from database
        await self.db.delete(knowledge)

        logger.info(
            f"Text knowledge deleted: {knowledge_id}", extra={"workspace_id": str(workspace_id)}
        )

    async def list_web_knowledge(
        self,
        workspace_id: UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[List[Dict[str, Any]], int]:
        """Return paginated web knowledge entries for the workspace."""
        from sqlalchemy import func

        # Get total count
        count_result = await self.db.execute(
            select(func.count()).select_from(Website).where(Website.workspace_id == workspace_id)
        )
        total_count = count_result.scalar()

        # Get paginated results
        result = await self.db.execute(
            select(Website)
            .where(Website.workspace_id == workspace_id)
            .order_by(Website.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        items = [knowledge.to_dict() for knowledge in result.scalars().all()]

        return items, total_count

    async def get_web_knowledge(self, workspace_id: UUID, web_id: UUID) -> Dict[str, Any]:
        """Return a single web knowledge entry."""
        knowledge = await self._get_website_or_404(web_id, workspace_id)
        return knowledge.to_dict()

    async def add_web_knowledge(
        self, workspace_id: UUID, url: str, knowledge_base_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """Create a new web knowledge entry by scraping the provided URL."""
        # Get or use default knowledge base
        if knowledge_base_id is None:
            kb_service = KnowledgeBaseService(self.db)
            kb = await kb_service.get_default_knowledge_base(workspace_id)
            knowledge_base_id = kb.id

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
            raise RextValidationException(
                message="Failed to scrape the provided URL",
                field_errors={"url": ["URL could not be scraped or is inaccessible"]},
            )

        content = result_entry.markdown or ""

        knowledge = Website(
            workspace_id=workspace_id,
            knowledge_base_id=knowledge_base_id,
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
                extra={
                    "workspace_id": str(workspace_id),
                    "url": result_entry.url,
                    "chunks": len(chunks),
                },
            )
            success_status = add_to_vector_store(
                blog_context=chunks,
                workspace_id=str(workspace_id),
                knowledge_base_id=str(knowledge_base_id) if knowledge_base_id else None,
                knowledge_id=str(knowledge.id),
                knowledge_type="web",
            )
            if not success_status:
                raise RextExternalServiceException(
                    message="Failed to insert chunks into vector store",
                    service_name="vector_store",
                    service_error="Insertion returned False",
                )
        except RextExternalServiceException:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Vector store insertion failed", exc_info=exc)
            raise RextExternalServiceException(
                message="Failed to process content in vector store",
                service_name="vector_store",
                service_error=str(exc),
            )

        logger.info(
            "Web knowledge created",
            extra={"workspace_id": str(workspace_id), "knowledge_id": str(knowledge.id)},
        )

        return knowledge.to_dict()

    async def update_web_knowledge_title(
        self, workspace_id: UUID, web_id: UUID, title: str
    ) -> Dict[str, Any]:
        """Update the title for a web knowledge entry."""
        knowledge = await self._get_website_or_404(web_id, workspace_id)
        knowledge.title = title
        await self.db.flush()
        await self.db.refresh(knowledge)
        return knowledge.to_dict()

    async def delete_web_knowledge(self, workspace_id: UUID, web_id: UUID) -> None:
        """Delete web knowledge entry and cleanup vector store."""
        knowledge = await self._get_website_or_404(web_id, workspace_id)

        # Delete from vector store using granular knowledge_id filter
        success_status = delete_vectors(workspace_id=str(workspace_id), knowledge_id=str(web_id))
        if not success_status:
            logger.warning(
                "Failed to delete vectors for web knowledge",
                extra={"workspace_id": str(workspace_id), "knowledge_id": str(web_id)},
            )

        await self.db.delete(knowledge)

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    async def _get_file_knowledge_or_404(self, file_id: UUID, workspace_id: UUID) -> KnowledgeFiles:
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
                KnowledgeFiles.id == file_id, KnowledgeFiles.workspace_id == workspace_id
            )
        )
        knowledge = result.scalar_one_or_none()

        if not knowledge:
            raise ResourceNotFoundException(resource_type="FileKnowledge", resource_id=str(file_id))

        return knowledge

    async def _get_website_or_404(self, web_id: UUID, workspace_id: UUID) -> Website:
        result = await self.db.execute(
            select(Website).where(Website.id == web_id, Website.workspace_id == workspace_id)
        )
        knowledge = result.scalar_one_or_none()

        if not knowledge:
            raise ResourceNotFoundException(
                resource_type="web_knowledge",
                resource_id=str(web_id),
                context={"workspace_id": str(workspace_id)},
            )

        return knowledge

    async def _send_kb_processing_completed_email(
        self, workspace_id: UUID, knowledge_base_id: UUID, file_name: str, chunks_count: int
    ) -> None:
        """Send email notification when knowledge base file processing completes."""

        from emails.templates.knowledge_base.kb_processing_completed import (
            render_kb_processing_completed_email,
        )
        from src.api.models.user_models.users import Users
        from src.api.models.workspace_models.workspace_model import WorkspaceModel
        from src.services.email_service import EmailService

        try:
            # Fetch knowledge base
            result = await self.db.execute(
                select(KnowledgeBase).where(KnowledgeBase.id == knowledge_base_id)
            )
            kb = result.scalar_one_or_none()
            if not kb:
                logger.warning(f"Knowledge base {knowledge_base_id} not found, skipping email")
                return

            # Fetch workspace
            result = await self.db.execute(
                select(WorkspaceModel).where(WorkspaceModel.id == workspace_id)
            )
            workspace = result.scalar_one_or_none()
            if not workspace:
                logger.warning(f"Workspace {workspace_id} not found, skipping email")
                return

            # Fetch workspace owner to send email notification
            from src.api.models.workspace_models.workspace_member import WorkspaceMembers

            result = await self.db.execute(
                select(WorkspaceMembers).where(
                    WorkspaceMembers.workspace_id == workspace_id,
                    WorkspaceMembers.is_default.is_(True),
                )
            )
            owner_member = result.scalar_one_or_none()
            if not owner_member:
                logger.warning(f"No owner found for workspace {workspace_id}, skipping email")
                return

            result = await self.db.execute(select(Users).where(Users.id == owner_member.user_id))
            user = result.scalar_one_or_none()
            if not user:
                logger.warning(f"User {owner_member.user_id} not found, skipping email")
                return

            # Build URLs
            frontend_url = settings.FRONTEND_URL
            dashboard_url = f"{frontend_url}/w/{workspace.slug}/knowledge/{knowledge_base_id}"
            create_content_url = f"{frontend_url}/w/{workspace.slug}/content/new"

            # Render professional email
            user_name = user.full_name or user.display_name or user.email.split("@")[0]
            html_content = render_kb_processing_completed_email(
                user_name=user_name,
                kb_name=kb.name,
                items_processed=chunks_count,
                processing_time="< 1 minute",  # File processing is fast
                workspace_name=workspace.name,
                dashboard_url=dashboard_url,
                create_content_url=create_content_url,
                frontend_url=frontend_url,
            )

            # Send email
            email_service = EmailService(self.db)
            await email_service.send_email(
                to=user.email,
                subject=f"Knowledge Base Ready - {kb.name}",
                html=html_content,
                user_id=kb.created_by_user_id,
                workspace_id=workspace_id,
                template_type="kb_processing_completed",
            )

            logger.info(f"KB processing completed email sent for {file_name}")

        except Exception as e:
            logger.error(f"Error sending KB processing email: {str(e)}", exc_info=True)
            # Don't fail the upload if email fails
