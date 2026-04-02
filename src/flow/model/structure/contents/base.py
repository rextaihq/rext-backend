from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from src.flow.model.structure.content import ImageAltText, Link, SchemaMarkup
from src.flow.model.structure.outline import Fact


class BaseGeneratedContent(BaseModel):
    """Base model for all generated content types."""
    title: str = Field(description="Final SEO-optimized article title starting with the keyphrase.")
    slug: str = Field(description="URL-friendly slug containing the keyphrase.")
    meta_title: str = Field(description="Meta title (50-60 chars).")
    meta_description: str = Field(description="Meta description (150-160 chars).")
    tags: List[str] = Field(description="List of tags.")
    focus_keyphrase: str = Field(description="Primary focus keyphrase.")
    keyphrase_density: float = Field(description="Keyphrase density percentage.")
    secondary_keywords: List[str] = Field(default=[], description="Secondary keywords.")
    introduction: str = Field(description="Opening paragraph(s) containing the keyphrase.")
    body_markdown: str = Field(description="Complete body in Markdown (excluding introduction).")
    images: List[ImageAltText] = Field(default=[], description="SEO-optimized image alt suggestions.")
    internal_links: List[Link] = Field(default=[], description="Internal link suggestions.")
    outbound_links: List[Link] = Field(default=[], description="Outbound link suggestions.")
    schema_markup: SchemaMarkup = Field(description="JSON-LD schema markup.")
    facts: List[Fact] = Field(default_factory=list, description="Verifiable facts/statistics.")
