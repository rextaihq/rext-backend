from typing import List, Optional
from pydantic import Field
from src.flow.model.structure.outlines.base import BaseOutline, Section


class BuyingGuideOutline(BaseOutline):
    """Outline for content helping users make a purchasing decision."""
    product_category: str = Field(description="The category being bought (e.g., 'Laptops').")
    key_features_to_consider: List[str] = Field(description="Important features buyers should look for.")
    budget_tiers: Optional[List[str]] = Field(description="Summary of pricing or budget levels.")
    common_mistakes_to_avoid: Optional[List[str]] = Field(description="Pitfalls buyers make.")
