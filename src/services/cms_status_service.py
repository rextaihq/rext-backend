import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.content_models.publishing_result import ContentPublishingResult, PublishingStatus
from src.api.models.integrations.workspace_integration import WorkspaceIntegration
from src.web.wordpress import WordPressPublisher
from src.web.shopify import ShopifyConnector
from src.utils.logger import logger


class CMSStatusService:
    """Syncs per-site publishing state from external CMS platforms."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def sync_content_status(
        self, publishing_result_id: uuid.UUID
    ) -> Optional[ContentPublishingResult]:
        """
        Pull current status from the external CMS for one publishing record.
        Returns the updated record, or None if the record doesn't exist.
        """
        result = await self.db.get(ContentPublishingResult, publishing_result_id)
        if not result:
            logger.error(f"PublishingResult {publishing_result_id} not found.")
            return None

        integration = await self.db.get(WorkspaceIntegration, result.site_id)
        if not integration or not integration.is_active:
            logger.warning(f"Integration {result.site_id} inactive or missing — skipping sync.")
            return result

        try:
            if integration.integration_type == "wordpress":
                await self._sync_wordpress(result, integration)
            elif integration.integration_type == "shopify":
                await self._sync_shopify(result, integration)
            else:
                logger.warning(f"Unknown integration type '{integration.integration_type}' — skipping.")
                return result

            result.last_synced_at = datetime.now(timezone.utc)
            result.sync_error = None

        except Exception as e:
            logger.error(f"Sync failed for PublishingResult {result.id}: {e}")
            result.sync_error = str(e)
            result.status = PublishingStatus.UNKNOWN

        await self.db.flush()
        return result

    async def _sync_wordpress(
        self, result: ContentPublishingResult, integration: WorkspaceIntegration
    ) -> None:
        if not result.wp_post_id:
            logger.warning(f"PublishingResult {result.id} has no wp_post_id — cannot sync.")
            result.sync_error = "No WordPress post ID recorded; publish may have failed."
            return

        async with WordPressPublisher(
            site_url=integration.site_url,
            username=integration.username,
            app_password=integration.app_password,
            api_key=integration.api_key,
            api_endpoint=integration.api_endpoint,
        ) as wp:
            data = await wp.get_post_status(result.wp_post_id)

        raw_status = data.get("status")

        # WP REST returns 404 for trashed posts even when authenticated (unless admin token).
        # Map "trash" defensively but in practice it arrives as "deleted" via 404 handling.
        status_map = {
            "publish": PublishingStatus.PUBLISHED,
            "draft":   PublishingStatus.DRAFT,
            "pending": PublishingStatus.DRAFT,
            "private": PublishingStatus.DRAFT,
            "trash":   PublishingStatus.TRASHED,
            "deleted": PublishingStatus.DELETED,
        }
        result.status = status_map.get(raw_status, PublishingStatus.UNKNOWN)

        if data.get("link"):
            result.external_url = data["link"]

    async def _sync_shopify(
        self, result: ContentPublishingResult, integration: WorkspaceIntegration
    ) -> None:
        config = integration.config_json or {}
        connection_mode = str(config.get("connection_mode") or "").lower()

        # Bridge-mode stores have no direct Admin API access token on our side.
        # Sync is not possible without going through the bridge app.
        if connection_mode == "app_bridge" or not integration.api_key:
            logger.info(
                f"PublishingResult {result.id}: Shopify bridge mode — direct sync not supported. Skipping."
            )
            result.sync_error = "Bridge-mode Shopify: direct status sync not available."
            return

        if not result.shopify_article_id:
            logger.warning(f"PublishingResult {result.id} has no shopify_article_id — cannot sync.")
            result.sync_error = "No Shopify article ID recorded; publish may have failed."
            return

        async with ShopifyConnector(
            store_url=integration.site_url,
            access_token=integration.api_key,
        ) as shopify:
            data = await shopify.get_article_status(
                article_id=result.shopify_article_id,
                blog_id=result.shopify_blog_id,  # avoids guessing the blog
            )

        raw_status = data.get("status")
        status_map = {
            "published": PublishingStatus.PUBLISHED,
            "draft":     PublishingStatus.DRAFT,
            "deleted":   PublishingStatus.DELETED,
        }
        result.status = status_map.get(raw_status, PublishingStatus.UNKNOWN)

    async def get_active_publications(
        self, content_id: uuid.UUID
    ) -> List[ContentPublishingResult]:
        """
        Return all live or draft publications for a piece of content.
        Excludes deleted, trashed, and unknown records.
        """
        stmt = select(ContentPublishingResult).where(
            ContentPublishingResult.content_id == content_id,
            ContentPublishingResult.status.in_(
                [PublishingStatus.PUBLISHED, PublishingStatus.DRAFT]
            ),
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        return list(rows)
