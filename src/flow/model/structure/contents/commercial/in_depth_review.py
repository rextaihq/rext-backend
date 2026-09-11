from typing import List, Optional

from pydantic import BaseModel, Field

from src.flow.model.structure.contents.base import BaseGeneratedContent


class ReviewSection(BaseModel):
    product_feature: str = Field(description="The specific feature being reviewed.")
    rating: Optional[float] = Field(default=None, description="Rating for this particular feature.")
    details: str = Field(description="Review details for this feature.")


class InDepthReviewGeneratedContent(BaseGeneratedContent):
    product_name: Optional[str] = Field(
        default=None, description="The name of the product or service."
    )
    manufacturer: Optional[str] = Field(default=None, description="Product manufacturer.")
    is_biased: Optional[bool] = Field(default=False)
    verdict: Optional[str] = Field(default=None, description="The final verdict.")
    review_sections: Optional[List[ReviewSection]] = Field(
        default_factory=list, description="Detailed feature-by-feature review sections."
    )
    overall_rating: Optional[float] = Field(
        default=None, ge=0.0, le=10.0, description="Overall numerical rating."
    )
