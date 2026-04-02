from typing import List, Optional
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class AboutUsGeneratedContent(BaseGeneratedContent):
    company_name: str = Field(description="Company name.")
    mission_statement: str = Field(description="Core mission.")
    key_milestones: Optional[List[str]] = Field(description="Important dates.")
    team_members_mentioned: Optional[List[str]] = Field(description="Key members.")
