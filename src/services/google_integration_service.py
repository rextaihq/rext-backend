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

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    RextValidationException,
)
from src.api.models.content_models.content import Content
from src.api.models.content_models.content_performance_metric import (
    ContentPerformanceMetric,
    PerformanceMetricSource,
)
from src.api.models.content_models.publishing_result import ContentPublishingResult, PublishingStatus
from src.api.models.integrations.google_integration import GoogleIntegration
from src.api.models.integrations.google_site_mapping import GoogleSiteMapping
from src.api.models.integrations.workspace_integration import WorkspaceIntegration
from src.config.google_config import google_config
from src.services.google_analytics_service import GoogleAnalyticsService
from src.services.google_oauth_service import GoogleOAuthService
from src.services.search_console_service import SearchConsoleService
from src.utils.logger import logger

# Strong references to in-flight fire-and-forget tasks, so they aren't
# garbage-collected mid-execution (see asyncio docs on create_task).
_background_tasks: set = set()

SyncTarget = Tuple[GoogleSiteMapping, GoogleIntegration, ContentPublishingResult]
SiteSyncTarget = Tuple[GoogleSiteMapping, GoogleIntegration]


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
    # Onboarding flow (setup status, site selection, content selection)
    # ------------------------------------------------------------------

    async def get_setup_status(
        self, workspace_id: uuid.UUID, google_connected: bool
    ) -> Dict[str, Any]:
        """Cheap DB-only counts driving the onboarding gate — no Google calls."""
        wp_sites = (await self.db.execute(
            select(WorkspaceIntegration.id).where(
                WorkspaceIntegration.workspace_id == workspace_id,
                WorkspaceIntegration.integration_type.ilike("wordpress"),
            )
        )).scalars().all()

        mappings = (await self.db.execute(
            select(GoogleSiteMapping).where(
                GoogleSiteMapping.workspace_id == workspace_id,
                GoogleSiteMapping.is_active.is_(True),
                GoogleSiteMapping.deleted_at.is_(None),
            )
        )).scalars().all()
        selected_sites = len(mappings)
        last_synced_at = max(
            (m.last_synced_at for m in mappings if m.last_synced_at), default=None
        )

        tracked_content = 0
        if wp_sites:
            tracked_content = (await self.db.scalar(
                select(func.count()).select_from(ContentPublishingResult).where(
                    ContentPublishingResult.site_id.in_(wp_sites),
                    ContentPublishingResult.status == PublishingStatus.PUBLISHED,
                    ContentPublishingResult.tracking_enabled.is_(True),
                )
            )) or 0

        # Content selection is no longer a blocking step — configuring a site
        # auto-enrolls its published articles, so setup is complete once a
        # site is selected. tracked_content is still reported (informational).
        if not google_connected:
            step = "connect_google"
        elif selected_sites == 0:
            step = "select_site"
        else:
            step = "ready"

        return {
            "google_connected": google_connected,
            "wordpress_sites": len(wp_sites),
            "selected_sites": selected_sites,
            "tracked_content": tracked_content,
            "last_synced_at": last_synced_at,
            "step": step,
        }

    async def list_wordpress_sites_with_mappings(
        self, workspace_id: uuid.UUID
    ) -> List[Dict[str, Any]]:
        """Connected WordPress sites, each with its current mapping (if any)."""
        sites = (await self.db.execute(
            select(WorkspaceIntegration).where(
                WorkspaceIntegration.workspace_id == workspace_id,
                WorkspaceIntegration.integration_type.ilike("wordpress"),
            )
        )).scalars().all()
        if not sites:
            return []

        mappings = (await self.db.execute(
            select(GoogleSiteMapping).where(
                GoogleSiteMapping.site_id.in_([s.id for s in sites]),
                GoogleSiteMapping.deleted_at.is_(None),
            )
        )).scalars().all()
        mapping_by_site = {m.site_id: m for m in mappings}

        return [
            {
                "site_id": site.id,
                "site_url": site.site_url,
                "is_active": site.is_active,
                "mapping": (
                    mapping_by_site[site.id].to_dict()
                    if site.id in mapping_by_site else None
                ),
            }
            for site in sites
        ]

    async def select_sites(
        self, workspace_id: uuid.UUID, selections: List[Dict[str, Any]]
    ) -> List[GoogleSiteMapping]:
        """
        Declarative batch site selection: every listed site gets an active
        mapping with the given GSC/GA4 properties; previously mapped sites
        not in the list are deactivated. GA4 validation is the route's job
        (needs an access token) — this only persists.
        """
        selected_ids = {s["site_id"] for s in selections}

        existing = (await self.db.execute(
            select(GoogleSiteMapping).where(
                GoogleSiteMapping.workspace_id == workspace_id,
                GoogleSiteMapping.deleted_at.is_(None),
            )
        )).scalars().all()
        for mapping in existing:
            if mapping.site_id not in selected_ids and mapping.is_active:
                mapping.is_active = False

        result: List[GoogleSiteMapping] = []
        for selection in selections:
            mapping = await self.upsert_site_mapping(
                workspace_id=workspace_id,
                site_id=selection["site_id"],
                gsc_site_url=selection.get("gsc_site_url"),
                ga4_property_id=selection.get("ga4_property_id"),
                is_active=True,
            )
            result.append(mapping)

        # Configuring a site implies tracking everything published on it —
        # the dashboard aggregates all articles without a separate
        # content-selection step. PUT /tracked-content remains as an opt-out.
        if selected_ids:
            now = datetime.now(timezone.utc)
            untracked = (await self.db.execute(
                select(ContentPublishingResult).where(
                    ContentPublishingResult.site_id.in_(selected_ids),
                    ContentPublishingResult.status == PublishingStatus.PUBLISHED,
                    ContentPublishingResult.tracking_enabled.is_(False),
                )
            )).scalars().all()
            for pr in untracked:
                pr.tracking_enabled = True
                pr.tracking_enabled_at = now

        await self.db.flush()
        return result

    async def list_published_content(
        self, site_id: uuid.UUID
    ) -> List[Dict[str, Any]]:
        """Published articles on one site, with their tracking state."""
        rows = (await self.db.execute(
            select(ContentPublishingResult, Content)
            .join(Content, Content.id == ContentPublishingResult.content_id)
            .where(
                ContentPublishingResult.site_id == site_id,
                ContentPublishingResult.status == PublishingStatus.PUBLISHED,
                Content.deleted_at.is_(None),
            )
            .order_by(ContentPublishingResult.created_at.desc())
        )).all()

        return [
            {
                "content_id": content.id,
                "publishing_result_id": pr.id,
                "title": content.title,
                "external_url": pr.external_url or content.wordpress_url,
                "published_at": content.wordpress_published_at or pr.created_at,
                "tracked": pr.tracking_enabled,
            }
            for pr, content in rows
        ]

    async def set_tracked_content(
        self, site_id: uuid.UUID, content_ids: List[uuid.UUID]
    ) -> Dict[str, Any]:
        """
        Declarative tracking selection for one site: listed content is
        tracked, everything else untracked. Returns counts plus the
        publishing-result ids that were newly enabled (for immediate sync).
        """
        prs = (await self.db.execute(
            select(ContentPublishingResult).where(
                ContentPublishingResult.site_id == site_id,
                ContentPublishingResult.status == PublishingStatus.PUBLISHED,
            )
        )).scalars().all()

        wanted = set(content_ids)
        now = datetime.now(timezone.utc)
        tracked = 0
        untracked = 0
        newly_enabled: List[uuid.UUID] = []

        for pr in prs:
            should_track = pr.content_id in wanted
            if should_track:
                if not pr.tracking_enabled:
                    pr.tracking_enabled = True
                    pr.tracking_enabled_at = now
                    newly_enabled.append(pr.id)
                tracked += 1
            else:
                if pr.tracking_enabled:
                    pr.tracking_enabled = False
                untracked += 1

        await self.db.flush()
        return {
            "tracked_count": tracked,
            "untracked_count": untracked,
            "newly_enabled_ids": newly_enabled,
        }

    # ------------------------------------------------------------------
    # Scheduler support
    # ------------------------------------------------------------------

    async def list_site_sync_targets(
        self, workspace_id: Optional[uuid.UUID] = None
    ) -> List[SiteSyncTarget]:
        """
        Active (mapping, integration) pairs eligible for a *site-level*
        metrics sync (SiteDailyMetric). Unlike list_sync_targets this is
        independent of publishing results — a configured site with zero
        published articles still has site-wide GSC/GA4 data worth showing.
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

        integrations = (await self.db.execute(
            select(GoogleIntegration).where(
                GoogleIntegration.workspace_id.in_(list({m.workspace_id for m in mappings})),
                GoogleIntegration.is_active.is_(True),
                GoogleIntegration.deleted_at.is_(None),
            )
        )).scalars().all()
        integration_by_workspace = {i.workspace_id: i for i in integrations}

        return [
            (m, integration_by_workspace[m.workspace_id])
            for m in mappings
            if m.workspace_id in integration_by_workspace
        ]

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
                ContentPublishingResult.tracking_enabled.is_(True),
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
                ContentPublishingResult.tracking_enabled.is_(True),
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
                # Site has no GSC/GA4 configuration yet — the article is
                # auto-enrolled later when the user configures the site.
                return

            if not pr.tracking_enabled:
                # Site is configured → new publishes are tracked automatically
                # (PUT /tracked-content remains as a per-article opt-out).
                pr.tracking_enabled = True
                pr.tracking_enabled_at = datetime.now(timezone.utc)
                await db.flush()

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
                await SearchConsoleService(db).sync_query_metrics(
                    pr, mapping, access_token, lookback_days
                )
            except Exception:
                logger.warning(
                    f"Post-publish Search Console query sync failed for publishing_result={publishing_result_id}",
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


# ==============================================================================
# Post-site-selection trigger (fire-and-forget, own DB session)
# ==============================================================================

def schedule_site_metrics_sync(workspace_id: uuid.UUID) -> None:
    """
    Kick off an immediate, best-effort *site-level* GSC/GA4 sync right after
    the user saves their site selection, so the dashboard shows site-wide
    data right away instead of waiting for the next scheduled sync cycle.
    Same decoupling contract as schedule_post_publish_sync: own DB session,
    safe to call pre-commit, never raises.
    """
    try:
        task = asyncio.create_task(_run_site_metrics_sync(workspace_id))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
    except RuntimeError:
        logger.debug("No running event loop; skipping post-selection site metrics sync.")
    except Exception:
        logger.exception("Failed to schedule site metrics sync (non-fatal).")


async def _run_site_metrics_sync(workspace_id: uuid.UUID) -> None:
    from src.api.database.async_database import get_async_db_context

    try:
        # The caller fires this right after flush(); poll with fresh sessions
        # until the newly saved mappings are committed and visible.
        targets = []
        for attempt in range(_POST_PUBLISH_MAX_ATTEMPTS):
            async with get_async_db_context() as db:
                targets = await GoogleIntegrationService(db).list_site_sync_targets(workspace_id)
            if targets:
                break
            if attempt < _POST_PUBLISH_MAX_ATTEMPTS - 1:
                await asyncio.sleep(_POST_PUBLISH_RETRY_DELAY_SECONDS)

        if not targets:
            logger.info(
                f"Site metrics sync: no active site mappings visible for workspace={workspace_id}."
            )
            return

        async with get_async_db_context() as db:
            oauth_service = GoogleOAuthService(db)
            integration = await oauth_service.get_active_integration(workspace_id)
            if not integration:
                return
            access_token = await oauth_service.get_valid_access_token(integration)

            mappings = (await db.execute(
                select(GoogleSiteMapping).where(
                    GoogleSiteMapping.workspace_id == workspace_id,
                    GoogleSiteMapping.is_active.is_(True),
                    GoogleSiteMapping.deleted_at.is_(None),
                )
            )).scalars().all()

            for mapping in mappings:
                try:
                    await SearchConsoleService(db).sync_site_metrics(
                        mapping,
                        access_token,
                        google_config.GOOGLE_SYNC_LOOKBACK_DAYS,
                        first_sync_backfill_days=google_config.GOOGLE_SYNC_SITE_BACKFILL_DAYS,
                    )
                except Exception:
                    logger.warning(
                        f"Post-selection site GSC sync failed for mapping={mapping.id}",
                        exc_info=True,
                    )
                try:
                    await GoogleAnalyticsService(db).sync_site_metrics(
                        mapping,
                        access_token,
                        google_config.GOOGLE_SYNC_LOOKBACK_DAYS,
                        first_sync_backfill_days=google_config.GOOGLE_SYNC_SITE_BACKFILL_DAYS,
                    )
                except Exception:
                    logger.warning(
                        f"Post-selection site GA4 sync failed for mapping={mapping.id}",
                        exc_info=True,
                    )
    except Exception:
        logger.exception(f"Site metrics sync failed entirely for workspace={workspace_id}")
