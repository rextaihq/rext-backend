"""
Content Performance Dashboard Service - Module 1 KPIs + trend charts

Aggregates already-synced GSC/GA4 data (ContentPerformanceMetric,
ContentIndexStatus) plus rule-based scoring (ContentScoringService) into the
dashboard's 9 KPIs + 4 trend charts. No external API calls — pure read/
aggregation over data other jobs have already synced.
"""

from datetime import date as date_, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.content_models.content import Content
from src.api.models.content_models.content_index_status import ContentIndexStatus
from src.api.models.content_models.content_performance_metric import (
    ContentPerformanceMetric,
    PerformanceMetricSource,
)
from src.services.content_scoring_service import ContentScoringService
from src.utils.gsc_metrics import sum_metric, weighted_avg_position


class ContentPerformanceDashboardService:
    """Builds the Module 1 dashboard payload (KPIs + charts) for a workspace."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_dashboard(
        self, workspace_id: uuid.UUID, days: int = 28
    ) -> Dict[str, Any]:
        today = datetime.now(timezone.utc).date()
        current_start = today - timedelta(days=days)
        previous_start = current_start - timedelta(days=days)

        total_articles = await self.db.scalar(
            select(func.count()).select_from(Content).where(
                Content.workspace_id == workspace_id,
                Content.deleted_at.is_(None),
            )
        ) or 0

        indexed_pages = await self.db.scalar(
            select(func.count()).select_from(ContentIndexStatus).where(
                ContentIndexStatus.workspace_id == workspace_id,
                ContentIndexStatus.verdict == "PASS",
            )
        ) or 0

        rows = (await self.db.execute(
            select(ContentPerformanceMetric).where(
                ContentPerformanceMetric.workspace_id == workspace_id,
                ContentPerformanceMetric.source == PerformanceMetricSource.SEARCH_CONSOLE.value,
                ContentPerformanceMetric.metric_date >= previous_start,
                ContentPerformanceMetric.metric_date < today,
            )
        )).scalars().all()

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
            workspace_id, window_days=days
        )

        return {
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
            },
            "charts": self._build_charts(current_rows),
        }

    def _build_charts(
        self, rows: List[ContentPerformanceMetric]
    ) -> Dict[str, List[Dict[str, Any]]]:
        by_date: Dict[date_, List[ContentPerformanceMetric]] = {}
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
