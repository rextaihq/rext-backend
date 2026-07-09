"""
Content Inventory Service - Module 2

Lists every published (or draft) article as an individual asset — one row
per Content item — for a filterable/sortable/paginated table view.

Row grain is Content, not ContentPublishingResult: the PRD frames this as
"every article becomes an individual asset," and in practice a workspace's
content is published to at most one WordPress site today. URL/performance
data is read from the content's cached WordPress fields and its already-
synced ContentPerformanceMetric rows (via ContentScoringService), so this
service makes no external API calls.

health_score reuses ContentHealthScoreService (Module 3); ai_recommendation
is intentionally always null — it belongs to Module 5 (AI Diagnosis), which
doesn't exist yet.

opportunity_score/trend/needs_update/low_ctr reuse ContentScoringService —
the same rule-based logic that powers the Module 1 dashboard — rather than
recomputing it here.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Sequence
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware.exceptions import RextValidationException
from src.api.models.content_models.content import Content
from src.api.models.content_models.content_index_status import ContentIndexStatus
from src.api.models.content_models.content_seo_data import ContentSEOData
from src.services.content_health_score_service import ContentHealthScoreService
from src.services.content_scoring_service import ContentScoringService
from src.utils.tracked_content import tracked_content_ids_subquery

_VALID_FILTERS = {
    "published", "growing", "declining", "needs_update",
    "high_opportunity", "low_ctr", "not_indexed", "cannibalized",
}
_HIGH_OPPORTUNITY_THRESHOLD = 70.0

_DEFAULT_SORT_FIELD = "opportunity_score"
_DEFAULT_PAGE_SIZE = 25
_MAX_PAGE_SIZE = 200


@dataclass
class InventoryRow:
    content_id: uuid.UUID
    url: Optional[str]
    title: str
    primary_keyword: Optional[str]
    status: str
    health_score: Optional[float]
    opportunity_score: Optional[float]
    organic_clicks: Optional[float]
    organic_impressions: Optional[float]
    ctr: Optional[float]
    average_position: Optional[float]
    last_updated: Optional[datetime]
    ai_recommendation: Optional[str]
    trend: Optional[str]
    needs_update: bool
    low_ctr: bool
    is_indexed: Optional[bool]
    is_cannibalized: bool


# Sort key extractors — None-safe so unscored/unsynced rows sort last regardless of direction.
_SORT_KEYS: Dict[str, Callable[[InventoryRow], Any]] = {
    "title": lambda r: (r.title or "").lower(),
    "status": lambda r: r.status or "",
    "opportunity_score": lambda r: (r.opportunity_score is None, r.opportunity_score or 0.0),
    "organic_clicks": lambda r: (r.organic_clicks is None, r.organic_clicks or 0.0),
    "organic_impressions": lambda r: (r.organic_impressions is None, r.organic_impressions or 0.0),
    "ctr": lambda r: (r.ctr is None, r.ctr or 0.0),
    "average_position": lambda r: (r.average_position is None, r.average_position or 0.0),
    "last_updated": lambda r: (r.last_updated is None, r.last_updated),
}


class ContentInventoryService:
    """Builds the Module 2 content inventory table for a workspace."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_inventory(
        self,
        *,
        workspace_id: uuid.UUID,
        window_days: int = 28,
        filters: Optional[Sequence[str]] = None,
        sort_by: Optional[str] = None,
        sort_order: str = "desc",
        page: int = 1,
        page_size: int = _DEFAULT_PAGE_SIZE,
    ) -> Dict[str, Any]:
        normalized_filters = self._validate_filters(filters)
        sort_key = self._validate_sort(sort_by)
        page = max(1, page)
        page_size = max(1, min(page_size, _MAX_PAGE_SIZE))

        # Only the articles the user opted into tracking during onboarding —
        # the Google modules never report on unselected content.
        content_rows = (await self.db.execute(
            select(Content).where(
                Content.workspace_id == workspace_id,
                Content.deleted_at.is_(None),
                Content.id.in_(tracked_content_ids_subquery()),
            )
        )).scalars().all()
        if not content_rows:
            return self._paginated_result([], page, page_size)

        content_by_id = {c.id: c for c in content_rows}

        seo_rows = (await self.db.execute(
            select(ContentSEOData).where(ContentSEOData.content_id.in_(content_by_id.keys()))
        )).scalars().all()
        seo_by_content = {s.content_id: s for s in seo_rows}

        scores = await ContentScoringService(self.db).score_workspace_content(
            workspace_id, window_days=window_days
        )

        index_by_content = await self._latest_index_status_by_content(workspace_id)

        health_service = ContentHealthScoreService(self.db)
        analytics_by_content = await health_service.fetch_analytics_by_content(
            workspace_id, list(content_by_id.keys()), days=window_days
        )

        keyword_counts = self._count_published_keywords(content_rows, seo_by_content)

        rows = [
            self._build_row(
                content, seo_by_content.get(content.id), scores.get(content.id),
                index_by_content.get(content.id), keyword_counts,
                health_service.score_from_prefetched(
                    content, seo_by_content.get(content.id), index_by_content.get(content.id),
                    analytics_by_content.get(content.id, []),
                ).overall,
            )
            for content in content_rows
        ]

        rows = [r for r in rows if self._passes_filters(r, normalized_filters)]
        rows.sort(key=sort_key, reverse=(sort_order.lower() != "asc"))

        return self._paginated_result(rows, page, page_size)

    # ------------------------------------------------------------------
    # Row assembly
    # ------------------------------------------------------------------

    def _build_row(
        self,
        content: Content,
        seo: Optional[ContentSEOData],
        score,
        index_status: Optional[ContentIndexStatus],
        keyword_counts: Dict[str, int],
        health_score: Optional[float],
    ) -> InventoryRow:
        keyword = (seo.focus_keyphrase or "").strip() if seo and seo.focus_keyphrase else None
        keyword_key = keyword.lower() if keyword else ""
        is_indexed = (index_status.verdict == "PASS") if index_status else None
        is_cannibalized = bool(keyword_key) and keyword_counts.get(keyword_key, 0) > 1

        return InventoryRow(
            content_id=content.id,
            url=content.wordpress_url,
            title=content.title,
            primary_keyword=keyword,
            status=content.status,
            health_score=health_score,  # Module 3
            ai_recommendation=None,     # Module 5 — not yet implemented
            opportunity_score=score.opportunity_score if score else None,
            organic_clicks=score.clicks_current if score else None,
            organic_impressions=score.impressions_current if score else None,
            ctr=score.ctr_current if score else None,
            average_position=score.position_current if score else None,
            last_updated=content.updated_at,
            trend=score.trend if score else None,
            needs_update=score.needs_update if score else False,
            low_ctr=score.low_ctr if score else False,
            is_indexed=is_indexed,
            is_cannibalized=is_cannibalized,
        )

    async def _latest_index_status_by_content(
        self, workspace_id: uuid.UUID
    ) -> Dict[uuid.UUID, ContentIndexStatus]:
        """Most recent ContentIndexStatus per content (a content may have been
        inspected via more than one publishing_result historically)."""
        rows = (await self.db.execute(
            select(ContentIndexStatus).where(ContentIndexStatus.workspace_id == workspace_id)
        )).scalars().all()

        latest: Dict[uuid.UUID, ContentIndexStatus] = {}
        for row in rows:
            existing = latest.get(row.content_id)
            row_time = row.inspected_at or row.updated_at
            existing_time = (existing.inspected_at or existing.updated_at) if existing else None
            if not existing or (existing_time is None) or (row_time and row_time > existing_time):
                latest[row.content_id] = row
        return latest

    def _count_published_keywords(
        self, content_rows: Sequence[Content], seo_by_content: Dict[uuid.UUID, ContentSEOData]
    ) -> Dict[str, int]:
        """Count published articles per normalized focus keyphrase (→ cannibalization)."""
        counts: Dict[str, int] = {}
        for content in content_rows:
            if content.status != "published":
                continue
            seo = seo_by_content.get(content.id)
            keyword = (seo.focus_keyphrase or "").strip().lower() if seo and seo.focus_keyphrase else ""
            if keyword:
                counts[keyword] = counts.get(keyword, 0) + 1
        return counts

    # ------------------------------------------------------------------
    # Filtering / sorting / pagination
    # ------------------------------------------------------------------

    def _validate_filters(self, filters: Optional[Sequence[str]]) -> set:
        normalized = {f.strip().lower() for f in (filters or []) if f and f.strip()}
        unknown = normalized - _VALID_FILTERS
        if unknown:
            raise RextValidationException(
                message=(
                    f"Unknown filter(s): {', '.join(sorted(unknown))}. "
                    f"Valid filters: {', '.join(sorted(_VALID_FILTERS))}"
                )
            )
        return normalized

    def _validate_sort(self, sort_by: Optional[str]) -> Callable[[InventoryRow], Any]:
        field = (sort_by or _DEFAULT_SORT_FIELD).strip().lower()
        key_fn = _SORT_KEYS.get(field)
        if key_fn is None:
            raise RextValidationException(
                message=(
                    f"Unknown sort_by '{sort_by}'. "
                    f"Valid values: {', '.join(sorted(_SORT_KEYS.keys()))}"
                )
            )
        return key_fn

    def _passes_filters(self, row: InventoryRow, filters: set) -> bool:
        if not filters:
            return True
        if "published" in filters and row.status != "published":
            return False
        if "growing" in filters and row.trend != "growing":
            return False
        if "declining" in filters and row.trend != "declining":
            return False
        if "needs_update" in filters and not row.needs_update:
            return False
        if "high_opportunity" in filters and not (
            row.opportunity_score is not None and row.opportunity_score >= _HIGH_OPPORTUNITY_THRESHOLD
        ):
            return False
        if "low_ctr" in filters and not row.low_ctr:
            return False
        if "not_indexed" in filters and row.is_indexed is True:
            return False
        if "cannibalized" in filters and not row.is_cannibalized:
            return False
        return True

    def _paginated_result(self, rows: List[InventoryRow], page: int, page_size: int) -> Dict[str, Any]:
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
