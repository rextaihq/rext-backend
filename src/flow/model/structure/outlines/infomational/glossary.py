from typing import List, Optional, Literal

from pydantic import Field, conlist

from src.flow.model.structure.content_types import ContentType
from src.flow.model.structure.outlines.strict import StrictModel


class GlossaryEntry(StrictModel):
    """An individual term and its definition."""
    term: str = Field(description="The term or phrase being defined.")
    definition: str = Field(description="Clear and concise definition.")
    examples: Optional[List[str]] = Field(default_factory=list, description="Examples of the term in use.")
    related_terms: Optional[List[str]] = Field(default_factory=list, description="Terms related to this one.")


class GlossarySection(StrictModel):
    heading: str = Field(description="Alphabetical or category heading (e.g., 'A-C', 'Tech Terms').")
    heading_level: Literal["H2", "H3"] = Field(description="Heading level.")
    description: str = Field(description="Introduction to the terms in this section.")
    entries: conlist(GlossaryEntry, min_length=2, max_length=20)


class GlossaryOutline(StrictModel):
    content_type: ContentType = Field(
        description="Canonical content type slug. Must match the requested content_type."
    )
    title: str = Field(description="SEO-optimized glossary title (e.g., '[Focus Keyphrase] Glossary').")
    slug_suggestion: str = Field(
        pattern=r"^[a-z0-9-]+$",
        description="Suggested URL slug."
    )
    brief: str = Field(description="Target audience and the specific lexicon the glossary covers.")
    
    # Context
    focus_keyphrase: str = Field(
        description="The primary domain or industry the glossary covers."
    )
    keywords_to_include: conlist(str, min_length=1)
    
    # Structure
    sections: conlist(GlossarySection, min_length=1, max_length=20)
    
    # Navigation/A-Z Strategy
    alphabetical_navigation: bool = Field(default=True, description="Whether to include A-Z navigation at the top.")
    
    # Images Planning
    image_suggestions: List[str] = Field(
        description="Suggested header image or icons for categories (min 1)."
    )
    
    # Links Planning
    link_suggestions: List[str] = Field(
        description="Suggested internal links to in-depth guides for terms."
    )
    
    # Schema
    schema_type: Literal["Article", "DefinedTermSet", "WebPage"] = Field(
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
    target_word_count: int = Field(ge=500, le=5000)
