from typing import List, Optional
from pydantic import Field
from src.flow.model.structure.outlines.base import BaseOutline, Section


class ReviewSection(Section):
    """Specific for product review focus."""
    product_feature: str = Field(description="The specific feature being reviewed in this section.")
    rating: Optional[float] = Field(description="Rating for this particular feature (0.0 to 10.0).")


class InDepthReviewOutline(BaseOutline):
    """Outline for a single-product in-depth review."""
    product_name: str = Field(description="The name of the product or service.")
    manufacturer: Optional[str] = Field(description="Product manufacturer or developer.")
    is_biased: bool = Field(default=False, description="Whether the review is promotional or independent.")
    verdict: Optional[str] = Field(description="The final verdict on the product.")
    sections: List[ReviewSection] = Field(description="Detailed feature-by-feature review sections.")
    overall_rating: float = Field(ge=0.0, le=10.0, description="The overall numerical rating out of 10.")
