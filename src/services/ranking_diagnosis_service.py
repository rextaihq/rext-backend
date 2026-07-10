"""
Ranking Diagnosis Service - Module 5 (AI Diagnosis)

Explains why a specific article's search performance changed. Two layers:

1. Rule-based signal detection (this file, always runs) — deterministic,
   reuses Modules 1-4 data (GSC current-vs-prior-window deltas, Module 3's
   health components, on-page structure). Zero LLM, zero cost, always
   correct — this is the ground truth the optional AI layer narrates.
2. Optional LLM synthesis (generate_ai_summary=True) — narrates ONLY the
   signals layer 1 detected into clear prose, via the same
   init_chat_model + with_structured_output pattern used throughout
   src/flow/. Credit-gated (ANALYSIS_STAGE_CREDITS["ranking_diagnosis"]).
   Falls back to a plain templated sentence built from the same facts if
   the LLM call fails, credits are insufficient, or the output fails a
   grounding check — the diagnosis is never blocked or fabricated.

Explicitly NOT diagnosed: competitor topical coverage, search intent shift.
Both would need data this system doesn't persist (no competitor/SERP
history) — same reasoning as the Authority/Content Gap exclusions in
Modules 3/4. Guessing at these risks a wrong-answer diagnosis, which this
project has consistently avoided.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.config import settings
from src.api.models.content_models.content import Content
from src.api.models.content_models.content_performance_metric import (
    ContentPerformanceMetric,
    PerformanceMetricSource,
)
from src.api.models.content_models.content_query_metric import ContentQueryMetric
from src.services.content_health_score_service import ContentHealthScoreService
from src.utils.credit_manager import (
    ANALYSIS_STAGE_CREDITS,
    InsufficientCreditsError,
    consume_stage_credits,
)
from src.utils.gsc_metrics import sum_metric, weighted_avg_position
from src.utils.logger import logger

# --- Classification thresholds (mirrors ContentScoringService's already-
# established, already-tuned values, for consistency across modules) ---
_POSITION_DECLINE_THRESHOLD = 3.0
_CLICKS_DECLINE_THRESHOLD = -0.20
_IMPRESSIONS_STABLE_BAND = 0.10

# --- Content-signal thresholds ---
_LOW_HEALTH_COMPONENT_THRESHOLD = 40.0
_OUTDATED_STATS_YEAR_THRESHOLD = 2
_FAQ_PATTERN = re.compile(r"\b(faq|frequently asked questions)\b", re.IGNORECASE)
_YEAR_PATTERN = re.compile(r"\b(?:19|20)\d{2}\b")

# Phrases that would indicate the LLM introduced an ungrounded cause —
# a hard fail-safe on top of the "narrate only supplied facts" prompt.
_UNGROUNDED_TERMS = [
    "competitor", "competitors", "search intent", "algorithm update",
    "core update", "google update",
]


@dataclass
class RankingSignal:
    key: str
    label: str
    detail: str


@dataclass
class RankingDiagnosisResult:
    content_id: uuid.UUID
    classification: str  # ranking_drop | ctr_collapse | visibility_drop | improving | stable | no_data
    window_days: int

    position_current: Optional[float]
    position_previous: Optional[float]
    position_delta: Optional[float]
    clicks_current: float
    clicks_previous: float
    clicks_delta_pct: Optional[float]
    impressions_current: float
    impressions_previous: float
    impressions_delta_pct: Optional[float]

    top_query: Optional[str] = None
    top_query_position: Optional[float] = None

    signals: List[RankingSignal] = field(default_factory=list)
    summary: str = ""
    reasons: List[str] = field(default_factory=list)
    ai_generated: bool = False
    ai_unavailable_reason: Optional[str] = None


class RankingDiagnosisService:
    """Computes the Module 5 ranking-change diagnosis for one article."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def diagnose(
        self,
        content_id: uuid.UUID,
        *,
        window_days: int = 28,
        generate_ai_summary: bool = False,
        user_id: Optional[str] = None,
    ) -> Optional[RankingDiagnosisResult]:
        content = await self.db.get(Content, content_id)
        if not content:
            return None

        current_rows, previous_rows = await self._fetch_metric_rows(
            content.workspace_id, content_id, window_days
        )
        top_query = await self._top_query(content_id)
        health = await ContentHealthScoreService(self.db).score_content(content_id)

        result = self._classify_and_detect_signals(
            content, current_rows, previous_rows, top_query, health, window_days
        )

        # Rule-based baseline — always present, computed before any LLM call,
        # and what's returned if the AI layer is skipped/unavailable/fails.
        result.summary, result.reasons = self._template_summary(result)

        if generate_ai_summary:
            await self._try_generate_ai_summary(result, user_id)

        return result

    # ------------------------------------------------------------------
    # Data fetching
    # ------------------------------------------------------------------

    async def _fetch_metric_rows(
        self, workspace_id: uuid.UUID, content_id: uuid.UUID, window_days: int
    ) -> Tuple[List[ContentPerformanceMetric], List[ContentPerformanceMetric]]:
        today = datetime.now(timezone.utc).date()
        current_start = today - timedelta(days=window_days)
        previous_start = current_start - timedelta(days=window_days)

        rows = (await self.db.execute(
            select(ContentPerformanceMetric).where(
                ContentPerformanceMetric.workspace_id == workspace_id,
                ContentPerformanceMetric.content_id == content_id,
                ContentPerformanceMetric.source == PerformanceMetricSource.SEARCH_CONSOLE.value,
                ContentPerformanceMetric.metric_date >= previous_start,
                ContentPerformanceMetric.metric_date < today,
            )
        )).scalars().all()

        current = [r for r in rows if r.metric_date >= current_start]
        previous = [r for r in rows if r.metric_date < current_start]
        return current, previous

    async def _top_query(self, content_id: uuid.UUID) -> Optional[ContentQueryMetric]:
        rows = (await self.db.execute(
            select(ContentQueryMetric).where(ContentQueryMetric.content_id == content_id)
        )).scalars().all()
        if not rows:
            return None
        return max(rows, key=lambda r: r.impressions)

    # ------------------------------------------------------------------
    # Classification + signal detection (pure computation)
    # ------------------------------------------------------------------

    def _classify_and_detect_signals(
        self,
        content: Content,
        current_rows: Sequence[ContentPerformanceMetric],
        previous_rows: Sequence[ContentPerformanceMetric],
        top_query: Optional[ContentQueryMetric],
        health,
        window_days: int,
    ) -> RankingDiagnosisResult:
        clicks_current = sum_metric(current_rows, "clicks")
        impressions_current = sum_metric(current_rows, "impressions")
        position_current = weighted_avg_position(current_rows)

        clicks_previous = sum_metric(previous_rows, "clicks") if previous_rows else 0.0
        impressions_previous = sum_metric(previous_rows, "impressions") if previous_rows else 0.0
        position_previous = weighted_avg_position(previous_rows) if previous_rows else None

        position_delta = (
            position_current - position_previous
            if position_current is not None and position_previous is not None
            else None
        )
        clicks_delta_pct = (
            (clicks_current - clicks_previous) / clicks_previous if clicks_previous > 0 else None
        )
        impressions_delta_pct = (
            (impressions_current - impressions_previous) / impressions_previous
            if impressions_previous > 0 else None
        )

        classification = self._classify(
            has_data=bool(current_rows and previous_rows),
            position_delta=position_delta,
            clicks_delta_pct=clicks_delta_pct,
            impressions_delta_pct=impressions_delta_pct,
        )

        signals: List[RankingSignal] = []
        if classification in ("ranking_drop", "ctr_collapse", "visibility_drop"):
            signals = self._detect_signals(
                content, classification, position_delta, clicks_delta_pct, health
            )

        return RankingDiagnosisResult(
            content_id=content.id,
            classification=classification,
            window_days=window_days,
            position_current=round(position_current, 1) if position_current is not None else None,
            position_previous=round(position_previous, 1) if position_previous is not None else None,
            position_delta=round(position_delta, 1) if position_delta is not None else None,
            clicks_current=clicks_current,
            clicks_previous=clicks_previous,
            clicks_delta_pct=round(clicks_delta_pct * 100, 1) if clicks_delta_pct is not None else None,
            impressions_current=impressions_current,
            impressions_previous=impressions_previous,
            impressions_delta_pct=(
                round(impressions_delta_pct * 100, 1) if impressions_delta_pct is not None else None
            ),
            top_query=top_query.query if top_query else None,
            top_query_position=round(top_query.position, 1) if top_query else None,
            signals=signals,
        )

    @staticmethod
    def _classify(
        has_data: bool,
        position_delta: Optional[float],
        clicks_delta_pct: Optional[float],
        impressions_delta_pct: Optional[float],
    ) -> str:
        if not has_data:
            return "no_data"

        if position_delta is not None and position_delta >= _POSITION_DECLINE_THRESHOLD:
            return "ranking_drop"

        clicks_dropped = clicks_delta_pct is not None and clicks_delta_pct <= _CLICKS_DECLINE_THRESHOLD
        impressions_stable_or_up = (
            impressions_delta_pct is None or impressions_delta_pct >= -_IMPRESSIONS_STABLE_BAND
        )
        position_not_worse = position_delta is None or position_delta < _POSITION_DECLINE_THRESHOLD

        if clicks_dropped and impressions_stable_or_up and position_not_worse:
            return "ctr_collapse"

        impressions_dropped = (
            impressions_delta_pct is not None and impressions_delta_pct <= _CLICKS_DECLINE_THRESHOLD
        )
        if clicks_dropped and impressions_dropped:
            return "visibility_drop"

        if position_delta is not None and position_delta <= -_POSITION_DECLINE_THRESHOLD:
            return "improving"

        return "stable"

    def _detect_signals(
        self,
        content: Content,
        classification: str,
        position_delta: Optional[float],
        clicks_delta_pct: Optional[float],
        health,
    ) -> List[RankingSignal]:
        signals: List[RankingSignal] = []

        if classification == "ctr_collapse" and clicks_delta_pct is not None:
            signals.append(RankingSignal(
                key="serp_feature_suspected",
                label="Possible SERP feature impact (e.g. AI Overview)",
                detail=(
                    f"Position held roughly steady, but clicks fell "
                    f"{abs(clicks_delta_pct) * 100:.0f}% — a common signature of an AI "
                    f"Overview or other SERP feature displacing this result even though "
                    f"its ranking didn't move."
                ),
            ))

        if health and health.components:
            comp = health.components
            if comp.get("freshness") is not None and comp["freshness"] < _LOW_HEALTH_COMPONENT_THRESHOLD:
                signals.append(RankingSignal(
                    key="content_freshness_declined",
                    label="Content freshness declined",
                    detail=(
                        f"Freshness score {comp['freshness']:.0f}/100 — this article "
                        f"hasn't been substantively updated recently."
                    ),
                ))
            if comp.get("topical_coverage") is not None and comp["topical_coverage"] < _LOW_HEALTH_COMPONENT_THRESHOLD:
                signals.append(RankingSignal(
                    key="weak_topical_coverage",
                    label="Thin topical coverage",
                    detail=(
                        f"Topical coverage score {comp['topical_coverage']:.0f}/100 — the "
                        f"article may be too short or lack subtopic depth for this query."
                    ),
                ))
            if comp.get("technical_seo") is not None and comp["technical_seo"] < _LOW_HEALTH_COMPONENT_THRESHOLD:
                signals.append(RankingSignal(
                    key="technical_seo_issue",
                    label="Technical SEO issue",
                    detail=(
                        f"Technical SEO score {comp['technical_seo']:.0f}/100 — check this "
                        f"page's indexing status."
                    ),
                ))

        if not self._has_faq_section(content):
            signals.append(RankingSignal(
                key="missing_faq_section",
                label="No FAQ section detected",
                detail="The article doesn't appear to have an FAQ section or FAQPage schema markup.",
            ))

        if self._has_weak_internal_linking(content):
            signals.append(RankingSignal(
                key="weak_internal_linking",
                label="Weak internal linking",
                detail="No internal links were recorded for this article — thin internal linking can limit topical authority.",
            ))

        newest_year = self._newest_year_mentioned(content.body_markdown or content.body_html or "")
        if newest_year is not None:
            current_year = datetime.now(timezone.utc).year
            if current_year - newest_year >= _OUTDATED_STATS_YEAR_THRESHOLD:
                signals.append(RankingSignal(
                    key="outdated_statistics",
                    label="Possibly outdated statistics or references",
                    detail=(
                        f"The most recent year mentioned in the article is {newest_year} — "
                        f"data or examples may be stale. (Approximate signal — verify manually.)"
                    ),
                ))

        return signals

    @staticmethod
    def _has_faq_section(content: Content) -> bool:
        if content.body_markdown and _FAQ_PATTERN.search(content.body_markdown):
            return True
        if content.body_html and _FAQ_PATTERN.search(content.body_html):
            return True
        if content.schema_markup and "FAQPage" in str(content.schema_markup):
            return True
        return False

    @staticmethod
    def _has_weak_internal_linking(content: Content) -> bool:
        links_data = content.links_data
        if not links_data:
            return True
        if isinstance(links_data, dict):
            internal = links_data.get("internal")
            if isinstance(internal, list):
                return len(internal) == 0
        return False

    @staticmethod
    def _newest_year_mentioned(text: str) -> Optional[int]:
        if not text:
            return None
        current_year = datetime.now(timezone.utc).year
        years = [int(y) for y in _YEAR_PATTERN.findall(text) if int(y) <= current_year]
        return max(years) if years else None

    # ------------------------------------------------------------------
    # Rule-based summary (always computed, zero LLM)
    # ------------------------------------------------------------------

    @staticmethod
    def _template_summary(result: RankingDiagnosisResult) -> Tuple[str, List[str]]:
        if result.classification == "no_data":
            return "Not enough historical data yet to diagnose a ranking change.", []

        if result.classification == "ranking_drop" and result.position_delta is not None:
            summary = f"Ranking dropped by {abs(result.position_delta):.1f} positions over the last {result.window_days} days."
        elif result.classification == "ctr_collapse":
            summary = "Position held steady, but click-through rate declined significantly."
        elif result.classification == "visibility_drop":
            summary = "Both impressions and clicks declined — visibility for this article appears to have dropped."
        elif result.classification == "improving" and result.position_delta is not None:
            summary = f"Ranking improved by {abs(result.position_delta):.1f} positions over the last {result.window_days} days."
        else:
            summary = "No significant change detected in this article's search performance."

        if result.classification in ("ranking_drop", "ctr_collapse", "visibility_drop"):
            if result.signals:
                reasons = [f"{s.label} — {s.detail}" for s in result.signals]
            else:
                reasons = [
                    "No specific content or technical cause was detected — this may "
                    "reflect normal search result volatility."
                ]
        else:
            reasons = []

        return summary, reasons

    # ------------------------------------------------------------------
    # Optional LLM synthesis layer
    # ------------------------------------------------------------------

    async def _try_generate_ai_summary(
        self, result: RankingDiagnosisResult, user_id: Optional[str]
    ) -> None:
        if result.classification not in ("ranking_drop", "ctr_collapse", "visibility_drop"):
            result.ai_unavailable_reason = "No decline to explain."
            return

        if not settings.OPENAI_API_KEY:
            result.ai_unavailable_reason = "AI synthesis is not configured."
            return

        try:
            await consume_stage_credits(
                user_id, ANALYSIS_STAGE_CREDITS["ranking_diagnosis"], "ranking_diagnosis"
            )
        except InsufficientCreditsError as exc:
            logger.info(f"Insufficient credits for ranking_diagnosis AI summary: {exc}")
            result.ai_unavailable_reason = "Insufficient credits for AI summary."
            return

        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            from src.flow.model.llm_manager import load_ranking_diagnosis_model
            from src.flow.model.structure.ranking_diagnosis import RankingDiagnosisExplanation
            from src.flow.prompts.system.ranking_diagnosis import RANKING_DIAGNOSIS_PROMPT

            model = load_ranking_diagnosis_model().with_structured_output(
                RankingDiagnosisExplanation
            )

            facts: Dict[str, Any] = {
                "classification": result.classification,
                "position_current": result.position_current,
                "position_previous": result.position_previous,
                "position_delta": result.position_delta,
                "clicks_delta_pct": result.clicks_delta_pct,
                "impressions_delta_pct": result.impressions_delta_pct,
                "window_days": result.window_days,
                "signals": [{"label": s.label, "detail": s.detail} for s in result.signals],
            }

            messages = [
                SystemMessage(content=RANKING_DIAGNOSIS_PROMPT),
                HumanMessage(content=f"Pre-verified data (narrate only this):\n{facts}"),
            ]

            response: RankingDiagnosisExplanation = await model.ainvoke(messages)

            combined_text = f"{response.summary} {' '.join(response.reasons)}".lower()
            if any(term in combined_text for term in _UNGROUNDED_TERMS):
                logger.warning(
                    f"Ranking diagnosis AI output for content={result.content_id} referenced an "
                    "ungrounded cause — discarding, keeping rule-based diagnosis."
                )
                result.ai_unavailable_reason = "AI output failed grounding check; showing rule-based diagnosis."
                return

            result.summary = response.summary
            result.reasons = response.reasons or result.reasons
            result.ai_generated = True

        except Exception:
            logger.exception(
                f"Ranking diagnosis AI synthesis failed for content={result.content_id}"
            )
            result.ai_unavailable_reason = "AI synthesis failed; showing rule-based diagnosis."
