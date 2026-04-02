from __future__ import annotations
from typing_extensions import Optional
from src.flow.states.outline.base import BaseOutlineState, SectionState


class ReviewSectionState(SectionState, total=False):
    product_feature: str
    rating: Optional[float]


class InDepthReviewOutlineState(BaseOutlineState, total=False):
    product_name: str
    manufacturer: Optional[str]
    is_biased: bool
    verdict: Optional[str]
    sections: list[ReviewSectionState]
    overall_rating: float
