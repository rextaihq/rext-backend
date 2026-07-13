"""
Google Search Console / GA4 performance sync background task.

Reconciles ContentPerformanceMetric with Google on a schedule. This is what
keeps data fresh over time and, critically, fills in Search Console data
that isn't available yet at publish time (GSC finalizes data for a URL
2-3 days after the fact). See GoogleIntegrationService.schedule_post_publish_sync
for the immediate best-effort trigger fired right after a WordPress publish.

Environment variables (see src/config/google_config.py):
- GOOGLE_SYNC_ENABLED: Toggle this task (default: true)
- GOOGLE_SYNC_INTERVAL_HOURS: How often it runs (default: 6)
- GOOGLE_SYNC_LOOKBACK_DAYS: How many trailing days to re-sync each run (default: 7)
- GOOGLE_SYNC_SITE_BACKFILL_DAYS: History pulled the first time a site's
  site-level metrics are synced (default: 90)

Each cycle runs two passes:
1. Site-level (SiteDailyMetric): whole-property GSC/GA4 daily totals per
   mapped site — what the dashboard shows.
2. Per-content (ContentPerformanceMetric/ContentQueryMetric): per-URL data —
   what content inventory / health / opportunity / ranking diagnosis use.
"""

import asyncio

from src.api.database.async_database import get_async_db_context
from src.config.google_config import google_config
from src.services.google_analytics_service import GoogleAnalyticsService
from src.services.google_integration_service import GoogleIntegrationService
from src.services.google_oauth_service import GoogleOAuthService
from src.services.search_console_service import SearchConsoleService
from src.utils.logger import logger


class GooglePerformanceSyncTask:
    """Background task that reconciles GSC/GA4 metrics for all tracked content."""

    def __init__(self, db):
        self.db = db

    async def run(self) -> dict:
        integration_service = GoogleIntegrationService(self.db)
        oauth_service = GoogleOAuthService(self.db)

        site_targets = await integration_service.list_site_sync_targets()
        targets = await integration_service.list_sync_targets()
        if not site_targets and not targets:
            logger.info("[GoogleSync] Nothing to sync.")
            return {"synced": 0, "failed": 0, "sites_synced": 0, "sites_failed": 0}

        logger.info(
            f"[GoogleSync] {len(site_targets)} site(s) and {len(targets)} "
            "publishing result(s) to sync."
        )

        # Refresh each unique integration's access token once, up front —
        # avoids redundant refresh calls when a workspace has many published URLs.
        access_tokens: dict = {}
        for integration in [i for _m, i in site_targets] + [i for _m, i, _pr in targets]:
            if integration.id in access_tokens:
                continue
            try:
                access_tokens[integration.id] = await oauth_service.get_valid_access_token(integration)
            except Exception as e:
                logger.error(f"[GoogleSync] Token refresh failed for integration {integration.id}: {e}")
                access_tokens[integration.id] = None

        # Site-level pass (SiteDailyMetric) — whole-property GSC/GA4 totals
        # that power the dashboard. Sequential, same session constraint as
        # the per-content pass below.
        sites_synced = 0
        sites_failed = 0
        for mapping, integration in site_targets:
            access_token = access_tokens.get(integration.id)
            if not access_token:
                sites_failed += 1
                continue

            ok = True
            try:
                await SearchConsoleService(self.db).sync_site_metrics(
                    mapping,
                    access_token,
                    google_config.GOOGLE_SYNC_LOOKBACK_DAYS,
                    first_sync_backfill_days=google_config.GOOGLE_SYNC_SITE_BACKFILL_DAYS,
                )
            except Exception as e:
                logger.warning(f"[GoogleSync] Site GSC sync failed for mapping {mapping.id}: {e}")
                ok = False

            try:
                await GoogleAnalyticsService(self.db).sync_site_metrics(
                    mapping,
                    access_token,
                    google_config.GOOGLE_SYNC_LOOKBACK_DAYS,
                    first_sync_backfill_days=google_config.GOOGLE_SYNC_SITE_BACKFILL_DAYS,
                )
            except Exception as e:
                logger.warning(f"[GoogleSync] Site GA4 sync failed for mapping {mapping.id}: {e}")
                ok = False

            if ok:
                sites_synced += 1
            else:
                sites_failed += 1

        synced = 0
        failed = 0

        # Sequential on purpose: all targets share this one AsyncSession, and
        # SQLAlchemy sessions do not support concurrent flushes ("Session is
        # already flushing" under asyncio.gather).
        for mapping, integration, pr in targets:
            access_token = access_tokens.get(integration.id)
            if not access_token:
                failed += 1
                continue

            ok = True
            try:
                await SearchConsoleService(self.db).sync_publishing_result(
                    pr, mapping, access_token, google_config.GOOGLE_SYNC_LOOKBACK_DAYS
                )
            except Exception as e:
                logger.warning(f"[GoogleSync] Search Console sync failed for {pr.id}: {e}")
                ok = False

            try:
                await SearchConsoleService(self.db).sync_query_metrics(
                    pr, mapping, access_token, google_config.GOOGLE_SYNC_LOOKBACK_DAYS
                )
            except Exception as e:
                logger.warning(f"[GoogleSync] Search Console query sync failed for {pr.id}: {e}")
                ok = False

            try:
                await GoogleAnalyticsService(self.db).sync_publishing_result(
                    pr, mapping, access_token, google_config.GOOGLE_SYNC_LOOKBACK_DAYS
                )
            except Exception as e:
                logger.warning(f"[GoogleSync] GA4 sync failed for {pr.id}: {e}")
                ok = False

            if ok:
                synced += 1
            else:
                failed += 1

        logger.info(
            f"[GoogleSync] Cycle complete. sites_synced={sites_synced} "
            f"sites_failed={sites_failed} synced={synced} failed={failed}"
        )
        return {
            "synced": synced,
            "failed": failed,
            "sites_synced": sites_synced,
            "sites_failed": sites_failed,
        }


async def run_google_performance_sync_task() -> None:
    """Entry point for the APScheduler job."""
    async with get_async_db_context() as db:
        task = GooglePerformanceSyncTask(db)
        await task.run()


if __name__ == "__main__":
    asyncio.run(run_google_performance_sync_task())
