"""
Content Service - Business Logic for Content Operations

This service encapsulates all business logic related to content management,
including creation, updates, deletion, publishing, and slug generation.

Responsibilities:
- Content CRUD operations
- Slug generation and uniqueness validation
- Metadata and SEO data management
- Status transition validation
- Business rule enforcement

Does NOT:
- Handle HTTP requests/responses (that's routes)
- Commit transactions (that's decorators/routes)
- Authentication/authorization (that's decorators)
"""

from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timezone
import re

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.models.content_models.content import Content
from src.api.models.content_models.content_seo_data import ContentSEOData
# Note: ContentMetadata table dropped in migration 40fd95ca1e8d - now uses Content.metadata_json
from src.api.schema.content_schema import ContentCreate, ContentUpdate
from src.flow.states.payload_state import Payload
from src.flow.service.service import LangGraphService
from src.utils.logger import logger
from src.api.middleware.exceptions import (
    WrextValidationException,
    ResourceNotFoundException,
    DuplicateResourceException
)
from dotenv import load_dotenv
import asyncio
import os
load_dotenv()

class ContentService(LangGraphService):
    """Service for content business logic"""

    def __init__(
            self,
            db: AsyncSession,
            url: Optional[str] = None,
            api_key: Optional[str] = None
    ):
        """
        Initialize ContentService.

        Args:
            db: Async database session
            url: Optional LangSmith URL (defaults to settings)
            api_key: Optional LangSmith API key (defaults to settings)
        """
        from src.api.config import get_settings
        settings = get_settings()

        url = url or settings.LANGSMITH_DEV_URL
        api_key = api_key or settings.LANGSMITH_API_KEY
        super().__init__(
            db=db,
            url=url, 
            api_key=api_key
        )
        self.db = db
    
    async def _run_stream_in_background(self, assistant_id, payload):
        """Run the LangGraph stream in the background and update content progress."""
        try:
            async for mode, chunk in self.stream_content(
                assistant_id=assistant_id,
                input_payload={"request_payload": payload},
            ):
                logger.info(f"Streaming update: mode={mode}, chunk={chunk}")
        except Exception as e:
            logger.error(f"Error while streaming content generation: {e}")

    async def create_content(
        self,
        workspace_id: UUID,
        user_id: UUID,
        data: ContentCreate
    ) -> Content:
        """
        Create new content with metadata and SEO data.

        Business Rules:
        - Slug is auto-generated from title and must be unique within workspace
        - Creator and author are set to current user (unless author_id provided)
        - Status defaults to 'draft'
        - Metadata and SEO data are optional

        Args:
            workspace_id: Workspace UUID
            user_id: User UUID (creator)
            data: Content creation data

        Returns:
            Created Content object with relationships loaded

        Raises:
            WrextValidationException: If validation fails
        """
        # Generate unique slug from title
        base_slug = self._slugify(data.title)
        unique_slug = await self._generate_unique_slug(workspace_id, base_slug)

        # Create content entity
        # Default status is "generating" for new content that will be auto-generated
        # If body_markdown is provided, status can be "draft" (manual content)
        default_status = "generating" if not data.body_markdown else "draft"

        content = Content(
            workspace_id=workspace_id,
            topic_id=data.topic_id,
            created_by_user_id=user_id,
            assigned_to_user_id=data.assigned_to_user_id,
            author_id=getattr(data, "author_id", None) or user_id,  # Default to creator
            title=data.title,
            slug=unique_slug,
            body_markdown=data.body_markdown,
            content_format=data.content_format or "Markdown",
            status=data.status or default_status,  # Auto-set to "generating" if no body provided
            content_language=data.content_language or "English",
            langgraph_thread_id=data.langgraph_thread_id,  # Store thread ID if provided
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        self.db.add(content)
        await self.db.flush()  # Get content.id without committing

        # Create metadata JSONB if provided (consolidated from content_metadata table)
        if data.metadata:
            content.metadata_json = {
                "content_summary": data.metadata.content_summary,
                "content_type": data.metadata.content_type,
                "target_platform": data.metadata.target_platform,
                "target_industry": data.metadata.target_industry,
                "target_audience": data.metadata.target_audience,
                "audience_size": data.metadata.audience_size,
                "complexity_level": data.metadata.complexity_level,
                "content_tone": data.metadata.content_tone,
                "target_region": data.metadata.target_region,
                "content_objectives": data.metadata.content_objectives,
                "source_references": data.metadata.source_references,
                "content_word_count": data.metadata.content_word_count,
                "reading_time_minutes": data.metadata.reading_time_minutes,
                "content_quality_scores": data.metadata.content_quality_scores,
                "featured_image_prompt": data.metadata.featured_image_prompt,
                "featured_image_alt_text": data.metadata.featured_image_alt_text,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }

        # Create SEO data if provided
        if data.seo_data:
            seo_data = ContentSEOData(
                content_id=content.id,
                content_primary_keywords=data.seo_data.content_primary_keywords,
                content_secondary_keywords=data.seo_data.content_secondary_keywords,
                content_meta_description=data.seo_data.content_meta_description,
                content_search_intent=data.seo_data.content_search_intent,
                content_seo_score=data.seo_data.content_seo_score,
                content_readability_score=data.seo_data.content_readability_score,
                created_at=datetime.now(timezone.utc)
            )
            self.db.add(seo_data)

        await self.db.flush()
        
        # Eagerly load relationships to avoid lazy loading in async context
        # This prevents "greenlet_spawn has not been called" errors when to_dict() accesses relationships
        query = (
            select(Content)
            .where(Content.id == content.id)
            .options(
                selectinload(Content.seo_data)
            )
        )
        result = await self.db.execute(query)
        content = result.scalar_one()

        logger.info(
            f"Content created: {content.id}",
            extra={"workspace_id": str(workspace_id), "user_id": str(user_id), "title": data.title}
        )

        # Content generation will be triggered by background task in the route
        # This allows immediate API response while generation runs in background
        # create the assistant
        assistant = await self.create_assistant(
            graph_id="agent",
            config={},
            metadata={},
            name=f"Content Generation Assistant for content {content.id}"
        )

        # create a thread 
        # thread = await self.create_thread(thread_id="1234")

        # Build payload
        payload = Payload(
            content_id=str(content.id),
            workspace_id=str(workspace_id),
            topic_id=str(data.topic_id) if data.topic_id else None,
            author_id=str(user_id),
            title=data.title,
            content_language=data.content_language,
            content_format=data.content_format,
        )

        # Launch streaming process in background (non-blocking)
        asyncio.create_task(
            self._run_stream_in_background(assistant["assistant_id"], payload)
        )
        return content
    
    async def update_content(
        self,
        content_id: UUID,
        workspace_id: UUID,
        user_id: UUID,
        data: ContentUpdate
    ) -> Content:
        """
        Update existing content.

        Business Rules:
        - Slug is regenerated if title changes
        - Status transitions are validated (see _validate_status_transition)
        - Publishing requires 'content.publish' permission (checked in route)
        - Metadata and SEO data can be updated or created

        Args:
            content_id: Content UUID
            workspace_id: Workspace UUID (for verification)
            user_id: User UUID (for permission checks)
            data: Content update data

        Returns:
            Updated Content object

        Raises:
            ResourceNotFoundException: If content not found
            WrextValidationException: If validation fails
        """
        # Get content
        content = await self._get_content_or_404(content_id, workspace_id)

        # Update title and regenerate slug if title changed
        if data.title is not None and data.title != content.title:
            base_slug = self._slugify(data.title)
            # Exclude current content from uniqueness check
            unique_slug = await self._generate_unique_slug(
                workspace_id,
                base_slug,
                exclude_id=content.id
            )
            content.slug = unique_slug
            content.title = data.title

        # Update body fields
        if data.body_markdown is not None:
            content.body_markdown = data.body_markdown

        if data.body_html is not None:
            content.body_html = data.body_html

        # Update status with validation
        if data.status is not None:
            await self._validate_status_transition(content.status, data.status)
            content.status = data.status

        # Update other fields
        if data.content_language is not None:
            content.content_language = data.content_language

        if data.assigned_to_user_id is not None:
            content.assigned_to_user_id = data.assigned_to_user_id

        if data.topic_id is not None:
            content.topic_id = data.topic_id

        # Update LangGraph thread ID if provided
        if hasattr(data, 'langgraph_thread_id') and data.langgraph_thread_id is not None:
            content.langgraph_thread_id = data.langgraph_thread_id

        content.updated_at = datetime.now(timezone.utc)

        # Update metadata JSONB if provided (consolidated from content_metadata table)
        if data.metadata:
            # Get existing metadata_json or create new dict
            metadata_json = content.metadata_json or {}

            # Update only provided fields (partial update support)
            if data.metadata.content_summary is not None:
                metadata_json["content_summary"] = data.metadata.content_summary
            if data.metadata.content_type is not None:
                metadata_json["content_type"] = data.metadata.content_type
            if data.metadata.target_platform is not None:
                metadata_json["target_platform"] = data.metadata.target_platform
            if data.metadata.target_industry is not None:
                metadata_json["target_industry"] = data.metadata.target_industry
            if data.metadata.target_audience is not None:
                metadata_json["target_audience"] = data.metadata.target_audience
            if data.metadata.content_word_count is not None:
                metadata_json["content_word_count"] = data.metadata.content_word_count
            if data.metadata.reading_time_minutes is not None:
                metadata_json["reading_time_minutes"] = data.metadata.reading_time_minutes
            if data.metadata.audience_size is not None:
                metadata_json["audience_size"] = data.metadata.audience_size
            if data.metadata.complexity_level is not None:
                metadata_json["complexity_level"] = data.metadata.complexity_level
            if data.metadata.content_tone is not None:
                metadata_json["content_tone"] = data.metadata.content_tone
            if data.metadata.target_region is not None:
                metadata_json["target_region"] = data.metadata.target_region
            if data.metadata.content_objectives is not None:
                metadata_json["content_objectives"] = data.metadata.content_objectives
            if data.metadata.source_references is not None:
                metadata_json["source_references"] = data.metadata.source_references
            if data.metadata.content_quality_scores is not None:
                metadata_json["content_quality_scores"] = data.metadata.content_quality_scores
            if data.metadata.featured_image_prompt is not None:
                metadata_json["featured_image_prompt"] = data.metadata.featured_image_prompt
            if data.metadata.featured_image_alt_text is not None:
                metadata_json["featured_image_alt_text"] = data.metadata.featured_image_alt_text

            metadata_json["updated_at"] = datetime.now(timezone.utc).isoformat()
            content.metadata_json = metadata_json

        # Update SEO data if provided
        if data.seo_data:
            result = await self.db.execute(
                select(ContentSEOData).where(ContentSEOData.content_id == content_id)
            )
            seo_data = result.scalar_one_or_none()

            if seo_data:
                # Update existing SEO data
                if data.seo_data.content_primary_keywords is not None:
                    seo_data.content_primary_keywords = data.seo_data.content_primary_keywords
                if data.seo_data.content_secondary_keywords is not None:
                    seo_data.content_secondary_keywords = data.seo_data.content_secondary_keywords
                if data.seo_data.content_meta_description is not None:
                    seo_data.content_meta_description = data.seo_data.content_meta_description
                if data.seo_data.content_seo_score is not None:
                    seo_data.content_seo_score = data.seo_data.content_seo_score
                if data.seo_data.content_readability_score is not None:
                    seo_data.content_readability_score = data.seo_data.content_readability_score
                seo_data.updated_at = datetime.now(timezone.utc)
            else:
                # Create new SEO data
                seo_data = ContentSEOData(
                    content_id=content.id,
                    content_primary_keywords=data.seo_data.content_primary_keywords,
                    content_meta_description=data.seo_data.content_meta_description,
                    created_at=datetime.now(timezone.utc)
                )
                self.db.add(seo_data)

        await self.db.flush()
        await self.db.refresh(content)

        logger.info(
            f"Content updated: {content_id}",
            extra={"workspace_id": str(workspace_id), "user_id": str(user_id)}
        )

        return content

    async def delete_content(self, content_id: UUID, workspace_id: UUID) -> None:
        """
        Soft delete content by setting deleted_at timestamp.
/
        Args:
            content_id: Content UUID
            workspace_id: Workspace UUID (for verification)

        Raises:
            ResourceNotFoundException: If content not found
        """
        content = await self._get_content_or_404(content_id, workspace_id)

        content.deleted_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(content)
        await self.db.commit()

        logger.info(
            f"Content deleted: {content_id}",
            extra={"workspace_id": str(workspace_id)}
        )

    async def publish_content(self, content_id: UUID, workspace_id: UUID, user_id: UUID) -> Content:
        """
        Publish content (business logic for publishing).

        Business Rules:
        - Content must be in 'ready' status to publish
        - Content must have body content (not empty)
        - Permission check ('content.publish') handled in route decorator

        Args:
            content_id: Content UUID
            workspace_id: Workspace UUID
            user_id: User UUID (for logging)

        Returns:
            Published Content object

        Raises:
            WrextValidationException: If content not ready to publish
        """
        content = await self._get_content_or_404(content_id, workspace_id)

        # Validate content is ready to publish
        if content.status != "ready":
            raise WrextValidationException(
                message="Content must be in 'ready' status to publish",
                field_errors={"status": [f"Cannot publish content with status '{content.status}'. Move to 'ready' first."]}
            )

        if not content.body_markdown or content.body_markdown.strip() == "":
            raise WrextValidationException(
                message="Cannot publish empty content",
                field_errors={"body_markdown": ["Content body is required for publishing"]}
            )

        # Publish
        content.status = "published"
        content.updated_at = datetime.now(timezone.utc)

        logger.info(
            f"Content published: {content_id}",
            extra={"workspace_id": str(workspace_id), "user_id": str(user_id)}
        )

        return content

    async def list_content(
        self,
        workspace_id: UUID,
        status: Optional[str] = None,
        include_metadata: bool = False,
        include_seo: bool = False,
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        List content for workspace with filtering and pagination.

        Args:
            workspace_id: Workspace UUID
            status: Optional status filter
            include_metadata: Include content metadata
            include_seo: Include SEO data
            limit: Maximum items to return
            offset: Number of items to skip

        Returns:
            Dict with content list and total count
        """
        # Build query
        query = select(Content).where(
            Content.workspace_id == workspace_id,
            Content.deleted_at == None
        )

        # Filter by status if provided
        if status:
            query = query.where(Content.status == status)

        # Eagerly load relationships to avoid lazy loading issues
        # Note: metadata_json is now a JSONB column, no relationship to load
        if include_seo:
            query = query.options(selectinload(Content.seo_data))

        # Get total count
        count_query = select(func.count()).select_from(Content).where(
            Content.workspace_id == workspace_id,
            Content.deleted_at == None
        )
        if status:
            count_query = count_query.where(Content.status == status)

        count_result = await self.db.execute(count_query)
        total_count = count_result.scalar()

        # Apply pagination and ordering
        query = query.order_by(Content.created_at.desc()).offset(offset).limit(limit)
        result = await self.db.execute(query)
        content_items = result.scalars().all()

        # Build relationships list
        relationships = []
        # Note: metadata now in JSONB column (metadata_json), not a relationship
        if include_seo:
            relationships.append("seo_data")

        content_list = [
            content.to_dict(include_relationships=relationships if relationships else None)
            for content in content_items
        ]

        logger.info(f"Listed {len(content_list)} content items for workspace {workspace_id}")

        return {
            "content": content_list,
            "total_count": total_count
        }

    async def get_content(
        self,
        content_id: UUID,
        workspace_id: UUID,
        include_metadata: bool = True,
        include_seo: bool = True
    ) -> Dict[str, Any]:
        """
        Get single content item by ID.

        Args:
            content_id: Content UUID
            workspace_id: Workspace UUID
            include_metadata: Include content metadata
            include_seo: Include SEO data

        Returns:
            Content dict with requested relationships

        Raises:
            ResourceNotFoundException: If content not found
        """
        # Build query with eager loading for requested relationships
        query = select(Content).where(
            Content.id == content_id,
            Content.workspace_id == workspace_id,
            Content.deleted_at == None
        )

        # Eagerly load relationships to avoid lazy loading issues
        # Note: metadata_json is now a JSONB column, no relationship to load
        if include_seo:
            query = query.options(selectinload(Content.seo_data))

        result = await self.db.execute(query)
        content = result.scalar_one_or_none()

        if not content:
            raise ResourceNotFoundException(
                resource_type="Content",
                resource_id=str(content_id)
            )

        relationships = []
        # Note: metadata now in JSONB column (metadata_json), not a relationship
        if include_seo:
            relationships.append("seo_data")

        content_data = content.to_dict(
            include_relationships=relationships if relationships else None,
            include_nulls=True  # Include body_markdown even if null
        )

        logger.info(f"Retrieved content {content_id} from workspace {workspace_id}")

        return content_data

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    def _slugify(self, text: str) -> str:
        """
        Convert text to URL-safe slug.

        Args:
            text: Text to slugify

        Returns:
            URL-safe slug
        """
        # Convert to lowercase
        text = text.lower()
        # Replace spaces and underscores with hyphens
        text = re.sub(r'[\s_]+', '-', text)
        # Remove non-alphanumeric characters except hyphens
        text = re.sub(r'[^a-z0-9-]', '', text)
        # Remove multiple consecutive hyphens
        text = re.sub(r'-+', '-', text)
        # Strip hyphens from start and end
        text = text.strip('-')
        return text

    async def _generate_unique_slug(
        self,
        workspace_id: UUID,
        base_slug: str,
        exclude_id: Optional[UUID] = None
    ) -> str:
        """
        Generate unique slug within workspace.

        If slug exists, appends -1, -2, etc. until unique slug is found.

        Args:
            workspace_id: Workspace UUID
            base_slug: Base slug to make unique
            exclude_id: Content ID to exclude from uniqueness check (for updates)

        Returns:
            Unique slug
        """
        slug = base_slug
        counter = 1

        while True:
            # Check if slug exists
            query = select(Content).where(
                Content.workspace_id == workspace_id,
                Content.slug == slug,
                Content.deleted_at == None
            )

            if exclude_id:
                query = query.where(Content.id != exclude_id)

            result = await self.db.execute(query)
            existing = result.scalar_one_or_none()

            if not existing:
                return slug

            # Slug exists, try with counter
            slug = f"{base_slug}-{counter}"
            counter += 1

    async def _get_content_or_404(self, content_id: UUID, workspace_id: UUID) -> Content:
        """
        Get content by ID or raise 404.

        Args:
            content_id: Content UUID
            workspace_id: Workspace UUID (for verification)

        Returns:
            Content object

        Raises:
            ResourceNotFoundException: If content not found or not in workspace
        """
        result = await self.db.execute(
            select(Content).where(
                Content.id == content_id,
                Content.workspace_id == workspace_id,
                Content.deleted_at == None
            )
        )
        content = result.scalar_one_or_none()

        if not content:
            raise ResourceNotFoundException(
                resource_type="Content",
                resource_id=str(content_id)
            )

        return content

    async def _validate_status_transition(self, current: str, new: str) -> None:
        """
        Validate status transition follows allowed flow.

        Allowed transitions:
        - draft → ready, archived
        - ready → published, draft, archived
        - published → archived
        - archived → (no transitions allowed)

        Args:
            current: Current status
            new: New status to transition to

        Raises:
            WrextValidationException: If transition not allowed
        """
        # Define allowed transitions
        ALLOWED_TRANSITIONS = {
            "draft": ["ready", "archived"],
            "ready": ["published", "draft", "archived"],
            "published": ["archived"],
            "archived": [],  # Cannot transition from archived
        }

        allowed = ALLOWED_TRANSITIONS.get(current, [])

        if new not in allowed:
            raise WrextValidationException(
                message=f"Invalid status transition: {current} → {new}",
                field_errors={"status": [f"Cannot transition from '{current}' to '{new}'. Allowed: {', '.join(allowed) if allowed else 'none'}"]}
            )
