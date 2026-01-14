from typing import List, Optional
from pydantic import BaseModel, Field, HttpUrl


class ImageAsset(BaseModel):
    """Represents an image asset with SEO-optimized attributes."""
    
    url: str = Field(description="Image URL or path.")
    alt_text: str = Field(
        description="SEO-optimized alt text containing the keyphrase or synonyms."
    )
    caption: Optional[str] = Field(
        default=None,
        description="Optional image caption for context."
    )
    placement: str = Field(
        description="Where in the article this image should appear (e.g., 'introduction', 'section-2', 'conclusion')."
    )


class Link(BaseModel):
    """Represents an internal or outbound link."""
    
    url: str = Field(description="Link URL.")
    anchor_text: str = Field(description="Anchor text for the link.")
    link_type: str = Field(
        description="Type of link: 'internal' or 'outbound'."
    )
    placement: str = Field(
        description="Where in the article this link should appear (e.g., 'introduction', 'section-1', 'conclusion')."
    )
    rel: Optional[str] = Field(
        default=None,
        description="Link relationship attribute (e.g., 'nofollow', 'sponsored')."
    )


class SchemaMarkup(BaseModel):
    """Represents structured data/schema markup for the article."""
    
    schema_type: str = Field(
        default="Article",
        description="Schema.org type (e.g., 'Article', 'HowTo', 'FAQPage')."
    )
    schema_data: str = Field(
        description="Complete JSON-LD schema markup as a JSON string (to be parsed as JSON)."
    )


class GeneratedContent(BaseModel):
    """Validated output of the content generation step with comprehensive SEO requirements."""

    # Core Content
    title: str = Field(description="Final SEO-optimized article title starting with the keyphrase.")
    slug: str = Field(
        description="URL-friendly slug containing the keyphrase (e.g., 'best-seo-tools-2026')."
    )
    
    # SEO Meta Tags
    meta_title: str = Field(
        description="Meta title for the article, beginning with the keyphrase (50-60 chars)."
    )
    meta_description: str = Field(
        description="Meta description containing the keyphrase (150-160 chars)."
    )
    tags: List[str] = Field(description="List of tags for the article.")
    
    # Keywords
    focus_keyphrase: str = Field(
        description="The primary focus keyphrase for this article (2-4 words recommended)."
    )
    keyphrase_density: float = Field(
        ge=0.5,
        le=2.5,
        description="Keyphrase density percentage (target: 0.5%-2.5%)."
    )
    secondary_keywords: List[str] = Field(
        default=[],
        description="Secondary keywords for the article."
    )
    
    # Introduction
    introduction: str = Field(
        description="Opening paragraph(s) that introduce the topic and contain the keyphrase naturally (150-300 words in Markdown).",
        min_length=150,
        max_length=2000,
    )
    
    # Main Content
    body_markdown: str = Field(
        description="Complete article body written in Markdown format (excluding introduction), following the approved outline. Must include subheadings with keyphrase variants.",
        min_length=800,
        max_length=30000,
    )
    
    # Images
    images: List[ImageAsset] = Field(
        min_length=1,
        description="List of images with SEO-optimized alt text containing the keyphrase or synonyms."
    )
    
    # Links
    internal_links: List[Link] = Field(
        min_length=1,
        description="Internal links to other pages on the site."
    )
    outbound_links: List[Link] = Field(
        min_length=1,
        description="Outbound links to authoritative external sources."
    )
    
    # Schema Markup
    schema_markup: SchemaMarkup = Field(
        description="Structured data/schema markup for the article."
    )