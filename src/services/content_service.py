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
import markdown

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.models.content_models.content import Content
from src.api.models.content_models.content_seo_data import ContentSEOData
from src.api.models.content_models.content_media import ContentMedia
from src.api.models.content_models.publishing_result import ContentPublishingResult, PublishingStatus
from src.services.content_embedding_service import ContentEmbeddingService
from src.utils.logger import logger
from src.utils.datetime_utils import resolve_scheduled_datetime
from src.api.middleware.exceptions import (
    RextValidationException,
    ResourceNotFoundException,
    DuplicateResourceException
)
from src.api.models.integrations.workspace_integration import WorkspaceIntegration
from src.api.config import settings
from src.web.wordpress import WordPressPublisher
from src.flow.engines.content.generation.content_generation import _is_placeholder_image_url
from src.web.shopify_bridge import ShopifyAppBridge
from src.api.schema.content_schema import PublishResponse, ContentCreate, ContentUpdate, ContentSEODataSchema
from src.utils.slug_utils import slugify, generate_unique_slug
from src.utils.wordpress_status import (
    content_status_for_wordpress_status,
    normalize_wordpress_post_status,
)
import asyncio


def _extract_feature_image_url(images_data: Any) -> Optional[str]:
    """Extract the primary image URL from images_data, skipping hallucinated/placeholder links."""
    if isinstance(images_data, dict):
        for key in ("featured_image_url", "feature_image_url", "featured_image", "image_url", "source_url", "src", "url"):
            value = images_data.get(key)
            if isinstance(value, str) and value.strip() and not _is_placeholder_image_url(value):
                return value.strip()
    if isinstance(images_data, list):
        for item in images_data:
            if isinstance(item, str) and item.strip() and not _is_placeholder_image_url(item):
                return item.strip()
            if isinstance(item, dict):
                for key in ("url", "src", "image_url"):
                    value = item.get(key)
                    if isinstance(value, str) and value.strip() and not _is_placeholder_image_url(value):
                        return value.strip()
    return None


