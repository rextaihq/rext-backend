from __future__ import annotations
from typing_extensions import TypedDict, Literal, Optional, Annotated
import operator


class ResearchFinding(TypedDict):
    topic: str
    data_points: list[str]
    implication: str


class WhitePaperSection(TypedDict):
    heading: str
    heading_level: Literal["H2", "H3"]
    description: str
    findings: list[ResearchFinding]


class WhitePaperOutline(TypedDict):
    title: str
    slug_suggestion: str
    brief: str
    
    # Context
    focus_keyphrase: str
    keywords_to_include: list[str]
    methodology: str
    
    # Structure
    sections: list[WhitePaperSection]
    
    # Data Visualizations Planning
    image_suggestions: list[str]
    
    # Links Planning
    link_suggestions: list[str]
    
    # Schema
    schema_type: Literal["Article", "WhitePaper", "ScholarlyArticle"]
    
    # Content Strategy
    target_audience: list[str]
    tone: str
    target_word_count: int

    # Workflow fields
    status: Literal["approved", "rejected", "reviewing"]
    rejected_reason: Annotated[Optional[str], operator.add]
