"""
Google Search Console URL Inspection background task.

Periodically inspects the index status of published URLs (→ the "Indexed
Pages" dashboard KPI). Distinct from google_performance_sync_task.py: this
calls a quota-limited, one-URL-per-call API, so it processes URLs
oldest-inspected-first per Search Console property and stops early for a
property once its quota is exhausted for this run (picked up on the next
run/day instead).

Environment variables (see src/config/google_config.py):
- GOOGLE_INDEX_INSPECTION_ENABLED: Toggle this task (default: true)
- GOOGLE_INDEX_INSPECTION_INTERVAL_HOURS: How often it runs (default: 24)
- GOOGLE_INDEX_INSPECTION_DAILY_QUOTA_PER_SITE: Per-property daily call budget (default: 200)
- GOOGLE_INDEX_INSPECTION_PER_MINUTE_LIMIT: Per-property per-minute call budget (default: 300)
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, List
import uuid

from sqlalchemy import select

from src.api.database.async_database import get_async_db_context
from src.api.models.content_models.content_index_status import ContentIndexStatus
from src.services.google_integration_service import GoogleIntegrationService, SyncTarget
from src.services.google_oauth_service import GoogleOAuthService
from src.services.search_console_inspection_service import SearchConsoleInspectionService
from src.utils.google_quota_limiter import get_google_quota_limiter
from src.utils.logger import logger

_CALL_DELAY_SECONDS = 0.2  # small extra safety margin beyond the quota limiter


class GoogleIndexInspectionTask:
    """Background task that refreshes Search Console index status for published URLs."""

    def __init__(self, db):
        self.db = db

    async def run(self) -> dict:
        integration_service = GoogleIntegrationService(self.db)
        oauth_service = GoogleOAuthService(self.db)
        quota_limiter = get_google_quota_limiter()

        targets = await integration_service.list_sync_targets()
        if not targets:
            logger.info("[GoogleIndexInspection] Nothing to inspect.")
            return {"inspected": 0, "skipped": 0, "failed": 0}

        # Refresh each unique integration's access token once up front.
        access_tokens: Dict[uuid.UUID, str] = {}
        for mapping, integration, _pr in targets:
            if integration.id in access_tokens:
                continue
            try:
                access_tokens[integration.id] = await oauth_service.get_valid_access_token(integration)
            except Exception as e:
                logger.error(f"[GoogleIndexInspection] Token refresh failed for integration {integration.id}: {e}")
                access_tokens[integration.id] = None

        # Only URLs with a GSC site mapped make sense to inspect.
        eligible = [t for t in targets if t[0].gsc_site_url and access_tokens.get(t[1].id)]
        if not eligible:
            logger.info("[GoogleIndexInspection] Nothing eligible to inspect.")
            return {"inspected": 0, "skipped": 0, "failed": 0}

        # Last-inspected lookup, batched (no N+1).
        pr_ids = [t[2].id for t in eligible]
        existing_status = (await self.db.execute(
            select(ContentIndexStatus).where(ContentIndexStatus.publishing_result_id.in_(pr_ids))
        )).scalars().all()
        last_inspected: Dict[uuid.UUID, datetime] = {
            s.publishing_result_id: s.inspected_at for s in existing_status if s.inspected_at
        }

        # Group by Search Console property (the quota key), oldest-inspected-first within each.
        by_site: Dict[str, List[SyncTarget]] = {}
        for target in eligible:
            by_site.setdefault(target[0].gsc_site_url, []).append(target)

        for site_key, site_targets in by_site.items():
            site_targets.sort(key=lambda t: last_inspected.get(t[2].id, datetime.min.replace(tzinfo=timezone.utc)))

        inspected = failed = skipped = 0

        for site_key, site_targets in by_site.items():
            for idx, (mapping, integration, pr) in enumerate(site_targets):
                allowed = await quota_limiter.try_reserve(site_key)
                if not allowed:
                    remaining = len(site_targets) - idx
                    logger.info(
                        f"[GoogleIndexInspection] Quota exhausted for site={site_key} — "
                        f"deferring remaining {remaining} URL(s) to next run."
                    )
                    skipped += remaining
                    break

                access_token = access_tokens[integration.id]
                try:
                    await SearchConsoleInspectionService(self.db).inspect_and_upsert(
                        pr, mapping, access_token
                    )
                    inspected += 1
                except Exception as e:
                    logger.warning(f"[GoogleIndexInspection] Failed to inspect {pr.id}: {e}")
                    failed += 1

                await asyncio.sleep(_CALL_DELAY_SECONDS)

        logger.info(
            f"[GoogleIndexInspection] Cycle complete. inspected={inspected} failed={failed} skipped={skipped}"
        )
        return {"inspected": inspected, "failed": failed, "skipped": skipped}


async def run_google_index_inspection_task() -> None:
    """Entry point for the APScheduler job."""
    async with get_async_db_context() as db:
        task = GoogleIndexInspectionTask(db)
        await task.run()


if __name__ == "__main__":
    asyncio.run(run_google_index_inspection_task())
