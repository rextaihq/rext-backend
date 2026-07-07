"""
Content Health Score Service - Module 3

A composite 0-100 quality score per article, built entirely from data
already available in this codebase (Module 1/2's synced GSC/GA4 metrics,
on-page SEO fields, index status) — no new external API calls, no new
credentials, no new database columns.

Six components, weighted:
    Technical SEO       20%  (ContentIndexStatus — also a hard gate: a
                              confirmed non-indexed page caps the overall
                              score, since a great page nobody can find in
                              search delivers no real value)
    SEO Optimization    25%  (ContentSEOData.seo_score, or a lightweight
                              on-page fallback if that hasn't been computed)
    Content Quality     20%  (ContentSEOData.readability_score + trust_score)
    Topical Coverage    15%  (structural proxy: word count, heading depth,
                              secondary-keyword coverage — NOT enriched with
                              DataForSEO intent-matching; that would require
                              persisting currently-transient generation-flow
                              data, which was explicitly deferred)
    Freshness           10%  (decay curve from Content.updated_at)
    User Engagement     10%  (GA4 engagement_rate/bounce_rate/avg session
                              duration, already synced via
                              ContentPerformanceMetric source="analytics")

Any component with no data available yet is excluded and the remaining
weights are renormalized to 100% — a missing GA4 connection or a
not-yet-inspected URL never zeroes out or blocks the score.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.content_models.content import Content
from src.api.models.content_models.content_index_status import ContentIndexStatus
from src.api.models.content_models.content_performance_metric import (
    ContentPerformanceMetric,
    PerformanceMetricSource,
)
from src.api.models.content_models.content_seo_data import ContentSEOData

# --- Weights (sum to 100) ---
_WEIGHTS: Dict[str, float] = {
    "technical_seo": 20.0,
    "seo_optimization": 25.0,
    "content_quality": 20.0,
    "topical_coverage": 15.0,
    "freshness": 10.0,
    "user_engagement": 10.0,
}
_TECHNICAL_SEO_FAIL_CAP = 40.0  # hard cap on overall score if confirmed not indexed

# Minimum share of total weight that must have real data before reporting an
# overall score at all. Without this, near-empty content (e.g. a brand-new
# draft with no SEO analysis yet, no index check, no GA4 data) would have its
# score computed from whatever tiny sliver of components happen to have data
# — e.g. freshness alone (10% weight) is trivially ~100 for anything just
# created, which renormalization would then present as a fake "100/100".
_MIN_AVAILABLE_WEIGHT = 40.0

# --- Technical SEO verdict → base score ---
_VERDICT_SCORES = {"PASS": 100.0, "NEUTRAL": 60.0, "FAIL": 20.0}
_VERDICT_UNKNOWN_SCORE = 50.0

# --- SEO Optimization fallback thresholds ---
_META_TITLE_LEN_RANGE = (40, 65)
_META_DESCRIPTION_LEN_RANGE = (120, 165)
_KEYPHRASE_DENSITY_RANGE = (0.5, 2.5)

# --- Content Quality fallback ---
_QUALITY_FALLBACK_WORD_TARGET = 600

# --- Topical Coverage ---
_TOPICAL_TARGET_WORD_COUNT = 1200
_TOPICAL_TARGET_HEADINGS = 4

# --- Freshness decay curve ---
_FRESHNESS_FULL_DAYS = 90
_FRESHNESS_FLOOR_DAYS = 730
_FRESHNESS_FLOOR_SCORE = 20.0

# --- User Engagement ---
_ENGAGEMENT_ANALYTICS_WINDOW_DAYS = 28
_ENGAGEMENT_DURATION_BENCHMARK_SECONDS = 120.0


@dataclass
class ContentHealthScoreResult:
    content_id: uuid.UUID
    overall: Optional[float]
    components: Dict[str, Optional[float]] = field(default_factory=dict)
    capped_due_to_indexing: bool = False


class ContentHealthScoreService:
    """Computes the Module 3 composite health score for one or many articles."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Single-item entrypoint (dedicated health-score route)
    # ------------------------------------------------------------------

    async def score_content(self, content_id: uuid.UUID) -> Optional[ContentHealthScoreResult]:
        content = await self.db.get(Content, content_id)
        if not content:
            return None

        seo = (await self.db.execute(
            select(ContentSEOData).where(ContentSEOData.content_id == content_id)
        )).scalar_one_or_none()

        index_status = await self._latest_index_status(content.workspace_id, [content_id])
        analytics_by_content = await self.fetch_analytics_by_content(
            content.workspace_id, [content_id]
        )

        return self.score_from_prefetched(
            content, seo,
            index_status.get(content_id),
            analytics_by_content.get(content_id, []),
        )

    # ------------------------------------------------------------------
    # Batched entrypoint (workspace-wide — dashboard average)
    # ------------------------------------------------------------------

    async def score_workspace_content(
        self, workspace_id: uuid.UUID
    ) -> Dict[uuid.UUID, ContentHealthScoreResult]:
        content_rows = (await self.db.execute(
            select(Content).where(
                Content.workspace_id == workspace_id,
                Content.deleted_at.is_(None),
            )
        )).scalars().all()
        if not content_rows:
            return {}

        content_ids = [c.id for c in content_rows]

        seo_rows = (await self.db.execute(
            select(ContentSEOData).where(ContentSEOData.content_id.in_(content_ids))
        )).scalars().all()
        seo_by_content = {s.content_id: s for s in seo_rows}

        index_by_content = await self._latest_index_status(workspace_id, content_ids)
        analytics_by_content = await self.fetch_analytics_by_content(workspace_id, content_ids)

        results: Dict[uuid.UUID, ContentHealthScoreResult] = {}
        for content in content_rows:
            results[content.id] = self.score_from_prefetched(
                content,
                seo_by_content.get(content.id),
                index_by_content.get(content.id),
                analytics_by_content.get(content.id, []),
            )
        return results

    # ------------------------------------------------------------------
    # Shared batched data-fetch helper (also used by ContentInventoryService,
    # which already has Content/ContentSEOData/ContentIndexStatus in memory
    # for its own purposes and only needs this piece to avoid N+1 queries)
    # ------------------------------------------------------------------

    async def fetch_analytics_by_content(
        self,
        workspace_id: uuid.UUID,
        content_ids: Sequence[uuid.UUID],
        days: int = _ENGAGEMENT_ANALYTICS_WINDOW_DAYS,
    ) -> Dict[uuid.UUID, List[ContentPerformanceMetric]]:
        if not content_ids:
            return {}
        since = datetime.now(timezone.utc).date() - timedelta(days=days)
        rows = (await self.db.execute(
            select(ContentPerformanceMetric).where(
                ContentPerformanceMetric.workspace_id == workspace_id,
                ContentPerformanceMetric.content_id.in_(content_ids),
                ContentPerformanceMetric.source == PerformanceMetricSource.ANALYTICS.value,
                ContentPerformanceMetric.metric_date >= since,
            )
        )).scalars().all()

        by_content: Dict[uuid.UUID, List[ContentPerformanceMetric]] = {}
        for row in rows:
            by_content.setdefault(row.content_id, []).append(row)
        return by_content

    async def _latest_index_status(
        self, workspace_id: uuid.UUID, content_ids: Sequence[uuid.UUID]
    ) -> Dict[uuid.UUID, ContentIndexStatus]:
        if not content_ids:
            return {}
        rows = (await self.db.execute(
            select(ContentIndexStatus).where(
                ContentIndexStatus.workspace_id == workspace_id,
                ContentIndexStatus.content_id.in_(content_ids),
            )
        )).scalars().all()

        latest: Dict[uuid.UUID, ContentIndexStatus] = {}
        for row in rows:
            existing = latest.get(row.content_id)
            row_time = row.inspected_at or row.updated_at
            existing_time = (existing.inspected_at or existing.updated_at) if existing else None
            if not existing or existing_time is None or (row_time and row_time > existing_time):
                latest[row.content_id] = row
        return latest

    # ------------------------------------------------------------------
    # Pure computation (no I/O) — reusable by any caller with prefetched rows
    # ------------------------------------------------------------------

    def score_from_prefetched(
        self,
        content: Content,
        seo: Optional[ContentSEOData],
        index_status: Optional[ContentIndexStatus],
        analytics_rows: Sequence[ContentPerformanceMetric],
    ) -> ContentHealthScoreResult:
        technical_score, is_indexing_failure = self._score_technical_seo(index_status)

        components: Dict[str, Optional[float]] = {
            "technical_seo": technical_score,
            "seo_optimization": self._score_seo_optimization(content, seo),
            "content_quality": self._score_content_quality(seo, content.body_markdown),
            "topical_coverage": self._score_topical_coverage(content, seo),
            "freshness": self._score_freshness(content.updated_at),
            "user_engagement": self._score_user_engagement(analytics_rows),
        }

        available = {k: v for k, v in components.items() if v is not None}
        weight_total = sum(_WEIGHTS[k] for k in available)
        if not available or weight_total < _MIN_AVAILABLE_WEIGHT:
            overall = None
        else:
            overall = round(sum(_WEIGHTS[k] * v for k, v in available.items()) / weight_total, 1)
            if is_indexing_failure:
                overall = min(overall, _TECHNICAL_SEO_FAIL_CAP)

        return ContentHealthScoreResult(
            content_id=content.id,
            overall=overall,
            components=components,
            capped_due_to_indexing=is_indexing_failure,
        )

    # ------------------------------------------------------------------
    # Component scorers
    # ------------------------------------------------------------------

    @staticmethod
    def _score_technical_seo(
        index_status: Optional[ContentIndexStatus],
    ) -> "tuple[Optional[float], bool]":
        """Returns (score, is_confirmed_not_indexed). No inspection yet = no data (excluded)."""
        if index_status is None or not index_status.verdict:
            return None, False
        verdict = index_status.verdict
        score = _VERDICT_SCORES.get(verdict, _VERDICT_UNKNOWN_SCORE)
        return score, verdict == "FAIL"

    @staticmethod
    def _score_seo_optimization(content: Content, seo: Optional[ContentSEOData]) -> Optional[float]:
        if seo and seo.seo_score is not None:
            return float(seo.seo_score)
        if not seo:
            return None

        # Lightweight on-page fallback if seo_score was never computed for this article.
        checks: List[float] = []
        checks.append(1.0 if seo.focus_keyphrase else 0.0)

        title_len = len(seo.meta_title) if seo.meta_title else 0
        lo, hi = _META_TITLE_LEN_RANGE
        checks.append(1.0 if title_len and lo <= title_len <= hi else (0.4 if title_len else 0.0))

        desc_len = len(seo.meta_description) if seo.meta_description else 0
        lo, hi = _META_DESCRIPTION_LEN_RANGE
        checks.append(1.0 if desc_len and lo <= desc_len <= hi else (0.4 if desc_len else 0.0))

        if seo.keyphrase_density is not None:
            lo, hi = _KEYPHRASE_DENSITY_RANGE
            checks.append(1.0 if lo <= seo.keyphrase_density <= hi else 0.3)

        checks.append(1.0 if content.links_data else 0.0)

        return round(sum(checks) / len(checks) * 100, 1)

    @staticmethod
    def _score_content_quality(seo: Optional[ContentSEOData], body_markdown: Optional[str]) -> Optional[float]:
        scores = []
        if seo and seo.readability_score is not None:
            scores.append(float(seo.readability_score))
        if seo and seo.trust_score is not None:
            scores.append(float(seo.trust_score))
        if scores:
            return round(sum(scores) / len(scores), 1)

        # Fallback: word-count adequacy only (a low bar for "substantial content").
        word_count = len((body_markdown or "").split())
        if word_count == 0:
            return None
        return round(min(100.0, word_count / _QUALITY_FALLBACK_WORD_TARGET * 100), 1)

    @staticmethod
    def _score_topical_coverage(content: Content, seo: Optional[ContentSEOData]) -> Optional[float]:
        body_text, word_count, heading_count = ContentHealthScoreService._extract_body_stats(content)
        if word_count == 0:
            return None

        word_count_score = min(100.0, word_count / _TOPICAL_TARGET_WORD_COUNT * 100)
        heading_score = min(100.0, heading_count / _TOPICAL_TARGET_HEADINGS * 100)

        components = [word_count_score, heading_score]

        secondary_keywords = (seo.secondary_keywords if seo else None) or []
        secondary_keywords = [kw for kw in secondary_keywords if kw]
        if secondary_keywords:
            body_lower = body_text.lower()
            covered = sum(1 for kw in secondary_keywords if kw.lower() in body_lower)
            components.append(covered / len(secondary_keywords) * 100)

        return round(sum(components) / len(components), 1)

    @staticmethod
    def _extract_body_stats(content: Content) -> "tuple[str, int, int]":
        """Returns (plain_text, word_count, heading_count), preferring markdown."""
        if content.body_markdown:
            body = content.body_markdown
            word_count = len(re.findall(r"\S+", body))
            heading_count = len(re.findall(r"^#{2,3}\s", body, re.MULTILINE))
            return body, word_count, heading_count

        if content.body_html:
            heading_count = len(re.findall(r"<h[23][ >]", content.body_html, re.IGNORECASE))
            text = re.sub(r"<[^>]+>", " ", content.body_html)
            word_count = len(re.findall(r"\S+", text))
            return text, word_count, heading_count

        return "", 0, 0

    @staticmethod
    def _score_freshness(last_updated: Optional[datetime]) -> Optional[float]:
        if not last_updated:
            return None
        days = (datetime.now(timezone.utc) - last_updated).days
        if days <= _FRESHNESS_FULL_DAYS:
            return 100.0
        if days >= _FRESHNESS_FLOOR_DAYS:
            return _FRESHNESS_FLOOR_SCORE
        span = _FRESHNESS_FLOOR_DAYS - _FRESHNESS_FULL_DAYS
        progress = (days - _FRESHNESS_FULL_DAYS) / span
        return round(100.0 - progress * (100.0 - _FRESHNESS_FLOOR_SCORE), 1)

    @staticmethod
    def _score_user_engagement(analytics_rows: Sequence[ContentPerformanceMetric]) -> Optional[float]:
        if not analytics_rows:
            return None

        total_sessions = sum(float((r.metrics or {}).get("sessions") or 0) for r in analytics_rows)
        if total_sessions <= 0:
            return None

        def _weighted(key: str) -> float:
            return sum(
                float((r.metrics or {}).get(key) or 0) * float((r.metrics or {}).get("sessions") or 0)
                for r in analytics_rows
            ) / total_sessions

        engagement_rate = _weighted("engagement_rate")   # 0-1
        bounce_rate = _weighted("bounce_rate")            # 0-1
        avg_duration = _weighted("average_session_duration")  # seconds

        engagement_score = min(100.0, max(0.0, engagement_rate * 100))
        bounce_score = min(100.0, max(0.0, (1 - bounce_rate) * 100))
        duration_score = min(100.0, avg_duration / _ENGAGEMENT_DURATION_BENCHMARK_SECONDS * 100)

        return round((engagement_score + bounce_score + duration_score) / 3, 1)
