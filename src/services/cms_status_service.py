import asyncio
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.content_models.publishing_result import ContentPublishingResult, PublishingStatus
from src.api.models.content_models.content import Content
from src.api.models.integrations.workspace_integration import WorkspaceIntegration
from src.web.wordpress import WordPressPublisher
from src.web.shopify import ShopifyConnector
from src.utils.logger import logger

_SYNC_CONCURRENCY = 10  # max parallel HTTP calls per site


class CMSStatusService:
    """Syncs per-site publishing state from external CMS platforms."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # -------------------------------------------------------------------------
    # Single-record sync (used by the per-content API endpoint)
    # -------------------------------------------------------------------------

    async def sync_content_status(
        self, publishing_result_id: uuid.UUID
    ) -> Optional[ContentPublishingResult]:
        """Pull current status from CMS for one publishing record."""
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

    # -------------------------------------------------------------------------
    # Bulk sync (batched DB + concurrent HTTP, no N+1)
    # -------------------------------------------------------------------------

    async def bulk_sync_workspace(
        self, workspace_id: uuid.UUID
    ) -> dict:
        """
        Sync all publishing records for a workspace in one pass.

        - 1 DB query to fetch all records
        - 1 DB query per unique site to fetch integrations
        - HTTP calls run concurrently (up to _SYNC_CONCURRENCY parallel)
        - 1 batch flush at the end
        """
        return await self._bulk_sync(workspace_id=workspace_id)

    async def bulk_sync_all(self) -> dict:
        """Sync every publishing record across all workspaces."""
        return await self._bulk_sync(workspace_id=None)

    async def _bulk_sync(self, workspace_id: Optional[uuid.UUID]) -> dict:
        now = datetime.now(timezone.utc)

        # --- 1. Fetch all publishing records in one query ---
        stmt = (
            select(ContentPublishingResult)
            .join(Content, Content.id == ContentPublishingResult.content_id)
            .where(
                Content.deleted_at.is_(None),
                ContentPublishingResult.status.in_([
                    PublishingStatus.PUBLISHED,
                    PublishingStatus.DRAFT,
                    PublishingStatus.UNKNOWN,
                ]),
            )
        )
        if workspace_id:
            stmt = stmt.where(Content.workspace_id == workspace_id)

        rows = (await self.db.execute(stmt)).scalars().all()

        if not rows:
            logger.info("[BulkSync] No publishing records to sync.")
            return {"synced": 0, "failed": 0, "skipped": 0}

        # --- 2. Fetch all unique integrations in one query ---
        site_ids = list({r.site_id for r in rows})
        integrations_rows = (
            await self.db.execute(
                select(WorkspaceIntegration).where(
                    WorkspaceIntegration.id.in_(site_ids)
                )
            )
        ).scalars().all()

        integrations: dict[uuid.UUID, WorkspaceIntegration] = {
            i.id: i for i in integrations_rows
        }

        # --- 3. Group records by site ---
        by_site: dict[uuid.UUID, list[ContentPublishingResult]] = {}
        for r in rows:
            by_site.setdefault(r.site_id, []).append(r)

        # --- 4. Concurrent HTTP sync per site ---
        synced = failed = skipped = 0
        sem = asyncio.Semaphore(_SYNC_CONCURRENCY)

        async def _sync_one(rec: ContentPublishingResult, integration: WorkspaceIntegration):
            nonlocal synced, failed, skipped
            async with sem:
                try:
                    if integration.integration_type == "wordpress":
                        await self._sync_wordpress(rec, integration)
                    elif integration.integration_type == "shopify":
                        await self._sync_shopify(rec, integration)
                    else:
                        skipped += 1
                        return
                    rec.last_synced_at = now
                    rec.sync_error = None
                    synced += 1
                except Exception as e:
                    logger.error(f"[BulkSync] Failed {rec.id}: {e}")
                    rec.sync_error = str(e)
                    rec.status = PublishingStatus.UNKNOWN
                    failed += 1

        tasks = []
        for site_id, site_records in by_site.items():
            integration = integrations.get(site_id)
            if not integration or not integration.is_active:
                skipped += len(site_records)
                logger.warning(f"[BulkSync] Site {site_id} inactive/missing — skipping {len(site_records)} record(s).")
                continue
            for rec in site_records:
                tasks.append(_sync_one(rec, integration))

        await asyncio.gather(*tasks)

        # --- 5. Propagate CMS status → content.status ---
        await self._propagate_cms_status_to_content(rows)

        # --- 6. Single batch flush ---
        await self.db.flush()

        logger.info(f"[BulkSync] Done — synced={synced} failed={failed} skipped={skipped}")
        return {"synced": synced, "failed": failed, "skipped": skipped}

    # -------------------------------------------------------------------------
    # Status propagation
    # -------------------------------------------------------------------------

    async def _propagate_cms_status_to_content(
        self, pub_records: list[ContentPublishingResult]
    ) -> None:
        """
        Derive content.status from publishing results and update the content row.

        Priority across all sites for a given content_id:
          any PUBLISHED  → published
          any DRAFT      → draft (if nothing published)
          all TRASHED    → trashed
          all DELETED    → deleted
          otherwise      → leave content.status unchanged
        """
        # Group by content_id
        by_content: dict[uuid.UUID, list[PublishingStatus]] = {}
        for rec in pub_records:
            by_content.setdefault(rec.content_id, []).append(rec.status)

        if not by_content:
            return

        content_ids = list(by_content.keys())
        content_rows = (
            await self.db.execute(
                select(Content).where(Content.id.in_(content_ids))
            )
        ).scalars().all()
        content_map: dict[uuid.UUID, Content] = {c.id: c for c in content_rows}

        # Status priority map (lower index = higher priority)
        _PRIORITY = [
            PublishingStatus.PUBLISHED,
            PublishingStatus.DRAFT,
            PublishingStatus.TRASHED,
            PublishingStatus.DELETED,
        ]

        _CMS_TO_CONTENT = {
            PublishingStatus.PUBLISHED: "published",
            PublishingStatus.DRAFT:     "draft",
            PublishingStatus.TRASHED:   "trashed",
            PublishingStatus.DELETED:   "deleted",
        }

        for content_id, statuses in by_content.items():
            content = content_map.get(content_id)
            if not content:
                continue

            # Pick highest-priority status present across all sites
            derived = None
            for p in _PRIORITY:
                if p in statuses:
                    derived = _CMS_TO_CONTENT[p]
                    break

            if derived and content.status != derived:
                logger.info(
                    f"[BulkSync] content {content_id}: {content.status} → {derived} (from CMS)"
                )
                content.status = derived

    # -------------------------------------------------------------------------
    # CMS-specific helpers
    # -------------------------------------------------------------------------

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
        if str(config.get("connection_mode") or "").lower() == "app_bridge" or not integration.api_key:
            logger.info(f"PublishingResult {result.id}: Shopify bridge mode — direct sync not supported.")
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
                blog_id=result.shopify_blog_id,
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
        """Return all live or draft publications for a piece of content."""
        stmt = select(ContentPublishingResult).where(
            ContentPublishingResult.content_id == content_id,
            ContentPublishingResult.status.in_(
                [PublishingStatus.PUBLISHED, PublishingStatus.DRAFT]
            ),
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        return list(rows)
