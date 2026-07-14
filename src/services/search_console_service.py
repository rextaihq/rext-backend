"""
Search Console Service - GSC metric syncing business logic

Responsibilities:
- List verified Search Console properties for a connected Google account.
- Sync daily clicks/impressions/ctr/position for a single published URL into
  ContentPerformanceMetric (source="search_console"), upserting by date.
- Sync the per-query breakdown for a published URL into ContentQueryMetric
  (current-state, fully replaced each sync) — powers Module 4 (Opportunity
  Score), which needs to know the *specific* query driving a page's traffic,
  not just the page's blended average across all queries.

Does NOT:
- Manage OAuth tokens (see GoogleOAuthService.get_valid_access_token).
- Discover which (mapping, publishing_result) pairs need syncing (see
  GoogleIntegrationService.list_sync_targets).
"""

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.content_models.content_performance_metric import (
    ContentPerformanceMetric,
    PerformanceMetricSource,
)
from src.api.models.content_models.content_query_metric import ContentQueryMetric
from src.api.models.content_models.publishing_result import ContentPublishingResult
from src.api.models.integrations.google_site_mapping import GoogleSiteMapping
from src.api.models.integrations.site_daily_metric import SiteDailyMetric
from src.web.search_console import SearchConsoleClient


class SearchConsoleService:
    """Service for Search Console data syncing."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_available_sites(self, access_token: str) -> List[Dict[str, Any]]:
        """List verified Search Console properties for the connected account."""
        async with SearchConsoleClient(access_token) as client:
            return await client.list_sites()

    async def sync_publishing_result(
        self,
        publishing_result: ContentPublishingResult,
        mapping: GoogleSiteMapping,
        access_token: str,
        lookback_days: int,
    ) -> int:
        """
        Fetch the last ``lookback_days`` of GSC data for a published URL and
        upsert it into ContentPerformanceMetric. Returns the number of daily
        rows upserted.
        """
        if not mapping.gsc_site_url or not publishing_result.external_url:
            return 0

        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=lookback_days)

        async with SearchConsoleClient(access_token) as client:
            data = await client.query_analytics(
                site_url=mapping.gsc_site_url,
                page_url=publishing_result.external_url,
                start_date=start_date,
                end_date=end_date,
            )

        rows = data.get("rows", [])
        if not rows:
            return 0

        existing_by_date = await self._existing_metrics_by_date(
            publishing_result.id, start_date, end_date
        )

        upserted = 0
        now = datetime.now(timezone.utc)
        for row in rows:
            keys = row.get("keys") or []
            if not keys:
                continue
            metric_date = datetime.strptime(keys[0], "%Y-%m-%d").date()

            metrics = {
                "clicks": row.get("clicks", 0),
                "impressions": row.get("impressions", 0),
                "ctr": row.get("ctr", 0.0),
                "position": row.get("position", 0.0),
            }

            existing = existing_by_date.get(metric_date)
            if existing:
                existing.metrics = metrics
                existing.synced_at = now
            else:
                self.db.add(ContentPerformanceMetric(
                    content_id=publishing_result.content_id,
                    publishing_result_id=publishing_result.id,
                    workspace_id=mapping.workspace_id,
                    source=PerformanceMetricSource.SEARCH_CONSOLE.value,
                    metric_date=metric_date,
                    metrics=metrics,
                    synced_at=now,
                ))
            upserted += 1

        mapping.last_synced_at = now
        await self.db.flush()
        return upserted

    async def sync_site_metrics(
        self,
        mapping: GoogleSiteMapping,
        access_token: str,
        lookback_days: int,
        first_sync_backfill_days: int = 0,
    ) -> int:
        """
        Fetch site-wide (whole property, no page filter) daily GSC totals and
        upsert them into SiteDailyMetric. On the very first sync for a site
        (no rows yet) the window widens to ``first_sync_backfill_days`` so
        the dashboard's period-over-period comparison has history to work
        with. Returns the number of daily rows upserted.
        """
        if not mapping.gsc_site_url:
            return 0

        window = lookback_days
        if first_sync_backfill_days > lookback_days:
            has_rows = (await self.db.execute(
                select(SiteDailyMetric.id).where(
                    SiteDailyMetric.site_id == mapping.site_id,
                    SiteDailyMetric.source == PerformanceMetricSource.SEARCH_CONSOLE.value,
                ).limit(1)
            )).scalar_one_or_none()
            if has_rows is None:
                window = first_sync_backfill_days

        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=window)

        async with SearchConsoleClient(access_token) as client:
            data = await client.query_site_analytics(
                site_url=mapping.gsc_site_url,
                start_date=start_date,
                end_date=end_date,
            )

        rows = data.get("rows", [])
        if not rows:
            return 0

        existing_by_date = await self._existing_site_metrics_by_date(
            mapping.site_id, start_date, end_date
        )

        upserted = 0
        now = datetime.now(timezone.utc)
        for row in rows:
            keys = row.get("keys") or []
            if not keys:
                continue
            metric_date = datetime.strptime(keys[0], "%Y-%m-%d").date()

            metrics = {
                "clicks": row.get("clicks", 0),
                "impressions": row.get("impressions", 0),
                "ctr": row.get("ctr", 0.0),
                "position": row.get("position", 0.0),
            }

            existing = existing_by_date.get(metric_date)
            if existing:
                existing.metrics = metrics
                existing.synced_at = now
            else:
                self.db.add(SiteDailyMetric(
                    workspace_id=mapping.workspace_id,
                    site_id=mapping.site_id,
                    source=PerformanceMetricSource.SEARCH_CONSOLE.value,
                    metric_date=metric_date,
                    metrics=metrics,
                    synced_at=now,
                ))
            upserted += 1

        mapping.last_synced_at = now
        await self.db.flush()
        return upserted

    async def sync_query_metrics(
        self,
        publishing_result: ContentPublishingResult,
        mapping: GoogleSiteMapping,
        access_token: str,
        lookback_days: int,
    ) -> int:
        """
        Fetch the per-query breakdown for a published URL over the last
        ``lookback_days`` and fully replace ContentQueryMetric for this
        publishing_result (queries can appear/disappear between syncs, so a
        stale leftover row would misrepresent what currently drives the
        page). Returns the number of query rows written.
        """
        if not mapping.gsc_site_url or not publishing_result.external_url:
            return 0

        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=lookback_days)

        async with SearchConsoleClient(access_token) as client:
            data = await client.query_analytics_by_query(
                site_url=mapping.gsc_site_url,
                page_url=publishing_result.external_url,
                start_date=start_date,
                end_date=end_date,
            )

        rows = data.get("rows", [])

        await self.db.execute(
            delete(ContentQueryMetric).where(
                ContentQueryMetric.publishing_result_id == publishing_result.id
            )
        )

        if not rows:
            await self.db.flush()
            return 0

        now = datetime.now(timezone.utc)
        for row in rows:
            keys = row.get("keys") or []
            if not keys or not keys[0]:
                continue
            self.db.add(ContentQueryMetric(
                content_id=publishing_result.content_id,
                publishing_result_id=publishing_result.id,
                workspace_id=mapping.workspace_id,
                query=keys[0],
                clicks=int(row.get("clicks", 0)),
                impressions=int(row.get("impressions", 0)),
                ctr=float(row.get("ctr", 0.0)),
                position=float(row.get("position", 0.0)),
                window_days=lookback_days,
                synced_at=now,
            ))

        await self.db.flush()
        return len(rows)

    async def _existing_site_metrics_by_date(
        self, site_id: uuid.UUID, start_date: date, end_date: date
    ) -> Dict[date, SiteDailyMetric]:
        result = await self.db.execute(
            select(SiteDailyMetric).where(
                SiteDailyMetric.site_id == site_id,
                SiteDailyMetric.source == PerformanceMetricSource.SEARCH_CONSOLE.value,
                SiteDailyMetric.metric_date >= start_date,
                SiteDailyMetric.metric_date <= end_date,
            )
        )
        return {row.metric_date: row for row in result.scalars().all()}

    async def _existing_metrics_by_date(
        self, publishing_result_id: uuid.UUID, start_date: date, end_date: date
    ) -> Dict[date, ContentPerformanceMetric]:
        result = await self.db.execute(
            select(ContentPerformanceMetric).where(
                ContentPerformanceMetric.publishing_result_id == publishing_result_id,
                ContentPerformanceMetric.source == PerformanceMetricSource.SEARCH_CONSOLE.value,
                ContentPerformanceMetric.metric_date >= start_date,
                ContentPerformanceMetric.metric_date <= end_date,
            )
        )
        return {row.metric_date: row for row in result.scalars().all()}
