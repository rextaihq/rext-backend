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

from src.api.models.content_models.content import Content
from src.api.models.content_models.content_metadata import ContentMetadata
from src.api.models.content_models.content_seo_data import ContentSEOData
from src.api.schema.content_schema import ContentCreate, ContentUpdate
from src.utils.logger import logger
from src.api.middleware.exceptions import (
    WrextValidationException,
    ResourceNotFoundException,
    DuplicateResourceException
)


class ContentService:
    """Service for content business logic"""

    def __init__(self, db: AsyncSession):
        """
        Initialize ContentService.

        Args:
            db: Async database session
        """
        self.db = db

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
        content = Content(
            workspace_id=workspace_id,
            topic_id=data.topic_id,
            created_by_user_id=user_id,
            assigned_to_user_id=data.assigned_to_user_id,
            author_id=data.author_id or user_id,  # Default to creator
            title=data.title,
            slug=unique_slug,
            body_markdown=data.body_markdown,
            content_format=data.content_format or "Markdown",
            status=data.status or "draft",
            content_language=data.content_language or "English",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        self.db.add(content)
        await self.db.flush()  # Get content.id without committing

        # Create metadata if provided
        if data.metadata:
            metadata = ContentMetadata(
                content_id=content.id,
                content_summary=data.metadata.content_summary,
                content_type=data.metadata.content_type,
                target_platform=data.metadata.target_platform,
                target_industry=data.metadata.target_industry,
                target_audience=data.metadata.target_audience,
                audience_size=data.metadata.audience_size,
                complexity_level=data.metadata.complexity_level,
                content_tone=data.metadata.content_tone,
                target_region=data.metadata.target_region,
                content_objectives=data.metadata.content_objectives,
                source_references=data.metadata.source_references,
                content_word_count=data.metadata.content_word_count,
                reading_time_minutes=data.metadata.reading_time_minutes,
                content_quality_scores=data.metadata.content_quality_scores,
                featured_image_prompt=data.metadata.featured_image_prompt,
                featured_image_alt_text=data.metadata.featured_image_alt_text,
                created_at=datetime.now(timezone.utc)
            )
            self.db.add(metadata)

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
        await self.db.refresh(content)

        logger.info(
            f"Content created: {content.id}",
            extra={"workspace_id": str(workspace_id), "user_id": str(user_id), "title": data.title}
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

        content.updated_at = datetime.now(timezone.utc)

        # Update metadata if provided
        if data.metadata:
            result = await self.db.execute(
                select(ContentMetadata).where(ContentMetadata.content_id == content_id)
            )
            metadata = result.scalar_one_or_none()

            if metadata:
                # Update existing metadata
                if data.metadata.content_summary is not None:
                    metadata.content_summary = data.metadata.content_summary
                if data.metadata.content_type is not None:
                    metadata.content_type = data.metadata.content_type
                if data.metadata.target_platform is not None:
                    metadata.target_platform = data.metadata.target_platform
                if data.metadata.target_industry is not None:
                    metadata.target_industry = data.metadata.target_industry
                if data.metadata.target_audience is not None:
                    metadata.target_audience = data.metadata.target_audience
                if data.metadata.content_word_count is not None:
                    metadata.content_word_count = data.metadata.content_word_count
                if data.metadata.reading_time_minutes is not None:
                    metadata.reading_time_minutes = data.metadata.reading_time_minutes
                metadata.updated_at = datetime.now(timezone.utc)
            else:
                # Create new metadata
                metadata = ContentMetadata(
                    content_id=content.id,
                    content_summary=data.metadata.content_summary,
                    content_type=data.metadata.content_type,
                    target_platform=data.metadata.target_platform,
                    created_at=datetime.now(timezone.utc)
                )
                self.db.add(metadata)

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

        Args:
            content_id: Content UUID
            workspace_id: Workspace UUID (for verification)

        Raises:
            ResourceNotFoundException: If content not found
        """
        content = await self._get_content_or_404(content_id, workspace_id)

        content.deleted_at = datetime.now(timezone.utc)

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
