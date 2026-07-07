"""
Google Integration Service - orchestration facade for GSC/GA4 tracking

Responsibilities:
- CRUD for per-WordPress-site GSC/GA4 mappings (GoogleSiteMapping).
- Discover which (mapping, integration, publishing_result) tuples need
  syncing, batched (no N+1), for the periodic scheduler.
- Read stored performance metrics for a content item, and trigger an
  on-demand refresh (explicit user action, not the publish path).
- schedule_post_publish_sync: the fire-and-forget hook called right after a
  WordPress publish succeeds. Fully decoupled from the caller's request/
  transaction (own DB session) and never raises.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    RextValidationException,
)
from src.api.models.content_models.content_performance_metric import (
    ContentPerformanceMetric,
    PerformanceMetricSource,
)
from src.api.models.content_models.publishing_result import ContentPublishingResult, PublishingStatus
from src.api.models.integrations.google_integration import GoogleIntegration
from src.api.models.integrations.google_site_mapping import GoogleSiteMapping
from src.config.google_config import google_config
from src.services.google_analytics_service import GoogleAnalyticsService
from src.services.google_oauth_service import GoogleOAuthService
from src.services.search_console_service import SearchConsoleService
from src.utils.logger import logger

# Strong references to in-flight fire-and-forget tasks, so they aren't
# garbage-collected mid-execution (see asyncio docs on create_task).
_background_tasks: set = set()

SyncTarget = Tuple[GoogleSiteMapping, GoogleIntegration, ContentPublishingResult]


class GoogleIntegrationService:
    """Orchestration facade used by routes, the publish flow, and the scheduler."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Site mapping CRUD
    # ------------------------------------------------------------------

    async def get_site_mapping(self, site_id: uuid.UUID) -> Optional[GoogleSiteMapping]:
        result = await self.db.execute(
            select(GoogleSiteMapping).where(
                GoogleSiteMapping.site_id == site_id,
                GoogleSiteMapping.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def upsert_site_mapping(
        self,
        *,
        workspace_id: uuid.UUID,
        site_id: uuid.UUID,
        gsc_site_url: Optional[str] = None,
        ga4_property_id: Optional[str] = None,
        is_active: bool = True,
    ) -> GoogleSiteMapping:
        result = await self.db.execute(
            select(GoogleSiteMapping).where(GoogleSiteMapping.site_id == site_id)
        )
        mapping = result.scalar_one_or_none()

        if mapping:
            if gsc_site_url is not None:
                mapping.gsc_site_url = gsc_site_url
            if ga4_property_id is not None:
                mapping.ga4_property_id = ga4_property_id
            mapping.is_active = is_active
            mapping.deleted_at = None
        else:
            mapping = GoogleSiteMapping(
                workspace_id=workspace_id,
                site_id=site_id,
                gsc_site_url=gsc_site_url,
                ga4_property_id=ga4_property_id,
                is_active=is_active,
            )
            self.db.add(mapping)

        await self.db.flush()
        return mapping

    async def remove_site_mapping(self, site_id: uuid.UUID) -> None:
        mapping = await self.get_site_mapping(site_id)
        if not mapping:
            raise ResourceNotFoundException(resource_type="GoogleSiteMapping", resource_id=str(site_id))
        mapping.is_active = False
        mapping.soft_delete()
        await self.db.flush()

    # ------------------------------------------------------------------
    # Scheduler support
    # ------------------------------------------------------------------

    async def list_sync_targets(
        self, workspace_id: Optional[uuid.UUID] = None
    ) -> List[SyncTarget]:
        """
        Batched discovery of everything eligible for a sync pass: active
        mappings, with an active Google connection for their workspace, and
        a PUBLISHED ContentPublishingResult for their site. 3 queries total
        regardless of N (mirrors CMSStatusService._bulk_sync).
        """
        mapping_query = select(GoogleSiteMapping).where(
            GoogleSiteMapping.is_active.is_(True),
            GoogleSiteMapping.deleted_at.is_(None),
        )
        if workspace_id:
            mapping_query = mapping_query.where(GoogleSiteMapping.workspace_id == workspace_id)
        mappings = (await self.db.execute(mapping_query)).scalars().all()
        if not mappings:
            return []

        workspace_ids = list({m.workspace_id for m in mappings})
        integrations = (await self.db.execute(
            select(GoogleIntegration).where(
                GoogleIntegration.workspace_id.in_(workspace_ids),
                GoogleIntegration.is_active.is_(True),
                GoogleIntegration.deleted_at.is_(None),
            )
        )).scalars().all()
        integration_by_workspace = {i.workspace_id: i for i in integrations}

        mapping_by_site = {
            m.site_id: m for m in mappings if m.workspace_id in integration_by_workspace
        }
        if not mapping_by_site:
            return []

        publishing_results = (await self.db.execute(
            select(ContentPublishingResult).where(
                ContentPublishingResult.site_id.in_(list(mapping_by_site.keys())),
                ContentPublishingResult.status == PublishingStatus.PUBLISHED,
            )
        )).scalars().all()

        targets: List[SyncTarget] = []
        for pr in publishing_results:
            mapping = mapping_by_site.get(pr.site_id)
            if not mapping:
                continue
            integration = integration_by_workspace.get(mapping.workspace_id)
            if not integration:
                continue
            targets.append((mapping, integration, pr))
        return targets

    # ------------------------------------------------------------------
    # Reading performance data
    # ------------------------------------------------------------------

    async def get_content_performance(
        self, *, content_id: uuid.UUID, workspace_id: uuid.UUID, days: int = 30
    ) -> Dict[str, List[Dict[str, Any]]]:
        since = datetime.now(timezone.utc).date() - timedelta(days=days)
        result = await self.db.execute(
            select(ContentPerformanceMetric)
            .where(
                ContentPerformanceMetric.content_id == content_id,
                ContentPerformanceMetric.workspace_id == workspace_id,
                ContentPerformanceMetric.metric_date >= since,
            )
            .order_by(ContentPerformanceMetric.metric_date.asc())
        )
        rows = result.scalars().all()

        return {
            "search_console": [
                {"date": r.metric_date.isoformat(), **r.metrics}
                for r in rows if r.source == PerformanceMetricSource.SEARCH_CONSOLE.value
            ],
            "analytics": [
                {"date": r.metric_date.isoformat(), **r.metrics}
                for r in rows if r.source == PerformanceMetricSource.ANALYTICS.value
            ],
        }

    async def refresh_content_performance(
        self, *, content_id: uuid.UUID, workspace_id: uuid.UUID, lookback_days: int = 30
    ) -> int:
        """On-demand sync backing the ``?refresh=true`` read endpoint."""
        oauth_service = GoogleOAuthService(self.db)
        integration = await oauth_service.get_active_integration(workspace_id)
        if not integration:
            raise RextValidationException(
                message="Google account is not connected for this workspace."
            )
        access_token = await oauth_service.get_valid_access_token(integration)

        prs = (await self.db.execute(
            select(ContentPublishingResult).where(
                ContentPublishingResult.content_id == content_id,
                ContentPublishingResult.status == PublishingStatus.PUBLISHED,
            )
        )).scalars().all()

        synced = 0
        for pr in prs:
            mapping = await self.get_site_mapping(pr.site_id)
            if not mapping or not mapping.is_active:
                continue
            try:
                synced += await SearchConsoleService(self.db).sync_publishing_result(
                    pr, mapping, access_token, lookback_days
                )
            except Exception:
                logger.warning(f"Refresh: Search Console sync failed for {pr.id}", exc_info=True)
            try:
                synced += await GoogleAnalyticsService(self.db).sync_publishing_result(
                    pr, mapping, access_token, lookback_days
                )
            except Exception:
                logger.warning(f"Refresh: GA4 sync failed for {pr.id}", exc_info=True)

        return synced


# ==============================================================================
# Post-publish trigger (fire-and-forget, own DB session)
# ==============================================================================

def schedule_post_publish_sync(publishing_result_id: uuid.UUID) -> None:
    """
    Kick off an immediate, best-effort GSC/GA4 sync attempt right after a
    WordPress publish succeeds. This is the literal "trigger the workflow
    after a WordPress post is successfully published" hook.

    Runs fully decoupled from the caller's request/DB session/transaction —
    safe to call *before* the caller's transaction has committed. The task
    polls (via its own short-lived sessions) for the row to become visible
    rather than assuming it's already committed — call sites in this codebase
    fire this right after ``flush()``, not after ``commit()``, since the
    commit happens later inside ``db_transaction_handler``. Never raises.
    """
    try:
        task = asyncio.create_task(_run_post_publish_sync(publishing_result_id))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
    except RuntimeError:
        logger.debug("No running event loop; skipping post-publish Google sync trigger.")
    except Exception:
        logger.exception("Failed to schedule post-publish Google sync (non-fatal).")


_POST_PUBLISH_MAX_ATTEMPTS = 5
_POST_PUBLISH_RETRY_DELAY_SECONDS = 2.0


async def _wait_until_published(publishing_result_id: uuid.UUID) -> bool:
    """
    Poll (fresh session per attempt, so newly committed data is visible) for
    the ContentPublishingResult to show status PUBLISHED. Bridges the race
    where this trigger fires right after ``flush()`` but before the caller's
    transaction actually commits — see ``schedule_post_publish_sync``.
    """
    from src.api.database.async_database import get_async_db_context

    for attempt in range(_POST_PUBLISH_MAX_ATTEMPTS):
        async with get_async_db_context() as db:
            pr = await db.get(ContentPublishingResult, publishing_result_id)
            if pr and pr.status == PublishingStatus.PUBLISHED:
                return True
        if attempt < _POST_PUBLISH_MAX_ATTEMPTS - 1:
            await asyncio.sleep(_POST_PUBLISH_RETRY_DELAY_SECONDS)
    return False


async def _run_post_publish_sync(publishing_result_id: uuid.UUID) -> None:
    from src.api.database.async_database import get_async_db_context

    try:
        if not await _wait_until_published(publishing_result_id):
            logger.warning(
                f"Post-publish Google sync: publishing_result={publishing_result_id} "
                "never became visible as PUBLISHED in time — the periodic sync job will "
                "pick it up on its next run instead."
            )
            return

        async with get_async_db_context() as db:
            pr = await db.get(ContentPublishingResult, publishing_result_id)
            if not pr:
                return

            mapping_result = await db.execute(
                select(GoogleSiteMapping).where(
                    GoogleSiteMapping.site_id == pr.site_id,
                    GoogleSiteMapping.is_active.is_(True),
                    GoogleSiteMapping.deleted_at.is_(None),
                )
            )
            mapping = mapping_result.scalar_one_or_none()
            if not mapping:
                return

            oauth_service = GoogleOAuthService(db)
            integration = await oauth_service.get_active_integration(mapping.workspace_id)
            if not integration:
                return

            access_token = await oauth_service.get_valid_access_token(integration)
            lookback_days = google_config.GOOGLE_SYNC_LOOKBACK_DAYS

            try:
                await SearchConsoleService(db).sync_publishing_result(
                    pr, mapping, access_token, lookback_days
                )
            except Exception:
                logger.warning(
                    f"Post-publish Search Console sync failed for publishing_result={publishing_result_id}",
                    exc_info=True,
                )

            try:
                await GoogleAnalyticsService(db).sync_publishing_result(
                    pr, mapping, access_token, lookback_days
                )
            except Exception:
                logger.warning(
                    f"Post-publish GA4 sync failed for publishing_result={publishing_result_id}",
                    exc_info=True,
                )
    except Exception:
        logger.exception(
            f"Post-publish Google sync failed entirely for publishing_result={publishing_result_id}"
        )
