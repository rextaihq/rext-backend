"""
Content Scoring Service - rule-based opportunity scoring

Pure computation over already-synced ContentPerformanceMetric rows (source=
"search_console"). No new external API calls, no persisted score table —
recomputed on read, since the underlying data only changes on each sync
cycle (every GOOGLE_SYNC_INTERVAL_HOURS, or on-demand refresh).

NOT AI-driven: transparent, tunable constants. This is deliberately a
simple, explainable first cut (per explicit scope decision) — a future
phase may layer AI-generated recommendations on top of these numbers.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.content_models.content_performance_metric import (
    ContentPerformanceMetric,
    PerformanceMetricSource,
)
from src.utils.gsc_metrics import expected_ctr as _expected_ctr
from src.utils.gsc_metrics import sum_metric, weighted_avg_position

_CLICKS_DECLINE_THRESHOLD = -0.20   # flag if clicks dropped 20%+ vs prior window
_POSITION_DECLINE_THRESHOLD = 3.0   # flag if avg position worsened by 3+ vs prior window
_IMPRESSION_NORMALIZER = 1000       # impressions at which impression_weight saturates to 1.0
_STRIKABLE_POSITION_RANGE = (4, 20) # "close to page 1" bonus range
_NEAR_STRIKABLE_POSITION_RANGE = (20, 30)

_LOW_CTR_GAP_RATIO_THRESHOLD = 0.5  # actual CTR at/below 50% of expected-for-position = "low CTR"
_TREND_GROWTH_THRESHOLD = 0.10      # clicks up 10%+ vs prior window = "growing"
_TREND_DECLINE_THRESHOLD = -0.10    # clicks down 10%+ vs prior window = "declining"


@dataclass
class ContentScoreResult:
    content_id: uuid.UUID
    opportunity_score: float
    needs_update: bool
    clicks_current: float
    impressions_current: float
    position_current: Optional[float]
    clicks_previous: float
    position_previous: Optional[float]
    ctr_current: float
    ctr_gap_ratio: Optional[float]  # None if no position/impressions to compare against
    low_ctr: bool
    trend: str  # "growing" | "declining" | "stable" | "new" | "no_data"


class ContentScoringService:
    """Rule-based opportunity/health scoring over synced GSC metrics."""

    def __init__(self, db: AsyncSession):
        self.db = db

    def _score_content(
        self,
        content_id: uuid.UUID,
        current_rows: Sequence[ContentPerformanceMetric],
        previous_rows: Sequence[ContentPerformanceMetric],
    ) -> Optional[ContentScoreResult]:
        if not current_rows:
            return None

        clicks_current = sum_metric(current_rows, "clicks")
        impressions_current = sum_metric(current_rows, "impressions")
        position_current = weighted_avg_position(current_rows)
        ctr_current = (clicks_current / impressions_current) if impressions_current > 0 else 0.0

        clicks_previous = sum_metric(previous_rows, "clicks") if previous_rows else 0.0
        position_previous = weighted_avg_position(previous_rows) if previous_rows else None

        # --- Opportunity score (0-100) + CTR gap (0-1, None if not computable) ---
        opportunity_score = 0.0
        ctr_gap_ratio: Optional[float] = None
        if position_current is not None and impressions_current > 0:
            expected = _expected_ctr(position_current)
            ctr_gap_ratio = max(0.0, min(1.0, (expected - ctr_current) / expected)) if expected > 0 else 0.0

            lo, hi = _STRIKABLE_POSITION_RANGE
            near_lo, near_hi = _NEAR_STRIKABLE_POSITION_RANGE
            if lo <= position_current <= hi:
                position_factor = 1.0
            elif near_lo < position_current <= near_hi:
                position_factor = 0.5
            else:
                position_factor = 0.0

            impression_weight = min(1.0, impressions_current / _IMPRESSION_NORMALIZER)
            opportunity_score = round(
                100 * impression_weight * (0.6 * ctr_gap_ratio + 0.4 * position_factor), 1
            )

        low_ctr = bool(ctr_gap_ratio is not None and ctr_gap_ratio >= _LOW_CTR_GAP_RATIO_THRESHOLD)

        # --- Needs update? (only if we have a prior-window baseline to compare) ---
        needs_update = False
        if previous_rows:
            if clicks_previous > 0:
                clicks_trend = (clicks_current - clicks_previous) / clicks_previous
                if clicks_trend <= _CLICKS_DECLINE_THRESHOLD:
                    needs_update = True
            if position_current is not None and position_previous is not None:
                if (position_current - position_previous) >= _POSITION_DECLINE_THRESHOLD:
                    needs_update = True

        # --- Trend classification (descriptive, distinct from the stricter needs_update flag) ---
        if not previous_rows or clicks_previous <= 0:
            trend = "new" if clicks_current > 0 else "no_data"
        else:
            clicks_change = (clicks_current - clicks_previous) / clicks_previous
            if clicks_change >= _TREND_GROWTH_THRESHOLD:
                trend = "growing"
            elif clicks_change <= _TREND_DECLINE_THRESHOLD:
                trend = "declining"
            else:
                trend = "stable"

        return ContentScoreResult(
            content_id=content_id,
            opportunity_score=opportunity_score,
            needs_update=needs_update,
            clicks_current=clicks_current,
            impressions_current=impressions_current,
            position_current=position_current,
            clicks_previous=clicks_previous,
            position_previous=position_previous,
            ctr_current=ctr_current,
            ctr_gap_ratio=ctr_gap_ratio,
            low_ctr=low_ctr,
            trend=trend,
        )

    async def score_workspace_content(
        self, workspace_id: uuid.UUID, window_days: int = 28
    ) -> Dict[uuid.UUID, ContentScoreResult]:
        """
        Batched per-content scoring for a workspace (one query), comparing
        the current window against the immediately-prior equal-length
        window. Backs both the Module 1 dashboard summary
        (compute_workspace_summary) and the Module 2 content inventory table.
        """
        today = datetime.now(timezone.utc).date()
        current_start = today - timedelta(days=window_days)
        previous_start = current_start - timedelta(days=window_days)

        rows = (await self.db.execute(
            select(ContentPerformanceMetric).where(
                ContentPerformanceMetric.workspace_id == workspace_id,
                ContentPerformanceMetric.source == PerformanceMetricSource.SEARCH_CONSOLE.value,
                ContentPerformanceMetric.metric_date >= previous_start,
                ContentPerformanceMetric.metric_date < today,
            )
        )).scalars().all()

        if not rows:
            return {}

        by_content: Dict[uuid.UUID, Dict[str, list]] = {}
        for row in rows:
            bucket = by_content.setdefault(row.content_id, {"current": [], "previous": []})
            if row.metric_date >= current_start:
                bucket["current"].append(row)
            else:
                bucket["previous"].append(row)

        results: Dict[uuid.UUID, ContentScoreResult] = {}
        for content_id, buckets in by_content.items():
            result = self._score_content(content_id, buckets["current"], buckets["previous"])
            if result is not None:
                results[content_id] = result
        return results

    async def compute_workspace_summary(
        self, workspace_id: uuid.UUID, window_days: int = 28
    ) -> Dict[str, float]:
        """
        Aggregate opportunity score + needs-update count across all of a
        workspace's content, comparing the current window against the
        immediately-prior equal-length window.
        """
        results = list((await self.score_workspace_content(workspace_id, window_days)).values())

        if not results:
            return {"total_opportunity_score": 0.0, "articles_requiring_update": 0}

        weight_total = sum(r.impressions_current for r in results)
        if weight_total > 0:
            total_opportunity_score = round(
                sum(r.opportunity_score * r.impressions_current for r in results) / weight_total, 1
            )
        else:
            total_opportunity_score = round(sum(r.opportunity_score for r in results) / len(results), 1)

        return {
            "total_opportunity_score": total_opportunity_score,
            "articles_requiring_update": sum(1 for r in results if r.needs_update),
        }
