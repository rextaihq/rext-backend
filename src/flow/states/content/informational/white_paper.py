from __future__ import annotations

from typing_extensions import Optional, TypedDict

from src.flow.states.content.base import BaseFinalContent


class ResearchFinding(TypedDict):
    topic: str
    datum: str
    citation_url: Optional[str]
    methodology_context: str


class WhitePaperContent(BaseFinalContent):
    research_findings: list[ResearchFinding]
    executive_summary: str
    methodology_overview: str
    industry_impact_analysis: Optional[str]
    data_sources: list[str]
