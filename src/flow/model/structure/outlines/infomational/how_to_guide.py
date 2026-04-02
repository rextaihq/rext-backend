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
        description="Which section this image belongs to (e.g., 'introduction', 'step-1')."
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


class Step(BaseModel):
    """A single actionable step in the guide."""
    title: str = Field(description="Title of the step.")
    description: str = Field(description="Detailed instructions for this step.")
    tools_needed: Optional[List[str]] = Field(default_factory=list, description="Specific tools or materials for this step.")


class HowToSection(BaseModel):
    heading: str = Field(description="Section heading text.")
    heading_level: Literal["H2", "H3"] = Field(description="Heading level.")
    description: str = Field(description="What this section will cover.")
    key_points: conlist(str, min_length=2, max_length=6)
    steps: Optional[List[Step]] = Field(default_factory=list, description="Instructional steps within this section.")


class HowToGuideOutline(BaseModel):
    title: str = Field(description="SEO-optimized guide title starting with the focus keyphrase.")
    slug_suggestion: str = Field(
        pattern=r"^[a-z0-9-]+$",
        description="Suggested URL slug containing the focus keyphrase."
    )
    brief: str = Field(description="Guide goal and the specific problem it solves.")
    
    # Keyphrase Strategy
    focus_keyphrase: str = Field(
        description="The primary focus keyphrase for this guide."
    )
    keywords_to_include: conlist(str, min_length=1)
    
    # Prerequisite Info
    total_time: Optional[str] = Field(description="Estimated time to complete (e.g., '30 mins').")
    difficulty: Literal["Beginner", "Intermediate", "Advanced"] = "Beginner"
    tools_needed: List[str] = Field(default_factory=list, description="Overall tools or supplies required.")
    
    # Structure
    sections: conlist(HowToSection, min_length=3, max_length=10)
    faqs: Optional[List[str]] = Field(default_factory=list, description="FAQ questions for schema.")
    
    # Images Planning
    image_suggestions: List[ImageSuggestion] = Field(
        min_length=1,
        description="Suggested images (min 1)."
    )
    
    # Links Planning
    link_suggestions: List[LinkSuggestion] = Field(
        min_length=2,
        description="Suggested internal and outbound links (min 2)."
    )
    
    # Schema
    schema_type: Literal["HowTo", "Article"] = Field(
        default="HowTo",
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
