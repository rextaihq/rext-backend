from __future__ import annotations
from typing_extensions import Optional
from src.flow.states.content.base import BaseFinalContent


class LandingPageContentState(BaseFinalContent, total=False):
    campaign_name: str
    lead_magnet: Optional[str]
    conversion_goal: str
    hero_headline: str
    benefits_highlighted: list[str]
