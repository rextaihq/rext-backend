from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from src.flow.model.structure.content import ImageAltText, Link, SchemaMarkup
from src.flow.model.structure.outline import Fact


class BaseGeneratedContent(BaseModel):
    """Base model for all generated content types."""
    title: str = Field(description="Final SEO-optimized article title starting with the keyphrase.")
    slug: Optional[str] = Field(default=None, description="URL-friendly slug containing the keyphrase.")
    meta_title: Optional[str] = Field(default=None, description="Meta title (50-60 chars).")
    meta_description: Optional[str] = Field(default=None, description="Meta description (150-160 chars).")
    tags: List[str] = Field(default_factory=list, description="List of tags.")
    focus_keyphrase: Optional[str] = Field(default=None, description="Primary focus keyphrase.")
    keyphrase_density: Optional[float] = Field(default=None, description="Keyphrase density percentage.")
    secondary_keywords: List[str] = Field(default_factory=list, description="Secondary keywords.")
    introduction: Optional[str] = Field(default=None, description="Opening paragraph(s) containing the keyphrase.")
    body_markdown: Optional[str] = Field(default=None, description="Complete body in Markdown (excluding introduction).")
    images: List[ImageAltText] = Field(default_factory=list, description="SEO-optimized image alt suggestions.")
    internal_links: List[Link] = Field(default_factory=list, description="Internal link suggestions.")
    outbound_links: List[Link] = Field(default_factory=list, description="Outbound link suggestions.")
    schema_markup: Optional[SchemaMarkup] = Field(default=None, description="JSON-LD schema markup.")
    facts: List[Fact] = Field(default_factory=list, description="Verifiable facts/statistics.")
