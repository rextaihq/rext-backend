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

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.models.content_models.content import Content
from src.api.models.content_models.content_seo_data import ContentSEOData
from src.api.models.content_models.content_media import ContentMedia
from src.utils.logger import logger
from src.api.middleware.exceptions import (
    RextValidationException,
    ResourceNotFoundException,
    DuplicateResourceException
)
from src.api.models.workspace_models.workspace_integration import WorkspaceIntegration
from src.web.wordpress import WordPressPublisher
from src.api.schema.content_schema import PublishResponse, ContentCreate, ContentUpdate, ContentSEODataSchema
from src.utils.slug_utils import slugify, generate_unique_slug
import asyncio


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

        base_slug = slugify(data.title)
        unique_slug = await generate_unique_slug(self.db, base_slug, Content, workspace_id=workspace_id)

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
                trust_score=data.seo_data.trust_score,
                seo_details=data.seo_data.seo_details
            )
            self.db.add(seo_record)
            content.seo_data = seo_record  # Link relationship to avoid lazy loading later

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

            content.slug = await generate_unique_slug(
                self.db, slugify(data.title), Content, 
                workspace_id=workspace_id, exclude_id=content.id
            )
            content.title = data.title

        if data.status and data.status != content.status:
            await self._validate_status_transition(content.status, data.status)
            content.status = data.status

        # Update core fields
        updatable_fields = [
            "content_language", "introduction", "body_markdown", "body_html", 
            "tags", "images_data", "links_data", "schema_markup", "langgraph_thread_id"
        ]
        for field in updatable_fields:
            val = getattr(data, field, None)
            if val is not None:
                setattr(content, field, val)

        # Update SEO data
        if data.seo_data:
            seo = content.seo_data
            if not seo:
                seo = ContentSEOData(content_id=content.id)
                self.db.add(seo)
            
            seo_fields = [
                "meta_title", "meta_description", "focus_keyphrase", "keyphrase_density", 
                "secondary_keywords", "search_intent", "seo_score", "readability_score", 
                "trust_score", "seo_details"
            ]
            for field in seo_fields:
                val = getattr(data.seo_data, field, None)
                if val is not None:
                    setattr(seo, field, val)

        # Update media links (simplified clear & re-add)
        if data.media_items is not None:
            # Note: In production you might want a more subtle diff approach
            # Using execute() to avoid loading all objects
            await self.db.execute(delete(ContentMedia).where(ContentMedia.content_id == content.id))
            
            for item in data.media_items:
                self.db.add(ContentMedia(
                    content_id=content.id, 
                    media_id=item.media_id, 
                    usage_type=item.usage_type, 
                    position=item.position
                ))

        content.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(content)
        return content

    async def delete_content(self, content_id: UUID, workspace_id: UUID) -> None:
        content = await self._get_content_or_404(content_id, workspace_id)
        content.deleted_at = datetime.now(timezone.utc)
        await self.db.flush()

    async def list_content(self, workspace_id: UUID, status: Optional[str] = None, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        query = (
            select(Content)
            .where(Content.workspace_id == workspace_id, Content.deleted_at == None)
            .options(selectinload(Content.seo_data))
        )
        if status: query = query.where(Content.status == status)
        
        count_query = (
            select(func.count())
            .select_from(Content)
            .where(Content.workspace_id == workspace_id, Content.deleted_at == None)
        )
        if status: count_query = count_query.where(Content.status == status)
        
        total_count = (await self.db.execute(count_query)).scalar()
        result = await self.db.execute(
            query.order_by(Content.created_at.desc()).offset(offset).limit(limit)
        )
        items = result.scalars().all()
        
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


    async def _get_content_or_404(self, content_id: UUID, workspace_id: UUID, include_seo: bool = False) -> Content:
        query = select(Content).where(
            Content.id == content_id, 
            Content.workspace_id == workspace_id, 
            Content.deleted_at == None
        )
        if include_seo: query = query.options(selectinload(Content.seo_data))
        content = (await self.db.execute(query)).scalar_one_or_none()
        if not content: raise ResourceNotFoundException(resource_type="Content", resource_id=str(content_id))
        return content

    async def _validate_status_transition(self, current: str, new: str) -> None:
        ALLOWED = {
            "draft": ["generating", "ready", "archived"],
            "generating": ["ready", "failed", "draft"],
            "ready": ["published", "draft", "archived", "generating"],
            "published": ["archived", "ready"],
            "archived": ["draft"],
            "failed": ["draft", "generating", "archived"],
        }
        if new not in ALLOWED.get(current, []):
            raise RextValidationException(message=f"Invalid transition: {current} -> {new}")

    async def publish_to_sites(
        self,
        content: Content,
        workspace_id: UUID,
        publish_status: str = "publish"
    ) -> List[PublishResponse]:
        """
        Publish content to all active WordPress sites in the workspace.
        """
        # Fetch all active sites
        sites_query = select(WorkspaceIntegration).where(
            WorkspaceIntegration.workspace_id == workspace_id,
            WorkspaceIntegration.is_active.is_(True)
        )
        sites_result = await self.db.execute(sites_query)
        sites = sites_result.scalars().all()

        if not sites:
            logger.warning(f"No active sites found for workspace {workspace_id}")
            raise RextValidationException(
                message="No active WordPress sites found in this workspace. Please connect a site before publishing."
            )

        # Prepare content data for publisher
        seo_data = None
        
        # Ensure seo_data is loaded to avoid MissingGreenlet error
        from sqlalchemy.orm.base import NO_VALUE
        from sqlalchemy import inspect as sa_inspect
        if sa_inspect(content).attrs.seo_data.loaded_value is NO_VALUE:
            seo_result = await self.db.execute(
                select(ContentSEOData).where(ContentSEOData.content_id == content.id)
            )
            content.seo_data = seo_result.scalar_one_or_none()

        if content.seo_data:
            seo_data = ContentSEODataSchema(
                meta_title=content.seo_data.meta_title,
                meta_description=content.seo_data.meta_description,
                focus_keyphrase=content.seo_data.focus_keyphrase,
                trust_score=content.seo_data.trust_score
            )
            
        content_data = ContentCreate(
            title=content.title,
            introduction=content.introduction,
            body_markdown=content.body_markdown,
            body_html=content.body_html,
            tags=content.tags,
            seo_data=seo_data
        )

        async def publish_one(site):
            try:
                async with WordPressPublisher(
                    site_url=site.site_url,
                    api_endpoint=site.api_endpoint,
                    username=site.username,
                    app_password=site.app_password,
                    api_key=site.api_key
                ) as wp_publisher:
                    wp_response = await wp_publisher.publish_post(
                        data=content_data,
                        status=publish_status
                    )

                return PublishResponse(
                    site_id=site.id,
                    site_url=site.site_url,
                    success=True,
                    wordpress_post_id=wp_response.get("post_id"),
                    wordpress_url=wp_response.get("link")
                )
            except Exception as e:
                logger.error(f"Failed to publish to {site.site_url}: {str(e)}")
                return PublishResponse(
                    site_id=site.id,
                    site_url=site.site_url,
                    success=False,
                    error=str(e)
                )

        results = await asyncio.gather(*(publish_one(site) for site in sites))

        # Update content with first successful publish info
        successful_results = [r for r in results if r.success]
        if successful_results:
            first_success = successful_results[0]
            content.wordpress_post_id = first_success.wordpress_post_id
            content.wordpress_url = first_success.wordpress_url
            content.wordpress_published_at = datetime.now(timezone.utc)
            content.status = "published"
        else:
            content.status = "failed"
            logger.error(f"Publishing failed for all sites for content {content.id}")

        content.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        return results