class ContentService:
    """
    Service for content business logic.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_content(
        self, workspace_id: UUID, user_id: UUID, data: ContentCreate
    ) -> Content:
        """Create new content with nested SEO and Media data.

        Idempotent by langgraph_thread_id: if this generation thread already
        produced content in the workspace, the existing row is updated instead
        of creating a duplicate. This lets the generation graph auto-save the
        finished article while the editor's manual Save reconciles to the same
        row (no duplicate, no title-collision error).
        """
        # Idempotency: reconcile to the existing row for this generation thread.
        if data.langgraph_thread_id:
            existing_by_thread = (await self.db.execute(
                select(Content).where(
                    Content.workspace_id == workspace_id,
                    Content.langgraph_thread_id == data.langgraph_thread_id,
                    Content.deleted_at == None,
                )
            )).scalar_one_or_none()
            if existing_by_thread:
                from src.api.schema.content_schema import ContentUpdate
                update_payload = ContentUpdate(
                    title=data.title,
                    status=data.status,
                    content_language=data.content_language,
                    introduction=data.introduction,
                    body_markdown=data.body_markdown,
                    body_html=data.body_html,
                    tags=data.tags,
                    seo_data=data.seo_data,
                    media_items=data.media_items,
                    images_data=data.images_data,
                    links_data=data.links_data,
                    schema_markup=data.schema_markup,
                )
                return await self.update_content(
                    existing_by_thread.id, workspace_id, user_id, update_payload
                )

        # Check for duplicate title within the same workspace. Skipped for
        # generated content, which is keyed by langgraph_thread_id above.
        if not data.langgraph_thread_id:
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
            category=data.category,
            images_data=data.images_data,
            links_data=data.links_data,
            schema_markup=data.schema_markup,
            langgraph_thread_id=data.langgraph_thread_id,
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
                if not item.media_id:
                    continue
                media_link = ContentMedia(
                    content_id=content.id,
                    media_id=item.media_id,
                    usage_type=item.usage_type,
                    position=item.position
                )
                self.db.add(media_link)

        await self.db.flush()
        logger.info(f"Content created: {content.id}")
        
        # Upsert embedding synchronously after flush
        embed_service = ContentEmbeddingService(self.db)
        await embed_service.upsert_content_embedding(content.id, workspace_id)
        
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
            "tags", "category", "images_data", "links_data", "schema_markup", "langgraph_thread_id"
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
                if not item.media_id:
                    continue
                self.db.add(ContentMedia(
                    content_id=content.id, 
                    media_id=item.media_id, 
                    usage_type=item.usage_type, 
                    position=item.position
                ))

        content.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        
        # Only upsert embedding if title or introduction might have changed
        # We can optimize by just running it on every update for safety, as requested by the user.
        embed_service = ContentEmbeddingService(self.db)
        await embed_service.upsert_content_embedding(content.id, workspace_id)
        
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
        
        # Fetch publishing results for these items to show current live status
        content_ids = [c.id for c in items]
        pub_results = {}
        if content_ids:
            pub_query = select(ContentPublishingResult).where(ContentPublishingResult.content_id.in_(content_ids))
            pub_data = (await self.db.execute(pub_query)).scalars().all()
            for pr in pub_data:
                if pr.content_id not in pub_results:
                    pub_results[pr.content_id] = []
                pub_results[pr.content_id].append({
                    "site_id": str(pr.site_id),
                    "status": pr.status,
                    "url": pr.external_url,
                    "last_synced": pr.last_synced_at.isoformat() if pr.last_synced_at else None
                })

        content_list = []
        for c in items:
            d = c.to_dict(include_relationships=["seo_data"])
            d["publishing_results"] = pub_results.get(c.id, [])
            content_list.append(d)

        return {
            "content": content_list,
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
            "draft":      ["generating", "ready", "review", "archived", "scheduled","published"],
            "generating": ["ready", "failed", "draft"],
            "ready":      ["published", "review", "draft", "archived", "generating", "scheduled"],
            "review":     ["published", "ready", "draft", "archived", "scheduled"],
            "published":  ["archived", "ready", "draft", "trashed", "deleted", "scheduled"],
            "scheduled":  ["published", "failed", "draft", "archived"],
            "archived":   ["draft"],
            "failed":     ["draft", "generating", "archived"],
            "trashed":    ["draft", "deleted", "published"],
            "deleted":    ["draft", "published"],
        }
        if new not in ALLOWED.get(current, []):
            raise RextValidationException(message=f"Invalid transition: {current} -> {new}")

    async def publish_to_sites(
        self,
        content: Content,
        workspace_id: UUID,
        site_id: Optional[UUID] = None,
        publish_status: str = "publish",
        scheduled_at: Optional[datetime] = None,
        user_timezone: str = "UTC",
    ) -> List[PublishResponse]:
        """
        Publish content to active WordPress site(s) in the workspace.
        """
        publish_status = normalize_wordpress_post_status(publish_status)

        # A naive scheduled_at is wall-clock time in the user's account timezone
        # (never the server's or browser's) — normalize to UTC before any
        # comparison or storage so "10:00 AM" always means the same instant
        # regardless of where the request came from.
        if scheduled_at is not None:
            scheduled_at = resolve_scheduled_datetime(scheduled_at, user_timezone)

        # Fetch active sites (optionally filtered by site_id)
        sites_query = select(WorkspaceIntegration).where(
            WorkspaceIntegration.workspace_id == workspace_id,
            WorkspaceIntegration.is_active.is_(True)
        )
        if site_id:
            sites_query = sites_query.where(WorkspaceIntegration.id == site_id)

        sites_result = await self.db.execute(sites_query)
        sites = sites_result.scalars().all()

        if not sites:
            logger.warning(f"No active sites found for workspace {workspace_id}")
            raise RextValidationException(
                message="No active sites found in this workspace. Please connect a site before publishing."
            )

        logger.info(
            f"[PUBLISH] content_id={content.id} workspace={workspace_id} "
            f"publish_status={publish_status} sites_count={len(sites)}"
        )
        for s in sites:
            cfg = s.config_json or {}
            logger.info(
                f"[PUBLISH] site id={s.id} type={s.integration_type} "
                f"url={s.site_url} active={s.is_active} "
                f"connection_mode={cfg.get('connection_mode')} "
                f"has_api_key={bool(s.api_key)} "
                f"bridge_publish_url={cfg.get('bridge_publish_url')} "
                f"app_launch_url={cfg.get('app_launch_url')}"
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
            category=content.category,
            seo_data=seo_data,
            schema_markup=content.schema_markup,
            images_data=content.images_data,
        )

        logger.info(
            "[PUBLISH] content_data assembled: title=%r category=%r tags=%r",
            content.title,
            content.category,
            content.tags,
        )
        is_scheduled = bool(scheduled_at and scheduled_at > datetime.now(timezone.utc))

        async def publish_one(site) -> PublishResponse:
            try:
                if site.integration_type == "shopify":
                    config_json = site.config_json or {}
                    connection_mode = str(config_json.get("connection_mode") or "").lower()
                    use_bridge = connection_mode == "app_bridge" or not site.api_key

                    # We use html for universal support.
                    body_to_use = content.body_html
                    if not body_to_use and content.body_markdown:
                        body_to_use = markdown.markdown(content.body_markdown)
                    elif not body_to_use:
                        body_to_use = ""

                    is_published = publish_status == "publish"

                    if use_bridge:
                        logger.info(
                            f"[PUBLISH] Shopify bridge mode for site={site.site_url} "
                            f"SHOPIFY_BRIDGE_BASE_URL={settings.SHOPIFY_BRIDGE_BASE_URL!r} "
                            f"SHOPIFY_BRIDGE_PUBLISH_ENDPOINT={settings.SHOPIFY_BRIDGE_PUBLISH_ENDPOINT!r} "
                            f"has_shared_secret={bool(settings.SHOPIFY_BRIDGE_SHARED_SECRET)}"
                        )
                        bridge = ShopifyAppBridge(
                            shared_secret=settings.SHOPIFY_BRIDGE_SHARED_SECRET,
                            base_url=settings.SHOPIFY_BRIDGE_BASE_URL,
                            publish_endpoint=settings.SHOPIFY_BRIDGE_PUBLISH_ENDPOINT,
                            fallback_secret_seed=settings.SECRET_KEY,
                        )
                        shop_resp = await bridge.publish_blog_post(
                            store_url=site.site_url,
                            title=content.title,
                            body=body_to_use,
                            tags=content.tags,
                            published=is_published,
                            handle=content.slug,
                            feature_image_url=_extract_feature_image_url(content.images_data),
                            content_id=str(content.id),
                            workspace_id=str(workspace_id),
                            config_json=config_json,
                        )
                    else:
                        from src.web.shopify import ShopifyConnector

                        async with ShopifyConnector(
                            store_url=site.site_url,
                            access_token=site.api_key
                        ) as shopify:
                            shop_resp = await shopify.publish_blog_post(
                                title=content.title,
                                body_html=body_to_use,
                                tags=content.tags,
                                published=is_published,
                                handle=content.slug
                            )
                    article_id = shop_resp.get("article_id")
                    article_url = shop_resp.get("article_url")
                    logger.info(
                        f"[PUBLISH] Shopify SUCCESS site={site.site_url} "
                        f"article_id={article_id} article_url={article_url}"
                    )
                    return PublishResponse(
                        site_id=site.id,
                        site_url=site.site_url,
                        success=True,
                        shopify_article_id=article_id,
                        shopify_article_url=article_url,
                        shopify_blog_id=shop_resp.get("blog_id"),
                    )
                else:
                    # WordPress — if scheduled, defer to background task
                    if is_scheduled:
                        return PublishResponse(
                            site_id=site.id,
                            site_url=site.site_url,
                            success=True,
                        )
                    async with WordPressPublisher(
                        site_url=site.site_url,
                        api_endpoint=site.api_endpoint,
                        username=site.username,
                        app_password=site.app_password,
                        api_key=site.api_key
                    ) as wp_publisher:
                        wp_response = await wp_publisher.publish_post(
                            data=content_data,
                            status=publish_status,
                        )
                    return PublishResponse(
                        site_id=site.id,
                        site_url=site.site_url,
                        success=True,
                        wordpress_post_id=wp_response.get("post_id"),
                        wordpress_url=wp_response.get("link")
                    )
            except Exception as e:
                logger.error(
                    f"[PUBLISH] FAILED site={site.site_url} type={site.integration_type} "
                    f"error={str(e)}"
                )
                return PublishResponse(
                    site_id=site.id,
                    site_url=site.site_url,
                    success=False,
                    error=str(e)
                )

        results = await asyncio.gather(*(publish_one(site) for site in sites))

        # Update content with first successful publish info
        successful_results = [r for r in results if r.success]
        failed_results = [r for r in results if not r.success]

        logger.info(
            f"[PUBLISH] SUMMARY content_id={content.id} "
            f"total={len(results)} succeeded={len(successful_results)} failed={len(failed_results)}"
        )
        for r in failed_results:
            logger.error(f"[PUBLISH] SITE FAILED url={r.site_url} error={r.error}")

        if successful_results:
            wp_success = next((r for r in successful_results if r.wordpress_post_id), None)
            shopify_success = next((r for r in successful_results if r.shopify_article_id), None)
            # Scheduled WP: plugin not called → no post_id yet, identified by absence of both IDs
            wp_deferred = next(
                (r for r in successful_results if not r.wordpress_post_id and not r.shopify_article_id),
                None,
            ) if is_scheduled else None

            if wp_success:
                content.wordpress_post_id = wp_success.wordpress_post_id
                content.wordpress_url = wp_success.wordpress_url
                content.wordpress_published_at = (
                    datetime.now(timezone.utc)
                    if publish_status == "publish"
                    else None
                )
            elif wp_deferred:
                # Store scheduled_at for calendar display; background task overwrites on actual publish
                content.wordpress_published_at = scheduled_at
            if shopify_success:
                content.shopify_article_id = shopify_success.shopify_article_id
                content.shopify_article_url = shopify_success.shopify_article_url
                content.shopify_published_at = datetime.now(timezone.utc)
                logger.info(
                    f"[PUBLISH] Shopify article saved content_id={content.id} "
                    f"article_id={shopify_success.shopify_article_id} "
                    f"url={shopify_success.shopify_article_url}"
                )

            if wp_success or wp_deferred:
                content.status = content_status_for_wordpress_status(
                    "future" if is_scheduled else publish_status
                )
            elif shopify_success:
                content.status = (
                    "published" if publish_status == "publish" else "draft"
                )
            else:
                content.status = "published"
        else:
            content.status = "failed"

        # Track per-site publish results — identity by platform-native integer IDs only
        now = datetime.now(timezone.utc)
        for r in results:
            existing_pr_stmt = select(ContentPublishingResult).where(
                ContentPublishingResult.content_id == content.id,
                ContentPublishingResult.site_id == r.site_id,
            )
            existing_pr = (await self.db.execute(existing_pr_stmt)).scalar_one_or_none()

            if r.success:
                # Scheduled WP: no post_id yet (plugin not called), background task publishes later
                if is_scheduled and not r.wordpress_post_id and not r.shopify_article_id:
                    pub_status = PublishingStatus.SCHEDULED
                elif publish_status == "publish":
                    pub_status = PublishingStatus.PUBLISHED
                elif publish_status == "pending" and r.wordpress_post_id:
                    pub_status = PublishingStatus.PENDING
                else:
                    pub_status = PublishingStatus.DRAFT
                scheduled_at_value = scheduled_at if pub_status == PublishingStatus.SCHEDULED else None
                if existing_pr:
                    existing_pr.wp_post_id = r.wordpress_post_id
                    existing_pr.shopify_article_id = r.shopify_article_id
                    existing_pr.shopify_blog_id = r.shopify_blog_id
                    existing_pr.external_url = r.wordpress_url or r.shopify_article_url
                    existing_pr.status = pub_status
                    existing_pr.scheduled_publish_at = scheduled_at_value
                    existing_pr.last_synced_at = now
                    existing_pr.sync_error = None
                else:
                    self.db.add(ContentPublishingResult(
                        content_id=content.id,
                        site_id=r.site_id,
                        wp_post_id=r.wordpress_post_id,
                        shopify_article_id=r.shopify_article_id,
                        shopify_blog_id=r.shopify_blog_id,
                        external_url=r.wordpress_url or r.shopify_article_url,
                        status=pub_status,
                        scheduled_publish_at=scheduled_at_value,
                        last_synced_at=now,
                    ))
            else:
                # Publish failed — update sync_error on existing record if present;
                # don't create a new record with no IDs as there's nothing to sync later.
                if existing_pr:
                    existing_pr.sync_error = r.error
                    existing_pr.status = PublishingStatus.UNKNOWN

        content.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        
        # Update embedding on publish as well to guarantee sync
        embed_service = ContentEmbeddingService(self.db)
        await embed_service.upsert_content_embedding(content.id, workspace_id)
        
        return results
