from typing import List, Optional
from pydantic import BaseModel, Field

class Section(BaseModel):
    """Represents a single section within a content outline."""
    heading: str = Field(description="The heading of the section (e.g., H2 or H3).")
    description: str = Field(description="A brief overview of what this section will cover.")
    key_points: List[str] = Field(description="A list of key points or sub-topics to be discussed in this section.")
    suggested_word_count: Optional[int] = Field(None, description="The recommended word count for this section.")

class Outline(BaseModel):
    """Represents the full outline of the content to be generated."""
    title: str = Field(description="A compelling, SEO-optimized title for the article.")
    brief: str = Field(description="A short summary of the content's goal, angle, and unique value proposition.")
    sections: List[Section] = Field(description="A structured list of sections that make up the article.")
    target_audience: List[str] = Field(description="The primary and secondary audiences for this content.")
    tone: str = Field(description="The recommended tone of voice (e.g., Professional, Conversational, Technical).")
    keywords_to_include: List[str] = Field(description="A list of primary and secondary keywords to be integrated into the content.")