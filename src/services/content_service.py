"""
Content Service - Business Logic for Content Operations

Handles multi-table persistence for content, SEO, and media.
Strictly separates core content from SEO metadata.
"""

from typing import List, Optional, Dict, Any
from uuid import UUID
from uuid import uuid4
from datetime import datetime, timezone
import re

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.models.content_models.content import Content
from src.api.models.content_models.content_seo_data import ContentSEOData
from src.api.models.content_models.content_media import ContentMedia
from src.api.schema.content_schema import ContentCreate, ContentUpdate
from src.utils.logger import logger
from src.api.middleware.exceptions import (
    RextValidationException,
    ResourceNotFoundException,
    DuplicateResourceException
)


class ContentService:
    """
    Service for content business logic.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_content(
        self, workspace_id: UUID, user_id: UUID, data: ContentCreate
    ) -> Content:
        """Create new content with nested SEO and Media data."""
        # Check for duplicate title within the same workspace
        existing_query = select(Content).where(
            Content.workspace_id == workspace_id,
            Content.title == data.title,
            Content.deleted_at == None
        )
        existing_content = (await self.db.execute(existing_query)).scalar_one_or_none()
        if existing_content:
            raise DuplicateResourceException(
                resource_type="Content",
                conflicting_field="title",
                conflicting_value=data.title
            )

        base_slug = self._slugify(data.title)
        unique_slug = await self._generate_unique_slug(workspace_id, base_slug)

        # Create main content
        content = Content(
            workspace_id=workspace_id,
            created_by_user_id=user_id,
            title=data.title,
            slug=unique_slug,
            introduction=data.introduction,
            body_markdown=data.body_markdown,
            body_html=data.body_html,
            status=data.status or "draft",
            content_language=data.content_language or "English",
            tags=data.tags,
            images_data=data.images_data,
            links_data=data.links_data,
            schema_markup=data.schema_markup,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        
        self.db.add(content)
        await self.db.flush()

        # Save SEO data
        if data.seo_data:
            seo_record = ContentSEOData(
                content_id=content.id,
                meta_title=data.seo_data.meta_title,
                meta_description=data.seo_data.meta_description,
                focus_keyphrase=data.seo_data.focus_keyphrase,
                keyphrase_density=data.seo_data.keyphrase_density,
                secondary_keywords=data.seo_data.secondary_keywords,
                search_intent=data.seo_data.search_intent,
                seo_score=data.seo_data.seo_score,
                readability_score=data.seo_data.readability_score,
                seo_details=data.seo_data.seo_details
            )
            self.db.add(seo_record)

        # Save Media links
        if data.media_items:
            for item in data.media_items:
                media_link = ContentMedia(
                    content_id=content.id,
                    media_id=item.media_id,
                    usage_type=item.usage_type,
                    position=item.position
                )
                self.db.add(media_link)

        await self.db.flush()
        logger.info(f"Content created: {content.id}")
        return content

    async def update_content(
        self, content_id: UUID, workspace_id: UUID, user_id: UUID, data: ContentUpdate
    ) -> Content:
        """Update existing content and its nested relations."""
        content = await self._get_content_or_404(content_id, workspace_id, include_seo=True)

        if data.title and data.title != content.title:
            # Check for duplicate title within the same workspace
            existing_query = select(Content).where(
                Content.workspace_id == workspace_id,
                Content.title == data.title,
                Content.deleted_at == None,
                Content.id != content_id
            )
            existing_content = (await self.db.execute(existing_query)).scalar_one_or_none()
            if existing_content:
                raise DuplicateResourceException(
                    resource_type="Content",
                    conflicting_field="title",
                    conflicting_value=data.title
                )

            content.slug = await self._generate_unique_slug(workspace_id, self._slugify(data.title), exclude_id=content.id)
            content.title = data.title

        if data.status and data.status != content.status:
            await self._validate_status_transition(content.status, data.status)
            content.status = data.status

        # Update core fields
        for field in ["content_language", "introduction", "body_markdown", "body_html", "tags", "images_data", "links_data", "schema_markup", "langgraph_thread_id"]:
            val = getattr(data, field, None)
            if val is not None:
                setattr(content, field, val)

        # Update SEO data
        if data.seo_data:
            seo = content.seo_data
            if not seo:
                seo = ContentSEOData(content_id=content.id)
                self.db.add(seo)
            
            for field in ["meta_title", "meta_description", "focus_keyphrase", "keyphrase_density", "secondary_keywords", "search_intent", "seo_score", "readability_score", "seo_details"]:
                val = getattr(data.seo_data, field, None)
                if val is not None:
                    setattr(seo, field, val)

        # Update media links (simplified clear & re-add)
        if data.media_items is not None:
            # Note: In production you might want a more subtle diff approach
            # Using execute() to avoid loading all objects
            from sqlalchemy import delete
            await self.db.execute(delete(ContentMedia).where(ContentMedia.content_id == content.id))
            
            for item in data.media_items:
                self.db.add(ContentMedia(content_id=content.id, media_id=item.media_id, usage_type=item.usage_type, position=item.position))

        content.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(content)
        return content

    async def delete_content(self, content_id: UUID, workspace_id: UUID) -> None:
        content = await self._get_content_or_404(content_id, workspace_id)
        content.deleted_at = datetime.now(timezone.utc)
        await self.db.flush()

    async def list_content(self, workspace_id: UUID, status: Optional[str] = None, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        query = select(Content).where(Content.workspace_id == workspace_id, Content.deleted_at == None).options(selectinload(Content.seo_data))
        if status: query = query.where(Content.status == status)
        
        count_query = select(func.count()).select_from(Content).where(Content.workspace_id == workspace_id, Content.deleted_at == None)
        if status: count_query = count_query.where(Content.status == status)
        
        total_count = (await self.db.execute(count_query)).scalar()
        items = (await self.db.execute(query.order_by(Content.created_at.desc()).offset(offset).limit(limit))).scalars().all()
        
        return {
            "content": [c.to_dict(include_relationships=["seo_data"]) for c in items],
            "total_count": total_count,
            "workspace_id": workspace_id,
            "limit": limit,
            "offset": offset
        }

    async def get_content(self, content_id: UUID, workspace_id: UUID) -> Dict[str, Any]:
        content = await self._get_content_or_404(content_id, workspace_id, include_seo=True)
        return content.to_dict(include_relationships=["seo_data"])

    async def publish_content(self, content_id: UUID, workspace_id: UUID, user_id: UUID) -> Content:
        content = await self._get_content_or_404(content_id, workspace_id)
        if content.status != "ready": raise RextValidationException(message="Content must be 'ready' to publish")
        if not content.body_markdown: raise RextValidationException(message="Cannot publish empty content")
        content.status = "published"
        content.updated_at = datetime.now(timezone.utc)
        return content

    def _slugify(self, text: str) -> str:
        text = text.lower()
        text = re.sub(r"[\s_]+", "-", text)
        text = re.sub(r"[^a-z0-9-]", "", text)
        return text.strip("-")

    async def _generate_unique_slug(self, workspace_id: UUID, base_slug: str, exclude_id: Optional[UUID] = None) -> str:
        slug, counter = base_slug, 1
        while True:
            query = select(Content).where(Content.workspace_id == workspace_id, Content.slug == slug, Content.deleted_at == None)
            if exclude_id: query = query.where(Content.id != exclude_id)
            if not (await self.db.execute(query)).scalar_one_or_none(): return slug
            slug, counter = f"{base_slug}-{counter}", counter + 1

    async def _get_content_or_404(self, content_id: UUID, workspace_id: UUID, include_seo: bool = False) -> Content:
        query = select(Content).where(Content.id == content_id, Content.workspace_id == workspace_id, Content.deleted_at == None)
        if include_seo: query = query.options(selectinload(Content.seo_data))
        content = (await self.db.execute(query)).scalar_one_or_none()
        if not content: raise ResourceNotFoundException(resource_type="Content", resource_id=str(content_id))
        return content

    async def _validate_status_transition(self, current: str, new: str) -> None:
        ALLOWED = {"generating": ["ready", "archived", "draft"], "draft": ["ready", "archived", "generating"], "ready": ["published", "draft", "archived", "generating"], "published": ["archived", "ready"], "archived": []}
        if new not in ALLOWED.get(current, []): raise RextValidationException(message=f"Invalid transition: {current} -> {new}")
