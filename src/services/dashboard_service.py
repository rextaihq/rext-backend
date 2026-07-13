"""
Content Performance Dashboard Service - Module 1 KPIs + trend charts

Aggregates already-synced GSC/GA4 data plus rule-based scoring
(ContentScoringService) into the dashboard's 9 KPIs + 4 trend charts. No
external API calls — pure read/aggregation over data other jobs have synced.

Traffic KPIs and charts come from SiteDailyMetric — Google's own site-wide
(whole property) totals — so the dashboard reflects the entire site, not
just the articles published through Rext. Per-article rows
(ContentPerformanceMetric) keep powering the content-level modules
(inventory, health, opportunity, ranking diagnosis); they are only used
here as a fallback while a site's first site-level sync hasn't run yet.
"""

from datetime import date as date_, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.content_models.content import Content
from src.api.models.content_models.content_index_status import ContentIndexStatus
from src.api.models.content_models.publishing_result import (
    ContentPublishingResult,
    PublishingStatus,
)
from src.api.models.content_models.content_performance_metric import (
    ContentPerformanceMetric,
    PerformanceMetricSource,
)
from src.api.models.integrations.site_daily_metric import SiteDailyMetric
from src.services.content_health_score_service import ContentHealthScoreService
from src.services.content_scoring_service import ContentScoringService
from src.utils.gsc_metrics import sum_metric, weighted_avg_position


