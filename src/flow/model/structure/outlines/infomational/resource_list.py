from typing import List, Optional, Literal

from pydantic import Field, conlist

from src.flow.model.structure.content_types import ContentType
from src.flow.model.structure.outlines.strict import StrictModel


class Resource(StrictModel):
    """A specific tool, link, or resource."""
    title: str = Field(description="Name or title of the resource.")
    url: Optional[str] = Field(description="URL to the resource (if applicable).")
    description: str = Field(description="Brief overview of what the resource provides.")
    category: Optional[str] = Field(description="Sub-category within this section (e.g., 'Free', 'Premium').")
    pros: Optional[List[str]] = Field(default_factory=list, description="Key benefits or advantages.")


class ResourceSection(StrictModel):
    heading: str = Field(description="Category heading (e.g., 'Monitoring Tools', 'Research Sources').")
    heading_level: Literal["H2", "H3"] = Field(description="Heading level.")
    description: str = Field(description="Brief overview of the resources in this section.")
    resources: conlist(Resource, min_length=2, max_length=15)


class ResourceListOutline(StrictModel):
    content_type: ContentType = Field(
        description="Canonical content type slug. Must match the requested content_type."
    )
    title: str = Field(description="SEO-optimized resource list title starting with focus keyphrase.")
    slug_suggestion: str = Field(
        pattern=r"^[a-z0-9-]+$",
        description="Suggested URL slug."
    )
    brief: str = Field(description="Goal of this curated list and the audience it serves.")
    
    # Selection Criteria Strategy
    focus_keyphrase: str = Field(
        description="The primary domain or skill the resources support."
    )
    keywords_to_include: conlist(str, min_length=2)
    selection_criteria: str = Field(description="How these resources were chosen.")
    
    # Structure
    sections: conlist(ResourceSection, min_length=3, max_length=10)
    
    # Images/Graphics Planning
    image_suggestions: List[str] = Field(
        description="Suggested header image or specific graphics for sections (min 1)."
    )
    
    # Links Planning
    link_suggestions: List[str] = Field(
        description="Direct links to resources and internal related content."
    )
    
    # Schema
    schema_type: Literal["ItemList", "Article", "WebPage"] = Field(
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
    target_word_count: int = Field(ge=500, le=4000)
