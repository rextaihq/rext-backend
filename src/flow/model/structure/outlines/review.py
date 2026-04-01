from __future__ import annotations

from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field

from .common import OutlineBase, _ensure_focus_keyphrase_in_title


class RatingBreakdownItem(BaseModel):
    criterion: str
    rating: float = Field(ge=0, le=5)
    notes: str = Field(description="Why it scored this way (practical + specific).")


class FeatureItem(BaseModel):
    name: str
    why_it_matters: str
    what_to_check: Optional[List[str]] = Field(
        default=None, description="How to evaluate this feature."
    )


class ReviewOutlineBase(OutlineBase):
    product_or_service: str = Field(description="The exact product/service being reviewed.")
    who_its_for: Annotated[list[str], Field(min_length=2, max_length=6)]
    who_its_not_for: Optional[List[str]] = Field(default=None)
    rating: float = Field(ge=0, le=5, description="Overall rating out of 5.")
    rating_breakdown: Optional[List[RatingBreakdownItem]] = Field(default=None)
    standout_features: Annotated[list[FeatureItem], Field(min_length=3, max_length=10)]
    pros: Annotated[list[str], Field(min_length=3, max_length=8)]
    cons: Annotated[list[str], Field(min_length=2, max_length=8)]
    alternatives: Optional[List[str]] = Field(
        default=None, description="Alternatives worth considering."
    )
    verdict: str = Field(description="Final verdict with clear recommendation.")
    faqs: Optional[List[str]] = Field(default=None)
    schema_type: Literal["Review", "Article"] = Field(default="Review")


def validate_review_outline(outline: ReviewOutlineBase) -> None:
    _ensure_focus_keyphrase_in_title(outline.title, outline.focus_keyphrase)
    if outline.rating_breakdown:
        if len(outline.rating_breakdown) < 3:
            raise ValueError("rating_breakdown must include at least 3 criteria when provided")
