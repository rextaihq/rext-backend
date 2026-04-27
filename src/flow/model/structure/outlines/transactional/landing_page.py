from typing import List, Optional
from pydantic import Field
from src.flow.model.structure.outlines.base import BaseOutline, Section


class LandingPageOutline(BaseOutline):
    """Outline for a specific lead-gen or offer-driven landing page."""
    campaign_name: str = Field(description="The marketing campaign this belongs to.")
    lead_magnet: Optional[str] = Field(description="What the user gets (e.g., 'Free Ebook', 'Newsletter').")
    conversion_goal: str = Field(description="What action the user should take.")
    hero_headline: str = Field(description="The main hook.")
    benefits_highlighted: List[str] = Field(description="What to emphasize.")
