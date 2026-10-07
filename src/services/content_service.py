"""
Content Service - Business Logic for Content Operations

Handles multi-table persistence for content, SEO, and media.
Strictly separates core content from SEO metadata.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from uuid import UUID

import markdown
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.config import settings
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    ResourceNotFoundException,
    RextValidationException,
)
from src.api.models.content_models.content import Content
from src.api.models.content_models.content_seo_data import ContentSEOData
from src.api.models.content_models.publishing_result import (
    ContentPublishingResult,
    PublishingStatus,
)
from src.api.models.integrations.workspace_integration import WorkspaceIntegration
from src.api.schema.content_schema import (
    ContentCreate,
    ContentSEODataSchema,
    ContentUpdate,
    PublishResponse,
)
from src.flow.engines.content.generation.content_generation import _is_placeholder_image_url
from src.services.content_activity import (
    ACTION_CREATED,
    ACTION_DELETED,
    ACTION_UPDATED,
    record_content_activity,
    status_change_action,
)
from src.services.content_checklist import build_checklist
from src.services.content_embedding_service import ContentEmbeddingService
from src.utils.datetime_utils import resolve_scheduled_datetime
from src.utils.image_placeholder import strip_unresolved_placeholders
from src.utils.logger import logger
from src.utils.slug_utils import generate_unique_slug, slugify
from src.utils.wordpress_status import (
    content_status_for_wordpress_status,
    normalize_wordpress_post_status,
)
from src.web.shopify_bridge import ShopifyAppBridge
from src.web.wordpress import WordPressPublisher


def _extract_feature_image_url(images_data: Any) -> Optional[str]:
    """Extract the primary image URL from images_data, skipping hallucinated/placeholder links."""
    if isinstance(images_data, dict):
        keys = (
            "featured_image_url",
            "feature_image_url",
            "featured_image",
            "image_url",
            "source_url",
            "src",
            "url",
        )
        for key in keys:
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
                    if (
                        isinstance(value, str)
                        and value.strip()
                        and not _is_placeholder_image_url(value)
                    ):
                        return value.strip()
    return None


async def notify_content_published(content: Content, workspace_id) -> None:
    """In-app 'Content Published' notification for the content's author."""
    if not content.created_by_user_id:
        return
    from src.services.notification_helper import notify_now

    await notify_now(
        user_id=content.created_by_user_id,
        pref_flag="gen_published",
        message=f'"{content.title}" was published successfully.',
        payload={
            "content_id": str(content.id),
            "url": content.wordpress_url or content.shopify_article_url,
        },
        workspace_id=workspace_id,
    )


