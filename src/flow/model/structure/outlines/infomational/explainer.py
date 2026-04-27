from typing import List, Optional, Literal
from pydantic import BaseModel, Field, conlist


class ImageSuggestion(BaseModel):
    """Suggested image or diagram for explaining a concept."""
    
    description: str = Field(
        description="Description of what the image/diagram should show (e.g., 'A diagram showing the relation between X and Y')."
    )
    alt_text_template: str = Field(
        description="Template for SEO-optimized alt text."
    )
    section: str = Field(
        description="Which section this image/diagram belongs to."
    )


class LinkSuggestion(BaseModel):
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


class KeyConcept(BaseModel):
    """A core concept defined in the explainer."""
    term: str = Field(description="Term or concept being explained.")
    definition: str = Field(description="Clear and concise definition.")
    examples: Optional[List[str]] = Field(default_factory=list, description="Concrete examples of this concept.")


class ExplainerSection(BaseModel):
    heading: str = Field(description="Section heading text.")
    heading_level: Literal["H2", "H3"] = Field(description="Heading level.")
    description: str = Field(description="What this section will explain.")
    key_points: conlist(str, min_length=2, max_length=6)
    concepts: Optional[List[KeyConcept]] = Field(default_factory=list, description="Key concepts covered in this section.")


class ExplainerOutline(BaseModel):
    title: str = Field(description="SEO-optimized explainer title (e.g., 'What is [Focus Keyphrase]?').")
    slug_suggestion: str = Field(
        pattern=r"^[a-z0-9-]+$",
        description="Suggested URL slug."
    )
    brief: str = Field(description="The primary goal of this explainer and the knowledge gap it fills.")
    
    # Keyphrase Strategy
    focus_keyphrase: str = Field(
        description="The primary term or topic being explained."
    )
    keywords_to_include: conlist(str, min_length=1)
    
    # Structure
    sections: conlist(ExplainerSection, min_length=3, max_length=10)
    faqs: Optional[List[str]] = Field(default_factory=list, description="Questions common users ask about this topic.")
    
    # Images/Diagrams Planning
    image_suggestions: List[ImageSuggestion] = Field(
        min_length=1,
        description="Suggested diagrams or illustrative images (min 1)."
    )
    
    # Links Planning
    link_suggestions: List[LinkSuggestion] = Field(
        min_length=2,
        description="Suggested internal and outbound links (min 2)."
    )
    
    # Schema
    schema_type: Literal["Article", "HowTo", "FAQPage"] = Field(
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
    target_word_count: int = Field(ge=800, le=5000)
