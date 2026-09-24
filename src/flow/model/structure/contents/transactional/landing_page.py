from typing import List, Optional

from pydantic import Field

from src.flow.model.structure.contents.base import BaseGeneratedContent


class LandingPageGeneratedContent(BaseGeneratedContent):
    campaign_name: Optional[str] = Field(default=None, description="Sales campaign name.")
    lead_magnet: Optional[str] = Field(default=None, description="The lead magnet offered.")
    conversion_goal: Optional[str] = Field(default=None, description="Goal for conversion.")
    hero_headline: Optional[str] = Field(default=None, description="Main hook.")
    benefits_highlighted: Optional[List[str]] = Field(
        default_factory=list, description="Emphasized benefits."
    )
