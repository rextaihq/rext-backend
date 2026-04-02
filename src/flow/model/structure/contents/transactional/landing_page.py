from typing import List, Optional
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class LandingPageGeneratedContent(BaseGeneratedContent):
    campaign_name: str = Field(description="Sales campaign name.")
    lead_magnet: Optional[str] = Field(description="The lead magnet offered.")
    conversion_goal: str = Field(description="Goal for conversion.")
    hero_headline: str = Field(description="Main hook.")
    benefits_highlighted: List[str] = Field(description="Emphasized benefits.")
