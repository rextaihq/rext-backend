from __future__ import annotations

from typing_extensions import Optional, TypedDict

from src.flow.states.content.base import BaseFinalContent


class ReviewSectionState(TypedDict, total=False):
    product_feature: str
    rating: Optional[float]
    details: str


class InDepthReviewContentState(BaseFinalContent, total=False):
    product_name: str
    manufacturer: Optional[str]
    is_biased: bool
    verdict: Optional[str]
    review_sections: list[ReviewSectionState]
    overall_rating: float
