from typing import List, Optional
from pydantic import Field
from src.flow.model.structure.outlines.base import BaseOutline, Section


class AboutUsOutline(BaseOutline):
    """Outline for an about us / company story page."""
    company_name: str = Field(description="The company name.")
    mission_statement: str = Field(description="The core mission of the company.")
    key_milestones: Optional[List[str]] = Field(description="Important dates or achievements in company history.")
    team_members_mentioned: Optional[List[str]] = Field(description="Key founders or leaders highlighted in the story.")
