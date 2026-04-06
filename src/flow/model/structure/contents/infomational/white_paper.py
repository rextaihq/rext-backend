from typing import List, Optional
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class ResearchFinding(BaseModel):
    topic: str = Field(description="Topic or theme.")
    datum: str = Field(description="Key finding or data point.")
    citation_url: Optional[str] = Field(default=None, description="Link to study or source.")
    methodology_context: Optional[str] = Field(default=None, description="Background on how this finding was obtained.")


class WhitePaperGeneratedContent(BaseGeneratedContent):
    research_findings: Optional[List[ResearchFinding]] = Field(default_factory=list, description="Core data and analysis findings.")
    executive_summary: Optional[str] = Field(default=None, description="Brief summary for stakeholders.")
    methodology_overview: Optional[str] = Field(default=None, description="Explanation of the research approach.")
    industry_impact_analysis: Optional[str] = Field(default=None, description="What this means for the industry.")
    data_sources: List[str] = Field(default_factory=list, description="List of report or data URLs used.")
