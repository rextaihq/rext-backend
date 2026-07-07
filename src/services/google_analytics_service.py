"""
Google Analytics Service - GA4 metric syncing business logic

Responsibilities:
- Validate a manually-entered GA4 property ID against the connected account.
- Sync daily sessions/users/pageviews/engagement for a single published URL
  into ContentPerformanceMetric (source="analytics"), upserting by date.

Does NOT:
- Manage OAuth tokens (see GoogleOAuthService.get_valid_access_token).
- List GA4 properties (requires the separate Analytics Admin API — out of
  scope; property IDs are entered manually and verified via validate_property).
"""

from datetime import date, datetime, timedelta, timezone
from typing import Dict
from urllib.parse import urlparse
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.content_models.content_performance_metric import (
    ContentPerformanceMetric,
    PerformanceMetricSource,
)
from src.api.models.content_models.publishing_result import ContentPublishingResult
from src.api.models.integrations.google_site_mapping import GoogleSiteMapping
from src.web.google_analytics import GoogleAnalyticsClient


def _metric_value(values: list, index: int, cast=int):
    if index >= len(values) or values[index] is None:
        return cast(0)
    try:
        return cast(values[index])
    except (TypeError, ValueError):
        return cast(0)


class GoogleAnalyticsService:
    """Service for GA4 data syncing."""

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _extract_page_path(external_url: str) -> str:
        parsed = urlparse(external_url)
        return parsed.path or "/"

    async def validate_property(self, access_token: str, property_id: str) -> bool:
        """Confirm the connected account can query this GA4 property."""
        async with GoogleAnalyticsClient(access_token) as client:
            return await client.validate_property(property_id)

    async def sync_publishing_result(
        self,
        publishing_result: ContentPublishingResult,
        mapping: GoogleSiteMapping,
        access_token: str,
        lookback_days: int,
    ) -> int:
        """
        Fetch the last ``lookback_days`` of GA4 data for a published URL and
        upsert it into ContentPerformanceMetric. Returns the number of daily
        rows upserted.
        """
        if not mapping.ga4_property_id or not publishing_result.external_url:
            return 0

        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=lookback_days)
        page_path = self._extract_page_path(publishing_result.external_url)

        async with GoogleAnalyticsClient(access_token) as client:
            data = await client.run_report(
                property_id=mapping.ga4_property_id,
                page_path=page_path,
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
            dims = row.get("dimensionValues") or []
            if not dims or not dims[0].get("value"):
                continue
            metric_date = datetime.strptime(dims[0]["value"], "%Y%m%d").date()

            values = [mv.get("value") for mv in row.get("metricValues", [])]
            metrics = {
                "sessions": _metric_value(values, 0),
                "active_users": _metric_value(values, 1),
                "screen_page_views": _metric_value(values, 2),
                "engagement_rate": _metric_value(values, 3, float),
                "average_session_duration": _metric_value(values, 4, float),
                "bounce_rate": _metric_value(values, 5, float),
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
                    source=PerformanceMetricSource.ANALYTICS.value,
                    metric_date=metric_date,
                    metrics=metrics,
                    synced_at=now,
                ))
            upserted += 1

        mapping.last_synced_at = now
        await self.db.flush()
        return upserted

    async def _existing_metrics_by_date(
        self, publishing_result_id: uuid.UUID, start_date: date, end_date: date
    ) -> Dict[date, ContentPerformanceMetric]:
        result = await self.db.execute(
            select(ContentPerformanceMetric).where(
                ContentPerformanceMetric.publishing_result_id == publishing_result_id,
                ContentPerformanceMetric.source == PerformanceMetricSource.ANALYTICS.value,
                ContentPerformanceMetric.metric_date >= start_date,
                ContentPerformanceMetric.metric_date <= end_date,
            )
        )
        return {row.metric_date: row for row in result.scalars().all()}