class ContentService:
    """
    Service for content business logic.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _title_taken(
        self, workspace_id: UUID, title: str, exclude_id: Optional[UUID] = None
    ) -> bool:
        """Whether a live article in the workspace already has this title (several may)."""
        query = select(Content.id).where(
            Content.workspace_id == workspace_id,
            Content.title == title,
            Content.deleted_at.is_(None),
        )
        if exclude_id is not None:
            query = query.where(Content.id != exclude_id)
        return (await self.db.execute(query.limit(1))).first() is not None

    async def create_content(
        self, workspace_id: UUID, user_id: UUID, data: ContentCreate
    ) -> Content:
        """Create new content with nested SEO data.

        Idempotent by langgraph_thread_id: if this generation thread already
        produced content in the workspace, the existing row is updated instead
        of creating a duplicate. This lets the generation graph auto-save the
        finished article while the editor's manual Save reconciles to the same
        row (no duplicate, no title-collision error).
        """
        # Idempotency: reconcile to the existing row for this generation thread.
        if data.langgraph_thread_id:
            existing_by_thread = (
                await self.db.execute(
                    select(Content).where(
                        Content.workspace_id == workspace_id,
                        Content.langgraph_thread_id == data.langgraph_thread_id,
                        Content.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
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
                    images_data=data.images_data,
                    links_data=data.links_data,
                    schema_markup=data.schema_markup,
                    persona_id=data.persona_id,
                )
                return await self.update_content(
                    existing_by_thread.id,
                    workspace_id,
                    user_id,
                    update_payload,
                    _skip_activity_log=True,
                )

        # A title must be new in the workspace only for an article written by hand. A generated
        # article (it carries its generation thread) is always saved: the title step offers the
        # same titles for a keyword, so two articles on one keyword can share a title, and the
        # slug is unique anyway (generate_unique_slug). Refusing it lost the article (G55).
        if not data.langgraph_thread_id and await self._title_taken(workspace_id, data.title):
            raise DuplicateResourceException(
                resource_type="Content", conflicting_field="title", conflicting_value=data.title
            )

        base_slug = slugify(data.title)
        # uq_content_workspace_slug covers the trash, so a trashed article's slug is taken too.
        unique_slug = await generate_unique_slug(
            self.db, base_slug, Content, workspace_id=workspace_id, include_deleted=True
        )

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
            persona_id=data.persona_id,
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
                seo_details=data.seo_data.seo_details,
            )
            self.db.add(seo_record)
            content.seo_data = seo_record  # Link relationship to avoid lazy loading later

        await self.db.flush()
        logger.info(f"Content created: {content.id}")

        # Upsert embedding synchronously after flush
        embed_service = ContentEmbeddingService(self.db)
        await embed_service.upsert_content_embedding(content.id, workspace_id)

        await record_content_activity(
            self.db,
            content,
            ACTION_CREATED,
            user_id=user_id,
            workspace_id=workspace_id,
        )
        return content

    async def update_content(
        self,
        content_id: UUID,
        workspace_id: UUID,
        user_id: UUID,
        data: ContentUpdate,
        *,
        _skip_activity_log: bool = False,
    ) -> Content:
        """Update existing content and its nested relations."""
        content = await self._get_content_or_404(content_id, workspace_id, include_seo=True)

        if data.title and data.title != content.title:
            # The same rule as create_content: only an article written by hand needs a new title.
            generated = data.langgraph_thread_id or content.langgraph_thread_id
            if not generated and await self._title_taken(
                workspace_id, data.title, exclude_id=content_id
            ):
                raise DuplicateResourceException(
                    resource_type="Content", conflicting_field="title", conflicting_value=data.title
                )

            content.slug = await generate_unique_slug(
                self.db,
                slugify(data.title),
                Content,
                workspace_id=workspace_id,
                exclude_id=content.id,
                include_deleted=True,
            )
            content.title = data.title

        # Captured before the assignment: the transition is the fact the
        # activity feed is recording, and once the column is overwritten there
        # is nothing left to say what it moved from.
        previous_status = content.status
        if data.status and data.status != content.status:
            await self._validate_status_transition(content.status, data.status)
            content.status = data.status

        # Update core fields
        updatable_fields = [
            "content_language",
            "introduction",
            "body_markdown",
            "body_html",
            "tags",
            "category",
            "images_data",
            "links_data",
            "schema_markup",
            "langgraph_thread_id",
            "persona_id",
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
                "meta_title",
                "meta_description",
                "focus_keyphrase",
                "keyphrase_density",
                "secondary_keywords",
                "search_intent",
                "seo_score",
                "readability_score",
                "trust_score",
                "seo_details",
            ]
            for field in seo_fields:
                val = getattr(data.seo_data, field, None)
                if val is not None:
                    setattr(seo, field, val)

        content.updated_at = datetime.now(timezone.utc)
        await self.db.flush()

        # Only upsert embedding if title or introduction might have changed
        # We can optimize by just running it on every update for safety, as requested by the user.
        embed_service = ContentEmbeddingService(self.db)
        await embed_service.upsert_content_embedding(content.id, workspace_id)

        await self.db.refresh(content)

        # A status change is its own kind of event, so it is filed as one
        # rather than as an ordinary edit that happens to differ.
        if not _skip_activity_log:
            changed = content.status != previous_status
            await record_content_activity(
                self.db,
                content,
                status_change_action(previous_status, content.status)
                if changed
                else ACTION_UPDATED,
                user_id=user_id,
                workspace_id=workspace_id,
                previous_status=previous_status if changed else None,
            )
        return content

    async def delete_content(
        self, content_id: UUID, workspace_id: UUID, user_id: Optional[UUID] = None
    ) -> None:
        content = await self._get_content_or_404(content_id, workspace_id)
        previous_status = content.status
        content.deleted_at = datetime.now(timezone.utc)
        content.deleted_by = user_id
        await self.db.flush()

        # Written while the title is still in hand. This row is the only thing
        # that will report the deletion afterwards: the article is soft-deleted
        # and drops out of every listing, so nothing else can.
        await record_content_activity(
            self.db,
            content,
            ACTION_DELETED,
            user_id=user_id,
            workspace_id=workspace_id,
            previous_status=previous_status,
        )

    async def list_content(
        self,
        workspace_id: UUID,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        query = (
            select(Content)
            .where(Content.workspace_id == workspace_id, Content.deleted_at.is_(None))
            .options(selectinload(Content.seo_data))
        )
        if status:
            query = query.where(Content.status == status)

        count_query = (
            select(func.count())
            .select_from(Content)
            .where(Content.workspace_id == workspace_id, Content.deleted_at.is_(None))
        )
        if status:
            count_query = count_query.where(Content.status == status)

        total_count = (await self.db.execute(count_query)).scalar()
        result = await self.db.execute(
            query.order_by(Content.created_at.desc()).offset(offset).limit(limit)
        )
        items = result.scalars().all()

        # Fetch publishing results for these items to show current live status
        content_ids = [c.id for c in items]
        pub_results = {}
        if content_ids:
            pub_query = select(ContentPublishingResult).where(
                ContentPublishingResult.content_id.in_(content_ids)
            )
            pub_data = (await self.db.execute(pub_query)).scalars().all()
            for pr in pub_data:
                if pr.content_id not in pub_results:
                    pub_results[pr.content_id] = []
                pub_results[pr.content_id].append(
                    {
                        "site_id": str(pr.site_id),
                        "status": pr.status,
                        "url": pr.external_url,
                        "last_synced": pr.last_synced_at.isoformat() if pr.last_synced_at else None,
                    }
                )

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
            "offset": offset,
        }

    async def get_content(self, content_id: UUID, workspace_id: UUID) -> Dict[str, Any]:
        content = await self._get_content_or_404(content_id, workspace_id, include_seo=True)
        data = content.to_dict(include_relationships=["seo_data"])
        seo = content.seo_data
        data["checklist"] = (
            build_checklist(readability_score=seo.readability_score, seo_details=seo.seo_details)
            if seo is not None
            else None
        )
        return data

    async def publish_content(self, content_id: UUID, workspace_id: UUID, user_id: UUID) -> Content:
        content = await self._get_content_or_404(content_id, workspace_id)
        if content.status != "ready":
            raise RextValidationException(message="Content must be 'ready' to publish")
        if not content.body_markdown:
            raise RextValidationException(message="Cannot publish empty content")
        previous_status = content.status
        content.status = "published"
        content.updated_at = datetime.now(timezone.utc)
        await record_content_activity(
            self.db,
            content,
            status_change_action(previous_status, content.status),
            user_id=user_id,
            workspace_id=workspace_id,
            previous_status=previous_status,
        )
        return content

    async def _get_content_or_404(
        self, content_id: UUID, workspace_id: UUID, include_seo: bool = False
    ) -> Content:
        query = select(Content).where(
            Content.id == content_id,
            Content.workspace_id == workspace_id,
            Content.deleted_at.is_(None),
        )
        if include_seo:
            query = query.options(selectinload(Content.seo_data))
        content = (await self.db.execute(query)).scalar_one_or_none()
        if not content:
            raise ResourceNotFoundException(resource_type="Content", resource_id=str(content_id))
        return content

    async def _validate_status_transition(self, current: str, new: str) -> None:
        ALLOWED = {
            "draft": ["generating", "ready", "review", "archived", "scheduled", "published"],
            "generating": ["ready", "failed", "draft"],
            "ready": ["published", "review", "draft", "archived", "generating", "scheduled"],
            "review": ["published", "ready", "draft", "archived", "scheduled"],
            "published": ["archived", "ready", "draft", "trashed", "deleted", "scheduled"],
            "scheduled": ["published", "failed", "draft", "archived"],
            "archived": ["draft"],
            "failed": ["draft", "generating", "archived"],
            "trashed": ["draft", "deleted", "published"],
            "deleted": ["draft", "published"],
        }
        if new not in ALLOWED.get(current, []):
            raise RextValidationException(message=f"Invalid transition: {current} -> {new}")

    async def wordpress_publish_context(self, content: Content, site) -> Dict[str, Any]:
        """What a single-site publish needs to know beyond the article itself:
        the post a previous publish left on that site, and the author persona
        chosen for the article in the outline step."""
        persona = await self.author_persona_for(content)
        existing = await self.existing_wordpress_post_ids(content, [site])
        return {
            "post_id": existing.get(site.id),
            "author_name": (persona.full_name or persona.name) if persona else None,
            "author_email": persona.email if persona else None,
        }

    async def author_persona_for(self, content: Content):
        """The author persona chosen for this article in the outline step, if any.

        Returns None when the article was written with no persona, or when the
        persona has since been deleted — in both cases WordPress publishes under
        the connected account, as it did before a persona could be chosen.
        """
        persona_id = getattr(content, "persona_id", None)
        if not persona_id:
            return None
        from src.api.models.knowledge_models.persona_model import Persona

        persona = (
            await self.db.execute(
                # A persona in the trash credits no one (G45).
                select(Persona).where(Persona.id == persona_id, Persona.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
        if persona is None:
            logger.warning(
                "[PUBLISH] content_id=%s references persona %s which no longer exists",
                content.id,
                persona_id,
            )
        return persona

    async def existing_wordpress_post_ids(self, content: Content, sites) -> Dict[UUID, int]:
        """The WordPress post each site already holds for this content, by site ID.

        Publishing the same article twice must edit the post readers already
        have, not leave a duplicate behind. Identity comes from the per-site
        publishing result; ``content.wordpress_post_id`` is the fallback for
        rows published before those results were recorded, and is only trusted
        for the site its recorded URL actually points at.
        """
        wordpress_site_ids = {site.id for site in sites if site.integration_type != "shopify"}
        if not wordpress_site_ids:
            return {}

        existing: Dict[UUID, int] = {}
        results = (
            (
                await self.db.execute(
                    select(ContentPublishingResult).where(
                        ContentPublishingResult.content_id == content.id,
                        ContentPublishingResult.site_id.in_(wordpress_site_ids),
                    )
                )
            )
            .scalars()
            .all()
        )
        for result in results:
            if result.wp_post_id:
                existing[result.site_id] = int(result.wp_post_id)

        if content.wordpress_post_id and content.wordpress_url:
            published_host = urlparse(str(content.wordpress_url)).netloc.lower()
            for site in sites:
                if site.id in existing or site.id not in wordpress_site_ids:
                    continue
                site_host = urlparse(str(site.site_url or "")).netloc.lower()
                if site_host and site_host == published_host:
                    existing[site.id] = int(content.wordpress_post_id)

        return existing

    async def publish_to_sites(
        self,
        content: Content,
        workspace_id: UUID,
        site_id: Optional[UUID] = None,
        publish_status: str = "publish",
        scheduled_at: Optional[datetime] = None,
        user_timezone: str = "UTC",
        user_id: Optional[UUID] = None,
    ) -> List[PublishResponse]:
        """
        Publish content to active WordPress site(s) in the workspace.
        """
        publish_status = normalize_wordpress_post_status(publish_status)
        # Held from before any site is contacted: what this run did to the
        # article is the difference between this and the status on the way out,
        # and that difference is what the activity feed records.
        status_before_publish = content.status

        # A naive scheduled_at is wall-clock time in the user's account timezone
        # (never the server's or browser's) — normalize to UTC before any
        # comparison or storage so "10:00 AM" always means the same instant
        # regardless of where the request came from.
        if scheduled_at is not None:
            scheduled_at = resolve_scheduled_datetime(scheduled_at, user_timezone)

        # Fetch active sites (optionally filtered by site_id)
        sites_query = select(WorkspaceIntegration).where(
            WorkspaceIntegration.workspace_id == workspace_id,
            WorkspaceIntegration.is_active.is_(True),
        )
        if site_id:
            sites_query = sites_query.where(WorkspaceIntegration.id == site_id)

        sites_result = await self.db.execute(sites_query)
        sites = sites_result.scalars().all()

        if not sites:
            logger.warning(f"No active sites found for workspace {workspace_id}")
            raise RextValidationException(
                message=(
                    "No active sites found in this workspace. "
                    "Please connect a site before publishing."
                )
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
        from sqlalchemy import inspect as sa_inspect
        from sqlalchemy.orm.base import NO_VALUE

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
                trust_score=content.seo_data.trust_score,
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

        # The author persona chosen in the content outline step. Resolved once,
        # here, so every site in this publish credits the same author.
        author_persona = await self.author_persona_for(content)
        author_name = None
        author_email = None
        if author_persona is not None:
            author_name = author_persona.full_name or author_persona.name
            author_email = author_persona.email
            logger.info("[PUBLISH] content_id=%s author persona=%r", content.id, author_name)

        # WordPress post IDs a previous publish of this content created, per site.
        existing_wp_post_ids = await self.existing_wordpress_post_ids(content, sites)

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
                    # A manual-upload image placeholder left unresolved/undismissed
                    # in the editor is not a real image URL — never publish it as a
                    # broken <img> on the live site.
                    body_to_use = strip_unresolved_placeholders(body_to_use) or ""

                    is_published = publish_status == "publish"
                    if use_bridge:
                        logger.info(
                            f"[PUBLISH] Shopify bridge mode for site={site.site_url} "
                            f"SHOPIFY_BRIDGE_BASE_URL={settings.SHOPIFY_BRIDGE_BASE_URL!r} "
                            f"endpoint={settings.SHOPIFY_BRIDGE_PUBLISH_ENDPOINT!r} "
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
                            store_url=site.site_url, access_token=site.api_key
                        ) as shopify:
                            shop_resp = await shopify.publish_blog_post(
                                title=content.title,
                                body_html=body_to_use,
                                tags=content.tags,
                                published=is_published,
                                handle=content.slug,
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
                        api_key=site.api_key,
                    ) as wp_publisher:
                        # Republishing updates the post the first publish
                        # created, once it is confirmed to still be there.
                        existing_post_id = await wp_publisher.confirm_existing_post(
                            existing_wp_post_ids.get(site.id)
                        )
                        logger.info(
                            "[PUBLISH] WordPress site=%s mode=%s post_id=%s",
                            site.site_url,
                            "update" if existing_post_id else "create",
                            existing_post_id,
                        )
                        wp_response = await wp_publisher.publish_post(
                            data=content_data,
                            status=publish_status,
                            post_id=existing_post_id,
                            author_name=author_name,
                            author_email=author_email,
                        )
                        if author_name and not wp_response.get("author_applied", True):
                            logger.error(
                                "[PUBLISH] site=%s published post_id=%s but WordPress did not "
                                "credit persona=%r",
                                site.site_url,
                                wp_response.get("post_id"),
                                author_name,
                            )
                    return PublishResponse(
                        site_id=site.id,
                        site_url=site.site_url,
                        success=True,
                        wordpress_post_id=wp_response.get("post_id"),
                        wordpress_url=wp_response.get("link"),
                    )
            except Exception as e:
                logger.error(
                    f"[PUBLISH] FAILED site={site.site_url} type={site.integration_type} "
                    f"error={str(e)}"
                )
                return PublishResponse(
                    site_id=site.id, site_url=site.site_url, success=False, error=str(e)
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
            wp_deferred = (
                next(
                    (
                        r
                        for r in successful_results
                        if not r.wordpress_post_id and not r.shopify_article_id
                    ),
                    None,
                )
                if is_scheduled
                else None
            )

            if wp_success:
                content.wordpress_post_id = wp_success.wordpress_post_id
                content.wordpress_url = wp_success.wordpress_url
                content.wordpress_published_at = (
                    datetime.now(timezone.utc) if publish_status == "publish" else None
                )
            elif wp_deferred:
                # Store scheduled_at for calendar display
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
                content.status = "published" if publish_status == "publish" else "draft"
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
                scheduled_at_value = (
                    scheduled_at if pub_status == PublishingStatus.SCHEDULED else None
                )
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
                    self.db.add(
                        ContentPublishingResult(
                            content_id=content.id,
                            site_id=r.site_id,
                            wp_post_id=r.wordpress_post_id,
                            shopify_article_id=r.shopify_article_id,
                            shopify_blog_id=r.shopify_blog_id,
                            external_url=r.wordpress_url or r.shopify_article_url,
                            status=pub_status,
                            scheduled_publish_at=scheduled_at_value,
                            last_synced_at=now,
                        )
                    )
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

        if content.status != status_before_publish:
            await record_content_activity(
                self.db,
                content,
                status_change_action(status_before_publish, content.status),
                user_id=user_id,
                workspace_id=workspace_id,
                previous_status=status_before_publish,
            )

        # Drafts, pending review and scheduled posts are not "published" yet;
        # scheduled ones notify when the scheduler actually publishes them.
        if content.status == "published":
            await notify_content_published(content, workspace_id)

        return results
