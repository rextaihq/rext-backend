from typing import List, Optional, Literal

from pydantic import Field, conlist

from src.flow.model.structure.content_types import ContentType
from src.flow.model.structure.outlines.strict import StrictModel


class ResearchFinding(StrictModel):
    """A specific research finding or data point."""
    topic: str = Field(description="Topic or theme of the finding.")
    data_points: List[str] = Field(description="Key statistics, results, or data points.")
    implication: str = Field(description="What this means for the reader/industry.")


class WhitePaperSection(StrictModel):
    heading: str = Field(description="Section heading (e.g., 'Methodology', 'Key Trends').")
    heading_level: Literal["H2", "H3"] = Field(description="Heading level.")
    description: str = Field(description="Goal of this section in the paper.")
    findings: conlist(ResearchFinding, min_length=1, max_length=5)


class WhitePaperOutline(StrictModel):
    content_type: ContentType = Field(
        description="Canonical content type slug. Must match the requested content_type."
    )
    title: str = Field(description="SEO-optimized white paper title (e.g., 'State of [Focus Keyphrase]').")
    slug_suggestion: str = Field(
        pattern=r"^[a-z0-9-]+$",
        description="Suggested URL slug."
    )
    brief: str = Field(description="Overall goal and value proposition for the research.")
    
    # Context
    focus_keyphrase: str = Field(
        description="The primary research topic or industry focus."
    )
    keywords_to_include: conlist(str, min_length=3)
    methodology: str = Field(description="The research methodology used (e.g., 'Survey of 500 professionals').")
    
    # Structure
    sections: conlist(WhitePaperSection, min_length=4, max_length=12)
    
    # Data Visualizations Planning
    image_suggestions: List[str] = Field(
        description="Suggested charts, graphs, or visual data points (min 3)."
    )
    
    # Links Planning
    link_suggestions: List[str] = Field(
        description="Official reports, primary sources, or related white papers."
    )
    
    # Schema
    schema_type: Literal["Article", "WhitePaper", "ScholarlyArticle"] = Field(
        default="Article",
        description="Primary schema.org type."
    )
    
    # Content Strategy
    target_audience: List[str]
    tone: Literal[
    "Professional", "Conversational", "Authoritative", "Friendly", 
    "Encouraging", "Neutral", "Persuasive", "Analytical", 
    "Direct", "Action-oriented", "Trustworthy", "Urgent"
    ]
    target_word_count: int = Field(ge=2000, le=15000)
