from typing import List, Optional, Literal
from pydantic import BaseModel, Field, conlist

class Section(BaseModel):
    """Represents a single section in an SEO-friendly article."""
    heading: str = Field(description="The heading of the section (H2 or H3).")
    description: str = Field(description="Brief summary of what the section will cover.")
    key_points: conlist(str, min_length=1, max_length=4) = Field(
        description="2–4 key points or subtopics to include in the section."
    )
    suggested_word_count: Optional[int] = Field(
        None, description="Recommended word count for this section (150–300 for SEO blogs)."
    )

class Outline(BaseModel):
    """Represents a compact SEO-friendly content outline."""
    title: str = Field(description="SEO-optimized article title.")
    brief: str = Field(description="Short summary of the article's goal and value.")
    sections: conlist(Section, min_length=3, max_length=6) = Field(
        description="3–6 sections for SEO blog content."
    )
    target_audience: List[str] = Field(description="Primary and secondary audience.")
    tone: Literal["Professional", "Conversational", "Casual", "Authoritative"] = Field(
        description="Tone of voice for the article."
    )
    keywords_to_include: conlist(str, min_length=1) = Field(
        description="List of primary and secondary keywords to include."
    )