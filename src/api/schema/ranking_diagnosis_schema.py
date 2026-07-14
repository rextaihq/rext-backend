from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class RankingSignalItem(BaseModel):
    key: str
    label: str
    detail: str


class RankingDiagnosisResponse(BaseModel):
    """Module 5 (AI Diagnosis): why a specific article's ranking changed."""

    content_id: UUID
    classification: str  # ranking_drop | ctr_collapse | visibility_drop | improving | stable | no_data
    window_days: int

    position_current: Optional[float] = None
    position_previous: Optional[float] = None
    position_delta: Optional[float] = None
    clicks_current: float
    clicks_previous: float
    clicks_delta_pct: Optional[float] = None
    impressions_current: float
    impressions_previous: float
    impressions_delta_pct: Optional[float] = None

    top_query: Optional[str] = None
    top_query_position: Optional[float] = None

    signals: List[RankingSignalItem] = []
    summary: str
    reasons: List[str] = []

    ai_generated: bool = False
    ai_unavailable_reason: Optional[str] = None
