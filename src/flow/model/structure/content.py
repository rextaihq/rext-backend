from typing import List, Optional
from typing import List, Optional
import logging
from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)


class ImageAltText(BaseModel):
    """Represents an SEO-optimized alt text suggestion for an image placeholder."""

    alt_text: str = Field(
        description="SEO-optimized alt text containing the keyphrase or synonyms for the suggested image."
    )
    context: str = Field(
        description="Description of what type of image should be placed here (e.g., 'screenshot of dashboard', 'infographic showing statistics', 'diagram of process')."
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
        ge=0.0,
        le=10.0,
        description="Keyphrase density percentage (ideal target: 0.5%-2.5%, acceptable: 0.1%-5.0%)."
    )
    secondary_keywords: List[str] = Field(
        default=[],
        description="Secondary keywords for the article."
    )

    # Introduction
    introduction: str = Field(
        description="Opening paragraph(s) that introduce the topic and contain the keyphrase naturally (target: 150-300 words in Markdown).",
        min_length=50,
        max_length=5000,
    )

    # Main Content
    body_markdown: str = Field(
        description="""Complete article body written in Markdown format (excluding introduction), following the approved outline. Must include subheadings with keyphrase variants.
        H2 length must be 5-10 words.
        H3 length must be 5-10 words.
        """,
        min_length=200,
        max_length=60000,
    )

    # Html content
    html_content: str = Field(
        description="""Complete article body written in HTML format following the approved outline.
        H2 length must be 5-10 words.
        H3 length must be 5-10 words.
        """,
    )

    # Image Alt Text Suggestions
    images: List[ImageAltText] = Field(
        default=[],
        description="List of SEO-optimized alt text suggestions for images that should be added to the content. Include at least 1 suggestion when possible"
    )

    # Links
    internal_links: List[Link] = Field(
        default=[],
        description="Internal links to other pages on the site. Include at least 1 when possible."
    )
    outbound_links: List[Link] = Field(
        default=[],
        description="Outbound links to authoritative external sources. Include at least 1 when possible."
    )

    # Schema Markup
    schema_markup: SchemaMarkup = Field(
        description="Structured data/schema markup for the article."
    )
    
# class GeneratedContent(BaseModel):
#     """SEO-optimized, human-readable, and natural-sounding article output."""

#     # -------------------
#     # Core Content
#     # -------------------
#     title: str = Field(
#         min_length=10,
#         max_length=70,
#         description="SEO title starting with the keyphrase. Must be engaging and human-like (not robotic)."
#     )

#     slug: str = Field(
#         pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
#         description="Lowercase URL slug with hyphens, includes focus keyphrase."
#     )

#     # -------------------
#     # SEO Meta
#     # -------------------
#     meta_title: str = Field(
#         min_length=50,
#         max_length=60,
#         description="Compelling meta title starting with keyphrase, optimized for CTR."
#     )

#     meta_description: str = Field(
#         min_length=140,
#         max_length=160,
#         description="Engaging, human-like meta description with keyphrase and CTA."
#     )

#     tags: List[str] = Field(
#         min_length=3,
#         max_length=10,
#         description="Relevant SEO tags (3–10 items)."
#     )

#     # -------------------
#     # Keywords
#     # -------------------
#     focus_keyphrase: str = Field(
#         min_length=2,
#         max_length=50,
#         description="Primary keyword (2–4 words preferred)."
#     )

#     keyphrase_density: float = Field(
#         ge=0.5,
#         le=2.5,
#         description="Keep density natural (0.5%–2.5%). Avoid keyword stuffing."
#     )

#     secondary_keywords: List[str] = Field(
#         min_length=2,
#         max_length=15,
#         description="LSI and semantic keywords."
#     )

#     # -------------------
#     # Content Quality
#     # -------------------
#     introduction: str = Field(
#         min_length=150,
#         max_length=800,
#         description="Human-like intro with hook, problem, and value. Must include keyphrase naturally."
#     )

#     body_markdown: str = Field(
#         min_length=800,
#         max_length=60000,
#         description="""
#         Full article in Markdown:
#         - Use H2/H3 headings
#         - Short paragraphs (2–4 lines)
#         - Bullet points where needed
#         - Conversational tone
#         - Avoid AI-like repetition
#         """
#     )

#     html_content: str = Field(
#         description="Clean HTML version of the article. Must match Markdown content."
#     )

#     # -------------------
#     # SEO Enhancements
#     # -------------------
#     images: List["ImageAltText"] = Field(
#         min_length=1,
#         description="At least 1 SEO-optimized alt text including keyword variation."
#     )

#     internal_links: List["Link"] = Field(
#         min_length=1,
#         description="Relevant internal links with natural anchor text."
#     )

#     outbound_links: List["Link"] = Field(
#         min_length=1,
#         description="Links to high-authority sources."
#     )

#     schema_markup: "SchemaMarkup" = Field(
#         description="Valid structured data (Article schema preferred)."
#     )

#     # -------------------
#     # Optional: Humanization Score
#     # -------------------
#     readability_score: float = Field(
#         ge=50,
#         le=100,
#         description="Flesch readability score (higher = easier to read)."
#     )

#     # -------------------
#     # Validators
#     # -------------------
#     @field_validator("title")
#     def title_should_not_be_clickbait(cls, v):
#         banned = ["100%", "guaranteed", "secret"]
#         for word in banned:
#             if word.lower() in v.lower():
#                 raise ValueError("Avoid spammy/clickbait words in title")
#         return v

#     @field_validator("body_markdown")
#     def ensure_headings(cls, v):
#         if "##" not in v:
#             raise ValueError("Content must include subheadings (H2/H3)")
#         return v

    
   
