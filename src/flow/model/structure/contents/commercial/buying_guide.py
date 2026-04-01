from typing import List, Optional
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class BuyingGuideGeneratedContent(BaseGeneratedContent):
    product_category: str = Field(description="The category being bought.")
    key_features_to_consider: List[str] = Field(description="Important features to look for.")
    budget_tiers: Optional[List[str]] = Field(description="Summary of pricing or budget levels.")
    common_mistakes_to_avoid: Optional[List[str]] = Field(description="Pitfalls buyers make.")
