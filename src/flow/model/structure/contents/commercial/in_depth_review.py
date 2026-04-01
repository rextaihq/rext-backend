from typing import List, Optional
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class ReviewSection(BaseModel):
    product_feature: str = Field(description="The specific feature being reviewed.")
    rating: Optional[float] = Field(description="Rating for this particular feature.")
    details: str = Field(description="Review details for this feature.")


class InDepthReviewGeneratedContent(BaseGeneratedContent):
    product_name: str = Field(description="The name of the product or service.")
    manufacturer: Optional[str] = Field(description="Product manufacturer.")
    is_biased: bool = Field(default=False)
    verdict: Optional[str] = Field(description="The final verdict.")
    review_sections: List[ReviewSection] = Field(description="Detailed feature-by-feature review sections.")
    overall_rating: float = Field(ge=0.0, le=10.0, description="Overall numerical rating.")
