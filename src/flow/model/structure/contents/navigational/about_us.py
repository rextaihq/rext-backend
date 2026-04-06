from typing import List, Optional
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class AboutUsGeneratedContent(BaseGeneratedContent):
    company_name: Optional[str] = Field(default=None, description="Company name.")
    mission_statement: Optional[str] = Field(default=None, description="Core mission.")
    key_milestones: Optional[List[str]] = Field(default=None, description="Important dates.")
    team_members_mentioned: Optional[List[str]] = Field(default=None, description="Key members.")
