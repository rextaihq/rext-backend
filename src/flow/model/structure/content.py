from typing import List, Optional
from pydantic import BaseModel, Field

class GeneratedContent(BaseModel):
    """Validated output of the content generation step."""

    title: str = Field(description="Final SEO-optimized article title.")

    meta_title: str = Field(description="Meta title for the article.")
    meta_description: str = Field(description="Meta description for the article.")
    tags: List[str] = Field(description="List of tags for the article.")
    
    primary_keyword: Optional[str] = Field(description="Primary keyword for the article.")
    secondary_keywords: Optional[List[str]] = Field(description="Secondary keywords for the article.")

    body_markdown: str = Field(
        description="Complete article written in Markdown format, following the approved outline."
    )

    word_count: int = Field(
        ge=100,
        le=300,
        description="Total word count of the article."
    )   