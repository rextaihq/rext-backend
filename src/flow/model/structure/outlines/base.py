from typing import List, Optional, Literal
from pydantic import BaseModel, Field, conlist


class ImageSuggestion(BaseModel):
    """Suggested image for a section with SEO context."""
    
    description: str = Field(
        description="Description of what the image should show."
    )
    alt_text_template: str = Field(
        description="Template for SEO-optimized alt text (should include keyphrase or synonyms)."
    )
    section: str = Field(
        description="Which section this image belongs to (e.g., 'introduction', 'section-2')."
    )


class LinkSuggestion(BaseModel):
    """Suggested link with context."""
    
    anchor_text: str = Field(description="Suggested anchor text.")
    link_type: Literal["internal", "outbound"] = Field(
        description="Type of link to suggest."
    )
    context: str = Field(
        description="Context about what this link should point to or why it's needed."
    )
    section: str = Field(
        description="Which section this link should appear in."
    )


class Fact(BaseModel):
    """Verifiable fact or statistic with source citation context."""
    
    text: str = Field(description="The factual statement or statistic.")


class Section(BaseModel):
    heading: str = Field(description="Section heading text.")
    heading_level: Literal["H2", "H3"] = Field(description="Heading level.")
    description: str = Field(description="What this section will cover.")
    key_points: conlist(str, min_length=2, max_length=6)
    questions_to_answer: Optional[List[str]] = Field(
        description="PAA or user questions to answer in this section."
    )
    snippet_target: Optional[bool] = False
    search_intent: Literal["informational", "commercial", "navigational", "transactional"] = "informational"
    suggested_word_count: Optional[int] = 200
    include_keyphrase_in_heading: bool = Field(
        default=False,
        description="Whether this heading should include the focus keyphrase or a variant."
    )
    facts: Optional[List[Fact]] = Field(
        default=[],
        description="Verifiable facts, statistics, or data points with sources to include in this section."
    )


class BaseOutline(BaseModel):
    title: str = Field(description="SEO-optimized article title starting with the focus keyphrase.")
    slug_suggestion: str = Field(
        pattern=r"^[a-z0-9-]+$",
        description="Suggested URL slug containing the focus keyphrase."
    )
    brief: str = Field(description="Article goal and value proposition.")
    
    # Keyphrase Strategy
    focus_keyphrase: str = Field(
        description="The primary focus keyphrase for this article (2-4 words recommended)."
    )
    keywords_to_include: conlist(str, min_length=1)
    
    # Structure
    sections: conlist(Section, min_length=4, max_length=8)
    faqs: Optional[List[str]] = Field(default_factory=list, description="FAQ questions for schema.")
    key_facts: Optional[List[Fact]] = Field(
        default_factory=list,
        description="Key verifiable facts or statistics with sources to be used throughout the article."
    )
    
    # Images Planning
    image_suggestions: List[ImageSuggestion] = Field(
        min_length=1,
        description="Suggested images with SEO context (minimum 1 required)."
    )
    
    # Links Planning
    link_suggestions: List[LinkSuggestion] = Field(
        min_length=2,
        description="Suggested internal and outbound links (minimum 2 required)."
    )
    
    # Schema
    schema_type: Literal["Article", "HowTo", "FAQPage", "BlogPosting", "Product", "Review"] = Field(
        default="Article",
        description="Primary schema.org type for structured data."
    )
    
    # Content Strategy
    target_audience: List[str]
    tone: Literal[
        "Professional",
        "Conversational",
        "Authoritative",
        "Friendly",
        "Encouraging",
        "Neutral",
        "Persuasive",
        "Analytical",
        "Direct",
        "Action-oriented",
        "Trustworthy",
        "Urgent"
    ]
    target_word_count: int = Field(
        ge=500,
        le=5000,
        description="Target word count for the complete article."
    )
