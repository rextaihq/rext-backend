from typing import List, Optional
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class ResearchFinding(BaseModel):
    topic: str = Field(description="Topic or theme.")
    datum: str = Field(description="Key finding or data point.")
    citation_url: Optional[str] = Field(description="Link to study or source.")
    methodology_context: str = Field(description="Background on how this finding was obtained.")


class WhitePaperGeneratedContent(BaseGeneratedContent):
    research_findings: List[ResearchFinding] = Field(description="Core data and analysis findings.")
    executive_summary: str = Field(description="Brief summary for stakeholders.")
    methodology_overview: str = Field(description="Explanation of the research approach.")
    industry_impact_analysis: Optional[str] = Field(description="What this means for the industry.")
    data_sources: List[str] = Field(default_factory=list, description="List of report or data URLs used.")
