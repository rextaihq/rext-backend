from typing import List, Optional, Literal

from pydantic import Field, HttpUrl, conlist

from src.flow.model.structure.content_types import ContentType
from src.flow.model.structure.outlines.strict import StrictModel


class ImageSuggestion(StrictModel):
    """Suggested image or illustration for a section."""
    
    description: str = Field(
        description="Description of what the image should show."
    )
    alt_text_template: str = Field(
        description="Template for SEO-optimized alt text."
    )
    section: str = Field(
        description="Which section this image belongs to."
    )


class LinkSuggestion(StrictModel):
    """Suggested link with context."""
    
    anchor_text: str = Field(description="Suggested anchor text.")
    link_type: Literal["internal", "outbound"] = Field(
        description="Type of link to suggest."
    )
    context: str = Field(
        description="Context about what this link should point to."
    )
    section: str = Field(
        description="Which section this link should appear in."
    )


class Fact(StrictModel):
    """Verifiable fact or statistic with source citation context."""
    
    text: str = Field(description="The factual statement or statistic.")
    source_url: Optional[HttpUrl] = Field(
        default=None, description="Direct source URL for verifying this fact."
    )


class PillarSection(StrictModel):
    heading: str = Field(description="Section heading text.")
    heading_level: Literal["H2", "H3"] = Field(description="Heading level.")
    description: str = Field(description="Comprehensive coverage summary for this section.")
    key_points: conlist(str, min_length=2, max_length=8)
    subtopic_cluster: Optional[List[str]] = Field(default_factory=list, description="Related topics or clusters this section might link to.")
    facts: Optional[List[Fact]] = Field(default_factory=list, description="Statistics or data points to include.")


class PillarContentOutline(StrictModel):
    content_type: ContentType = Field(
        description="Canonical content type slug. Must match the requested content_type."
    )
    title: str = Field(description="SEO-optimized pillar article title starting with the focus keyphrase.")
    slug_suggestion: str = Field(
        pattern=r"^[a-z0-9-]+$",
        description="Suggested URL slug."
    )
    brief: str = Field(description="Overall mission statement for this ultimate guide/pillar content.")
    
    # Topic Authority Strategy
    focus_keyphrase: str = Field(
        description="The primary broad focus keyphrase (e.g., 'Content Marketing')."
    )
    keywords_to_include: conlist(str, min_length=5)
    related_clusters: List[str] = Field(description="Other subtopics that this pillar piece aims to govern.")
    
    # Structure
    sections: conlist(PillarSection, min_length=6, max_length=15)
    faqs: Optional[List[str]] = Field(default_factory=list, description="Extensive list of common questions.")
    
    # Images Planning
    image_suggestions: List[ImageSuggestion] = Field(
        min_length=3,
        description="High-quality images/graphics to keep the reader engaged (min 3)."
    )
    
    # Links Planning (Focus on Topic Clusters)
    link_suggestions: List[LinkSuggestion] = Field(
        min_length=4,
        description="Significant internal/external linking (min 4)."
    )
    
    # Schema
    schema_type: Literal["Article", "WebPage", "FAQPage"] = Field(
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
    target_word_count: int = Field(ge=1500, le=10000)