class ContentPerformanceDashboardService:
    """Builds the Module 1 dashboard payload (KPIs + charts) for a workspace."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_dashboard(
        self,
        workspace_id: uuid.UUID,
        days: int = 28,
        site_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        """
        Pass ``site_id`` (a WorkspaceIntegration.id) to scope every KPI and
        chart to one site; omitted, the dashboard blends all of the
        workspace's sites. Every filter below pairs site_id with
        workspace_id, so a foreign site_id just yields an empty dashboard.
        """
        today = datetime.now(timezone.utc).date()
        current_start = today - timedelta(days=days)
        previous_start = current_start - timedelta(days=days)

        # The selected site's published articles (all of them — tracking is
        # automatic once a site is configured). Also reused to scope the
        # workspace-level scoring/health aggregations to this site.
        site_content_ids: Optional[set] = None
        if site_id is not None:
            site_content_ids = set((await self.db.execute(
                select(func.distinct(ContentPublishingResult.content_id))
                .join(Content, Content.id == ContentPublishingResult.content_id)
                .where(
                    Content.workspace_id == workspace_id,
                    Content.deleted_at.is_(None),
                    ContentPublishingResult.status == PublishingStatus.PUBLISHED,
                    ContentPublishingResult.site_id == site_id,
                )
            )).scalars().all())
            total_articles = len(site_content_ids)
        else:
            total_articles = await self.db.scalar(
                select(func.count(func.distinct(ContentPublishingResult.content_id)))
                .select_from(ContentPublishingResult)
                .join(Content, Content.id == ContentPublishingResult.content_id)
                .where(
                    Content.workspace_id == workspace_id,
                    Content.deleted_at.is_(None),
                    ContentPublishingResult.status == PublishingStatus.PUBLISHED,
                )
            ) or 0

        indexed_query = (
            select(func.count()).select_from(ContentIndexStatus).where(
                ContentIndexStatus.workspace_id == workspace_id,
                ContentIndexStatus.verdict == "PASS",
            )
        )
        if site_id is not None:
            indexed_query = indexed_query.join(
                ContentPublishingResult,
                ContentPublishingResult.id == ContentIndexStatus.publishing_result_id,
            ).where(ContentPublishingResult.site_id == site_id)
        indexed_pages = await self.db.scalar(indexed_query) or 0

        # Site-wide GSC totals (whole property, straight from Google) — the
        # dashboard reports on the entire site, not just Rext-published
        # articles. Falls back to summing per-article rows only when the
        # site-level sync hasn't populated yet (fresh setups).
        site_rows_query = select(SiteDailyMetric).where(
            SiteDailyMetric.workspace_id == workspace_id,
            SiteDailyMetric.source == PerformanceMetricSource.SEARCH_CONSOLE.value,
            SiteDailyMetric.metric_date >= previous_start,
            SiteDailyMetric.metric_date < today,
        )
        if site_id is not None:
            site_rows_query = site_rows_query.where(SiteDailyMetric.site_id == site_id)
        rows = (await self.db.execute(site_rows_query)).scalars().all()
        traffic_data_source = "site"

        if not rows:
            fallback_query = select(ContentPerformanceMetric).where(
                ContentPerformanceMetric.workspace_id == workspace_id,
                ContentPerformanceMetric.source == PerformanceMetricSource.SEARCH_CONSOLE.value,
                ContentPerformanceMetric.metric_date >= previous_start,
                ContentPerformanceMetric.metric_date < today,
            )
            if site_id is not None:
                fallback_query = fallback_query.join(
                    ContentPublishingResult,
                    ContentPublishingResult.id == ContentPerformanceMetric.publishing_result_id,
                ).where(ContentPublishingResult.site_id == site_id)
            rows = (await self.db.execute(fallback_query)).scalars().all()
            traffic_data_source = "content_sum"

        current_rows = [r for r in rows if r.metric_date >= current_start]
        previous_rows = [r for r in rows if r.metric_date < current_start]

        organic_clicks = sum_metric(current_rows, "clicks")
        organic_impressions = sum_metric(current_rows, "impressions")
        average_position = weighted_avg_position(current_rows)
        ctr = (organic_clicks / organic_impressions) if organic_impressions > 0 else 0.0

        previous_clicks = sum_metric(previous_rows, "clicks")
        organic_traffic_trend: Optional[float] = (
            round((organic_clicks - previous_clicks) / previous_clicks * 100, 1)
            if previous_clicks > 0 else None
        )

        scoring = await ContentScoringService(self.db).compute_workspace_summary(
            workspace_id, window_days=days, content_ids=site_content_ids
        )

        health_results = await ContentHealthScoreService(self.db).score_workspace_content(workspace_id)
        health_scores = [
            r.overall
            for cid, r in health_results.items()
            if r.overall is not None
            and (site_content_ids is None or cid in site_content_ids)
        ]
        average_health_score: Optional[float] = (
            round(sum(health_scores) / len(health_scores), 1) if health_scores else None
        )

        site_ga4 = await self._site_ga4_summary(
            workspace_id, current_start, today, site_id=site_id
        )

        return {
            "traffic_data_source": traffic_data_source,
            "site_ga4": site_ga4,
            "kpis": {
                "total_articles": total_articles,
                "indexed_pages": indexed_pages,
                "organic_clicks": int(organic_clicks),
                "organic_impressions": int(organic_impressions),
                "average_position": round(average_position, 2) if average_position is not None else None,
                "ctr": round(ctr, 4),
                "organic_traffic_trend": organic_traffic_trend,
                "total_opportunity_score": scoring["total_opportunity_score"],
                "articles_requiring_update": scoring["articles_requiring_update"],
                "average_health_score": average_health_score,
            },
            "charts": self._build_charts(current_rows),
        }

    async def _site_ga4_summary(
        self,
        workspace_id: uuid.UUID,
        start: date_,
        end: date_,
        site_id: Optional[uuid.UUID] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Site-wide GA4 totals over the current window, summed across the
        workspace's mapped sites. Counts are summed; rates/durations are
        session-weighted averages. None until the site-level GA4 sync has
        produced data (e.g. no GA4 property mapped).
        """
        ga4_query = select(SiteDailyMetric).where(
            SiteDailyMetric.workspace_id == workspace_id,
            SiteDailyMetric.source == PerformanceMetricSource.ANALYTICS.value,
            SiteDailyMetric.metric_date >= start,
            SiteDailyMetric.metric_date < end,
        )
        if site_id is not None:
            ga4_query = ga4_query.where(SiteDailyMetric.site_id == site_id)
        rows = (await self.db.execute(ga4_query)).scalars().all()
        if not rows:
            return None

        sessions = sum_metric(rows, "sessions")

        def weighted(key: str) -> Optional[float]:
            if sessions <= 0:
                return None
            total = sum(
                float((r.metrics or {}).get(key) or 0) * float((r.metrics or {}).get("sessions") or 0)
                for r in rows
            )
            return round(total / sessions, 4)

        return {
            "sessions": int(sessions),
            "active_users": int(sum_metric(rows, "active_users")),
            "screen_page_views": int(sum_metric(rows, "screen_page_views")),
            "engagement_rate": weighted("engagement_rate"),
            "average_session_duration": weighted("average_session_duration"),
            "bounce_rate": weighted("bounce_rate"),
        }

    def _build_charts(
        self, rows: List[Any]
    ) -> Dict[str, List[Dict[str, Any]]]:
        # Rows are SiteDailyMetric (normal path) or ContentPerformanceMetric
        # (pre-first-site-sync fallback) — both carry .metric_date/.metrics.
        by_date: Dict[date_, List[Any]] = {}
        for row in rows:
            by_date.setdefault(row.metric_date, []).append(row)

        click_trend, impression_trend, position_trend, ctr_trend = [], [], [], []

        for metric_date in sorted(by_date.keys()):
            day_rows = by_date[metric_date]
            clicks = sum_metric(day_rows, "clicks")
            impressions = sum_metric(day_rows, "impressions")
            position = weighted_avg_position(day_rows)
            day_ctr = (clicks / impressions) if impressions > 0 else 0.0
            date_str = metric_date.isoformat()

            click_trend.append({"date": date_str, "value": int(clicks)})
            impression_trend.append({"date": date_str, "value": int(impressions)})
            position_trend.append({"date": date_str, "value": round(position, 2) if position is not None else None})
            ctr_trend.append({"date": date_str, "value": round(day_ctr, 4)})

        return {
            "click_trend": click_trend,
            "impression_trend": impression_trend,
            "position_trend": position_trend,
            "ctr_trend": ctr_trend,
        }
