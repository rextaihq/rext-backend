from typing import List, Optional
from pydantic import Field
from src.flow.model.structure.outlines.base import BaseOutline, Section


class ProductRoundupOutline(BaseOutline):
    """Outline for content summarizing several products or services."""
    category_name: str = Field(description="The general category for the roundup.")
    total_products: int = Field(description="Number of products included.")
    roundup_theme: Optional[str] = Field(description="E.g., 'Budget-friendly', 'For Beginners'.")
    best_value_pick: Optional[str] = Field(description="The best value product in the list.")
    premium_pick: Optional[str] = Field(description="The premium/expensive option in the list.")
