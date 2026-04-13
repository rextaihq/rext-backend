from typing import List, Optional, Literal

from pydantic import Field, conlist

from src.flow.model.structure.content_types import ContentType
from src.flow.model.structure.outlines.strict import StrictModel


class ResultMetric(StrictModel):
    """A specific metric or result achieved in the case study."""
    metric_name: str = Field(description="Name of the metric (e.g., 'Conversion Rate', 'Reduction in Cost').")
    result_value: str = Field(description="The achievement or numeric value (e.g., '+20%', '$50,000 saved').")
    context: Optional[str] = Field(description="Explanation of the significance of this result.")


class CaseStudySection(StrictModel):
    heading: str = Field(description="Section heading (e.g., 'The Challenge', 'Implementing X').")
    heading_level: Literal["H2", "H3"] = Field(description="Heading level.")
    description: str = Field(description="Overview of the challenges, actions, or outcomes in this stage.")
    key_highlights: conlist(str, min_length=2, max_length=6)
    results: Optional[List[ResultMetric]] = Field(default_factory=list, description="Specific metrics or KPIs for this stage.")


class CaseStudyOutline(StrictModel):
    content_type: ContentType = Field(
        description="Canonical content type slug. Must match the requested content_type."
    )
    title: str = Field(description="SEO-optimized case study title starting with focus keyphrase.")
    slug_suggestion: str = Field(
        pattern=r"^[a-z0-9-]+$",
        description="Suggested URL slug."
    )
    brief: str = Field(description="Client/project overview and the problem solved.")
    
    # Context
    focus_keyphrase: str = Field(
        description="The primary solution or service highlighted in the case study."
    )
    keywords_to_include: conlist(str, min_length=2)
    client: str = Field(description="The client or subject of the study.")
    
    # Structure
    sections: conlist(CaseStudySection, min_length=3, max_length=10)
    
    # Visual Storytelling
    image_suggestions: List[str] = Field(
        description="Suggested 'before/after' photos, client logo, or infographics (min 2)."
    )
    
    # Links Planning
    link_suggestions: List[str] = Field(
        description="Related product/service pages or client website."
    )
    
    # Schema
    schema_type: Literal["Article", "NewsArticle"] = Field(
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
    target_word_count: int = Field(ge=800, le=4000)
