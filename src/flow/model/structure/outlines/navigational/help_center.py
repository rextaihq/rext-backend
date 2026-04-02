from typing import List, Optional
from pydantic import Field
from src.flow.model.structure.outlines.base import BaseOutline, Section


class HelpCenterOutline(BaseOutline):
    """Outline for a help center homepage or major category page."""
    platform_name: str = Field(description="The platform providing help.")
    top_categories: List[str] = Field(description="The main buckets of support (e.g., 'Billing', 'Account Setup').")
    most_popular_articles: Optional[List[str]] = Field(description="Articles linked directly from the help center homepage.")
    search_bar_prominence: bool = Field(default=True, description="Whether search is the primary action.")
