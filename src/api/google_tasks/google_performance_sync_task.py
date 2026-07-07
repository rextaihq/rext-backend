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
"""

import asyncio

from src.api.database.async_database import get_async_db_context
from src.config.google_config import google_config
from src.services.google_analytics_service import GoogleAnalyticsService
from src.services.google_integration_service import GoogleIntegrationService
from src.services.google_oauth_service import GoogleOAuthService
from src.services.search_console_service import SearchConsoleService
from src.utils.logger import logger

_SYNC_CONCURRENCY = 5


class GooglePerformanceSyncTask:
    """Background task that reconciles GSC/GA4 metrics for all tracked content."""

    def __init__(self, db):
        self.db = db

    async def run(self) -> dict:
        integration_service = GoogleIntegrationService(self.db)
        oauth_service = GoogleOAuthService(self.db)

        targets = await integration_service.list_sync_targets()
        if not targets:
            logger.info("[GoogleSync] Nothing to sync.")
            return {"synced": 0, "failed": 0}

        logger.info(f"[GoogleSync] {len(targets)} publishing result(s) to sync.")

        # Refresh each unique integration's access token once, up front —
        # avoids redundant refresh calls when a workspace has many published URLs.
        access_tokens: dict = {}
        for mapping, integration, _pr in targets:
            if integration.id in access_tokens:
                continue
            try:
                access_tokens[integration.id] = await oauth_service.get_valid_access_token(integration)
            except Exception as e:
                logger.error(f"[GoogleSync] Token refresh failed for integration {integration.id}: {e}")
                access_tokens[integration.id] = None

        sem = asyncio.Semaphore(_SYNC_CONCURRENCY)
        synced = 0
        failed = 0

        async def _sync_one(mapping, integration, pr) -> None:
            nonlocal synced, failed
            access_token = access_tokens.get(integration.id)
            if not access_token:
                failed += 1
                return

            async with sem:
                ok = True
                try:
                    await SearchConsoleService(self.db).sync_publishing_result(
                        pr, mapping, access_token, google_config.GOOGLE_SYNC_LOOKBACK_DAYS
                    )
                except Exception as e:
                    logger.warning(f"[GoogleSync] Search Console sync failed for {pr.id}: {e}")
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

        await asyncio.gather(*[_sync_one(m, i, pr) for m, i, pr in targets])

        logger.info(f"[GoogleSync] Cycle complete. synced={synced} failed={failed}")
        return {"synced": synced, "failed": failed}


async def run_google_performance_sync_task() -> None:
    """Entry point for the APScheduler job."""
    async with get_async_db_context() as db:
        task = GooglePerformanceSyncTask(db)
        await task.run()


if __name__ == "__main__":
    asyncio.run(run_google_performance_sync_task())
