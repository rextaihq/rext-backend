"""
Opportunity Score Service - Module 4

Ranks articles by expected traffic growth potential after optimization.
Uses GSC data already synced by Module 1 (page-level daily metrics,
ContentPerformanceMetric) *and* Module 4's own per-query breakdown
(ContentQueryMetric) — together: page-level impressions set the demand/
volume weight and trend, while the single highest-impression query sharpens
the CTR-gap and position inputs (a page's blended average across many
queries can mask a big, specific opportunity on its single most valuable
query). No third-party/paid API — GSC only, per explicit scope decision.

Four weighted inputs + a technical-health gate (reused from Module 3):
    CTR Gap                35%  (query-level if available, else page-level)
    Position/Strikability  30%  (query-level if available, else page-level)
    Demand Volume          25%  (page-level impressions)
    Impression Trend       10%  (page-level, current vs. prior window)
    Technical SEO          gate (ContentHealthScoreService.score_technical_seo
                                 — a confirmed non-indexed page caps the score,
                                 same reasoning as Module 3)

Explicitly NOT scored: Competitor Performance and Content Gap. Both need live
competitor SERP/content data with no persistence layer built (that's Modules
8/9's job) — faking them here risks a wrong-answer score, which was
explicitly ruled out for this project.

Outputs: score (0-100), estimated_traffic_gain (clicks/month, modeled off a
realistic target position — not a #1 fantasy), estimated_ranking_gain
(positions), priority_level, estimated_time_to_improve (heuristic bucket —
no historical before/after optimization data exists yet to predict this
precisely), and target_query (the specific keyword the estimate is anchored
to, when query-level data is available).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.content_models.content import Content
from src.api.models.content_models.content_index_status import ContentIndexStatus
from src.api.models.content_models.content_performance_metric import (
    ContentPerformanceMetric,
    PerformanceMetricSource,
)
from src.api.models.content_models.content_query_metric import ContentQueryMetric
from src.api.models.content_models.publishing_result import ContentPublishingResult, PublishingStatus
from src.services.content_health_score_service import ContentHealthScoreService
from src.utils.gsc_metrics import expected_ctr, sum_metric, weighted_avg_position

# --- Weights (sum to 100) ---
_CTR_GAP_WEIGHT = 35.0
_POSITION_WEIGHT = 30.0
_CORE_WEIGHT_TOTAL = _CTR_GAP_WEIGHT + _POSITION_WEIGHT  # 65 — "is there a real gap to close"

# Volume and trend are NOT independent additive weights — a flat weighted
# average lets high traffic alone inflate the score even when CTR Gap and
# Position (the two signals that actually measure "is there a problem") are
# both near zero, e.g. a page already #1 with excellent CTR but huge volume.
# Instead they're multiplicative modifiers on the core gap signal: volume
# scales how much a real gap matters (no gap = nothing to scale, however
# high the traffic); trend nudges it slightly for rising/falling interest.
_VOLUME_MULTIPLIER_FLOOR = 0.3   # even zero-traffic content keeps some weight
_VOLUME_MULTIPLIER_RANGE = 0.7   # floor..floor+range = 0.3x .. 1.0x
_TREND_MODIFIER_FLOOR = 0.9      # trend is a minor nudge, not a driver
_TREND_MODIFIER_RANGE = 0.2      # floor..floor+range = 0.9x .. 1.1x

_TECHNICAL_SEO_FAIL_CAP = 40.0   # same cap value/reasoning as Module 3
_IMPRESSION_NORMALIZER = 1000.0  # impressions at which volume score saturates to 100

_DEFAULT_WINDOW_DAYS = 28
_DEFAULT_PAGE_SIZE = 25
_MAX_PAGE_SIZE = 200


@dataclass
class OpportunityScoreResult:
    content_id: uuid.UUID
    score: Optional[float]
    estimated_traffic_gain: Optional[float]      # clicks/month, modeled
    estimated_ranking_gain: Optional[float]       # positions
    priority_level: Optional[str]                 # Critical | High | Medium | Low
    estimated_time_to_improve: Optional[str]       # heuristic bucket label
    target_query: Optional[str]                    # the query the estimate is anchored to
    target_query_impressions: Optional[float]
    current_position: Optional[float]
    target_position: Optional[float]
    current_impressions: Optional[float]
    capped_due_to_indexing: bool = False


class OpportunityScoreService:
    """Computes the Module 4 opportunity score/ranking for one or many articles."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Single-item entrypoint (dedicated detail route)
    # ------------------------------------------------------------------

    async def score_content(
        self, content_id: uuid.UUID, window_days: int = _DEFAULT_WINDOW_DAYS
    ) -> Optional[OpportunityScoreResult]:
        content = await self.db.get(Content, content_id)
        if not content:
            return None

        current_rows, previous_rows = await self._fetch_metric_rows(
            content.workspace_id, [content_id], window_days
        )
        pr_by_content = await self._latest_publishing_result_by_content(
            content.workspace_id, [content_id]
        )
        top_query_by_pr = await self._top_query_by_publishing_result(
            [pr.id for pr in pr_by_content.values()]
        )
        index_by_content = await ContentHealthScoreService(self.db).latest_index_status_by_content(
            content.workspace_id, [content_id]
        )

        pr = pr_by_content.get(content_id)
        top_query = top_query_by_pr.get(pr.id) if pr else None

        return self._compute(
            content_id,
            current_rows.get(content_id, []),
            previous_rows.get(content_id, []),
            top_query,
            index_by_content.get(content_id),
        )

    # ------------------------------------------------------------------
    # Batched entrypoint
    # ------------------------------------------------------------------

    async def score_workspace_content(
        self, workspace_id: uuid.UUID, window_days: int = _DEFAULT_WINDOW_DAYS
    ) -> Dict[uuid.UUID, OpportunityScoreResult]:
        content_rows = (await self.db.execute(
            select(Content).where(
                Content.workspace_id == workspace_id,
                Content.deleted_at.is_(None),
            )
        )).scalars().all()
        if not content_rows:
            return {}

        content_ids = [c.id for c in content_rows]

        current_by_content, previous_by_content = await self._fetch_metric_rows(
            workspace_id, content_ids, window_days
        )
        pr_by_content = await self._latest_publishing_result_by_content(workspace_id, content_ids)
        top_query_by_pr = await self._top_query_by_publishing_result(
            [pr.id for pr in pr_by_content.values()]
        )
        index_by_content = await ContentHealthScoreService(self.db).latest_index_status_by_content(
            workspace_id, content_ids
        )

        results: Dict[uuid.UUID, OpportunityScoreResult] = {}
        for content in content_rows:
            pr = pr_by_content.get(content.id)
            top_query = top_query_by_pr.get(pr.id) if pr else None
            results[content.id] = self._compute(
                content.id,
                current_by_content.get(content.id, []),
                previous_by_content.get(content.id, []),
                top_query,
                index_by_content.get(content.id),
            )
        return results

    # ------------------------------------------------------------------
    # Ranked list (the "Ranks articles" deliverable)
    # ------------------------------------------------------------------

    async def list_ranked_opportunities(
        self,
        workspace_id: uuid.UUID,
        window_days: int = _DEFAULT_WINDOW_DAYS,
        page: int = 1,
        page_size: int = _DEFAULT_PAGE_SIZE,
    ) -> Dict[str, Any]:
        page = max(1, page)
        page_size = max(1, min(page_size, _MAX_PAGE_SIZE))

        content_rows = (await self.db.execute(
            select(Content).where(
                Content.workspace_id == workspace_id,
                Content.deleted_at.is_(None),
                Content.status == "published",
            )
        )).scalars().all()
        if not content_rows:
            return {"items": [], "total_count": 0, "page": page, "page_size": page_size, "total_pages": 0}

        results = await self.score_workspace_content(workspace_id, window_days)

        rows = []
        for content in content_rows:
            result = results.get(content.id)
            if not result:
                continue
            rows.append({
                "content_id": content.id,
                "title": content.title,
                "url": content.wordpress_url,
                "score": result.score,
                "estimated_traffic_gain": result.estimated_traffic_gain,
                "estimated_ranking_gain": result.estimated_ranking_gain,
                "priority_level": result.priority_level,
                "estimated_time_to_improve": result.estimated_time_to_improve,
                "target_query": result.target_query,
                "target_query_impressions": result.target_query_impressions,
                "current_position": result.current_position,
                "target_position": result.target_position,
                "current_impressions": result.current_impressions,
                "capped_due_to_indexing": result.capped_due_to_indexing,
            })

        rows.sort(key=lambda r: (r["score"] is None, -(r["score"] or 0.0)))

        total_count = len(rows)
        start = (page - 1) * page_size
        page_rows = rows[start:start + page_size]
        total_pages = (total_count + page_size - 1) // page_size if page_size else 0

        return {
            "items": page_rows,
            "total_count": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    # ------------------------------------------------------------------
    # Batched data-fetch helpers
    # ------------------------------------------------------------------

    async def _fetch_metric_rows(
        self, workspace_id: uuid.UUID, content_ids: Sequence[uuid.UUID], window_days: int
    ) -> "tuple[Dict[uuid.UUID, List[ContentPerformanceMetric]], Dict[uuid.UUID, List[ContentPerformanceMetric]]]":
        if not content_ids:
            return {}, {}
        today = datetime.now(timezone.utc).date()
        current_start = today - timedelta(days=window_days)
        previous_start = current_start - timedelta(days=window_days)

        rows = (await self.db.execute(
            select(ContentPerformanceMetric).where(
                ContentPerformanceMetric.workspace_id == workspace_id,
                ContentPerformanceMetric.content_id.in_(content_ids),
                ContentPerformanceMetric.source == PerformanceMetricSource.SEARCH_CONSOLE.value,
                ContentPerformanceMetric.metric_date >= previous_start,
                ContentPerformanceMetric.metric_date < today,
            )
        )).scalars().all()

        current: Dict[uuid.UUID, List[ContentPerformanceMetric]] = {}
        previous: Dict[uuid.UUID, List[ContentPerformanceMetric]] = {}
        for row in rows:
            if row.metric_date >= current_start:
                current.setdefault(row.content_id, []).append(row)
            else:
                previous.setdefault(row.content_id, []).append(row)
        return current, previous

    async def _latest_publishing_result_by_content(
        self, workspace_id: uuid.UUID, content_ids: Sequence[uuid.UUID]
    ) -> Dict[uuid.UUID, ContentPublishingResult]:
        if not content_ids:
            return {}
        rows = (await self.db.execute(
            select(ContentPublishingResult).where(
                ContentPublishingResult.content_id.in_(content_ids),
                ContentPublishingResult.status == PublishingStatus.PUBLISHED,
            )
        )).scalars().all()

        latest: Dict[uuid.UUID, ContentPublishingResult] = {}
        for row in rows:
            existing = latest.get(row.content_id)
            row_time = row.last_synced_at or row.created_at
            existing_time = (existing.last_synced_at or existing.created_at) if existing else None
            if not existing or existing_time is None or (row_time and row_time > existing_time):
                latest[row.content_id] = row
        return latest

    async def _top_query_by_publishing_result(
        self, publishing_result_ids: Sequence[uuid.UUID]
    ) -> Dict[uuid.UUID, ContentQueryMetric]:
        """The single highest-impression query per page — the concrete,
        actionable keyword this page's opportunity is anchored to."""
        publishing_result_ids = [pid for pid in publishing_result_ids if pid]
        if not publishing_result_ids:
            return {}
        rows = (await self.db.execute(
            select(ContentQueryMetric).where(
                ContentQueryMetric.publishing_result_id.in_(publishing_result_ids)
            )
        )).scalars().all()

        top: Dict[uuid.UUID, ContentQueryMetric] = {}
        for row in rows:
            existing = top.get(row.publishing_result_id)
            if not existing or row.impressions > existing.impressions:
                top[row.publishing_result_id] = row
        return top

    # ------------------------------------------------------------------
    # Pure computation
    # ------------------------------------------------------------------

    def _compute(
        self,
        content_id: uuid.UUID,
        current_rows: Sequence[ContentPerformanceMetric],
        previous_rows: Sequence[ContentPerformanceMetric],
        top_query: Optional[ContentQueryMetric],
        index_status: Optional[ContentIndexStatus],
    ) -> OpportunityScoreResult:
        impressions_current = sum_metric(current_rows, "impressions")
        impressions_previous = sum_metric(previous_rows, "impressions") if previous_rows else 0.0
        page_position = weighted_avg_position(current_rows)
        page_clicks = sum_metric(current_rows, "clicks")
        page_ctr = (page_clicks / impressions_current) if impressions_current > 0 else 0.0

        # Prefer the top query's own numbers (more precise/actionable) over
        # the page-level blended average; fall back to page-level if no
        # query-level data has synced yet.
        if top_query and top_query.impressions > 0:
            precision_position = top_query.position
            precision_ctr = top_query.ctr
            target_query = top_query.query
            target_query_impressions: Optional[float] = float(top_query.impressions)
            anchor_impressions = float(top_query.impressions)
        elif page_position is not None:
            precision_position = page_position
            precision_ctr = page_ctr
            target_query = None
            target_query_impressions = None
            anchor_impressions = impressions_current
        else:
            return OpportunityScoreResult(
                content_id=content_id, score=None, estimated_traffic_gain=None,
                estimated_ranking_gain=None, priority_level=None,
                estimated_time_to_improve=None, target_query=None,
                target_query_impressions=None, current_position=None,
                target_position=None, current_impressions=impressions_current or None,
            )

        technical_score, is_indexing_failure = ContentHealthScoreService.score_technical_seo(index_status)

        # --- CTR Gap (0-1, higher = more room to improve) ---
        expected = expected_ctr(precision_position)
        ctr_gap_ratio = max(0.0, min(1.0, (expected - precision_ctr) / expected)) if expected > 0 else 0.0
        ctr_gap_score = ctr_gap_ratio * 100.0

        # --- Position / strikability (0-100) ---
        position_score = self._position_strikability_score(precision_position)

        # --- Demand volume (0-100, page-level) ---
        volume_score = min(100.0, impressions_current / _IMPRESSION_NORMALIZER * 100.0)

        # --- Impression trend (0-100, page-level, None if no baseline at all) ---
        trend_score = self._trend_score(impressions_current, impressions_previous)

        # Core gap signal: is there actually a ranking/CTR problem worth
        # solving. Volume and trend then scale how much that gap matters —
        # they cannot manufacture a high score out of a near-zero gap, no
        # matter how much traffic the page already gets.
        core_gap_score = (
            ctr_gap_score * _CTR_GAP_WEIGHT + position_score * _POSITION_WEIGHT
        ) / _CORE_WEIGHT_TOTAL

        volume_multiplier = _VOLUME_MULTIPLIER_FLOOR + _VOLUME_MULTIPLIER_RANGE * (volume_score / 100.0)
        trend_multiplier = (
            _TREND_MODIFIER_FLOOR + _TREND_MODIFIER_RANGE * (trend_score / 100.0)
            if trend_score is not None else 1.0
        )

        score: Optional[float] = round(
            min(100.0, core_gap_score * volume_multiplier * trend_multiplier), 1
        )
        if is_indexing_failure:
            score = min(score, _TECHNICAL_SEO_FAIL_CAP)

        # --- Outputs modeled off a realistic target position ---
        target_position = self._model_target_position(precision_position)
        estimated_ranking_gain = round(max(0.0, precision_position - target_position), 1)
        target_expected_ctr = expected_ctr(target_position)
        estimated_traffic_gain = round(
            max(0.0, (target_expected_ctr - precision_ctr) * anchor_impressions), 1
        )
        priority_level = self._priority_level(score, estimated_traffic_gain)
        estimated_time_to_improve = self._time_to_improve_bucket(estimated_ranking_gain)

        return OpportunityScoreResult(
            content_id=content_id,
            score=score,
            estimated_traffic_gain=estimated_traffic_gain,
            estimated_ranking_gain=estimated_ranking_gain,
            priority_level=priority_level,
            estimated_time_to_improve=estimated_time_to_improve,
            target_query=target_query,
            target_query_impressions=target_query_impressions,
            current_position=round(precision_position, 1),
            target_position=target_position,
            current_impressions=impressions_current or None,
            capped_due_to_indexing=is_indexing_failure,
        )

    # ------------------------------------------------------------------
    # Component/output modeling helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _position_strikability_score(position: float) -> float:
        """How reachable/valuable is improving this ranking further, 0-100.
        Already-top positions have little room left; very low positions are
        a long shot; the 4-10 "strikable" zone is the highest-value target."""
        if position <= 3:
            return 20.0
        if position <= 10:
            return 100.0
        if position <= 20:
            return 80.0
        if position <= 30:
            return 50.0
        if position <= 50:
            return 25.0
        return 10.0

    @staticmethod
    def _trend_score(impressions_current: float, impressions_previous: float) -> Optional[float]:
        """0-100, 50 = flat. None only when there's truly no data to compare."""
        if impressions_previous <= 0:
            return 60.0 if impressions_current > 0 else None
        change = (impressions_current - impressions_previous) / impressions_previous
        return max(0.0, min(100.0, 50.0 + change * 100.0))

    @staticmethod
    def _model_target_position(position: float) -> float:
        """A realistic optimization target, not a #1-ranking fantasy —
        bigger gaps get a proportionally more conservative target."""
        if position <= 3:
            return max(1.0, position - 1)
        if position <= 10:
            return 3.0
        if position <= 20:
            return 6.0
        if position <= 50:
            return 12.0
        return round(position * 0.5, 1)

    @staticmethod
    def _priority_level(score: Optional[float], traffic_gain: Optional[float]) -> Optional[str]:
        """Score (the core-gap-aware signal) is primary; traffic_gain only
        amplifies priority when the score already indicates a real
        opportunity exists — it never overrides a low score on its own.
        Without this floor, curve-rounding noise near the top of the
        expected-CTR curve can model a nonzero "gain" for content that's
        already essentially saturated (e.g. rank #1 with near-ceiling CTR),
        which would otherwise misclassify it as high priority."""
        if score is None:
            return None
        if score < 15:
            return "Low"

        gain = traffic_gain or 0.0
        high_score, med_score = score >= 65, score >= 40
        high_gain, med_gain = gain >= 50, gain >= 10

        if high_score and high_gain:
            return "Critical"
        if high_score or (med_score and high_gain):
            return "High"
        if med_score or med_gain:
            return "Medium"
        return "Low"

    @staticmethod
    def _time_to_improve_bucket(ranking_gain: float) -> str:
        """Heuristic bucket based on gap size — there's no historical
        before/after optimization data yet to predict this precisely, so a
        rough bucket beats a fake-precise number of days."""
        if ranking_gain <= 2:
            return "Quick win (2-4 weeks)"
        if ranking_gain <= 6:
            return "Short-term (1-2 months)"
        if ranking_gain <= 15:
            return "Medium-term (2-3 months)"
        return "Long-term (3-6 months)"
