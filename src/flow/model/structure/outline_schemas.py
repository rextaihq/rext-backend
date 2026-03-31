"""Intent-specific Pydantic schemas for outline generation.

Four schemas share a common base but differ in the extra fields that are
meaningful for each search intent:

- ``InformationalOutline``  — blog, how-to-guide, tutorial, explainer, …
- ``CommercialOutline``     — comparison, best-tools, alternatives, …
- ``NavigationalOutline``   — brand-page, product-homepage, docs, …
- ``TransactionalOutline``  — landing-page, sales-page, pricing-page, …

Use ``get_outline_schema(content_type)`` to get the right class at runtime.
"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field, conlist

from src.flow.model.structure.intent_suggestion import get_intent_for_content_type


# ---------------------------------------------------------------------------
# Shared sub-models (identical across all schemas)
# ---------------------------------------------------------------------------

class ImageSuggestion(BaseModel):
    """Suggested image for a section."""
    description: str = Field(description="What the image should show.")
    alt_text_template: str = Field(description="SEO-optimized alt text template.")
    section: str = Field(description="Section this image belongs to.")


class LinkSuggestion(BaseModel):
    """Suggested internal or outbound link."""
    anchor_text: str = Field(description="Suggested anchor text.")
    link_type: Literal["internal", "outbound"] = Field(description="Link type.")
    context: str = Field(description="What this link points to and why.")
    section: str = Field(description="Section this link should appear in.")


class Section(BaseModel):
    """A single H2 (or H3) section of the outline."""
    heading: str = Field(description="Section heading text.")
    heading_level: Literal["H2", "H3"] = Field(description="Heading level.")
    description: str = Field(description="What this section will cover.")
    key_points: conlist(str, min_length=2, max_length=4)
    questions_to_answer: Optional[List[str]] = Field(
        default=None,
        description="PAA or user questions answered by this section."
    )
    snippet_target: Optional[bool] = False
    search_intent: Literal["informational", "commercial"] = "informational"
    suggested_word_count: Optional[int] = 200
    include_keyphrase_in_heading: bool = Field(
        default=False,
        description="Whether this heading should include the focus keyphrase."
    )


# ---------------------------------------------------------------------------
# 1. INFORMATIONAL — blog, how-to-guide, explainer, pillar-content,
#                    checklist, tutorial, faq, white-paper,
#                    case-study, glossary, resource-list
# ---------------------------------------------------------------------------

class InformationalOutline(BaseModel):
    """Outline for informational content — educates and explains."""

    # Core
    title: str = Field(description="SEO-optimized title starting with the focus keyphrase.")
    slug_suggestion: str = Field(description="URL slug containing the focus keyphrase.")
    brief: str = Field(description="Content goal and value proposition.")
    focus_keyphrase: str = Field(description="Primary focus keyphrase (2-4 words).")
    keywords_to_include: conlist(str, min_length=1)

    # Structure
    sections: conlist(Section, min_length=4, max_length=8)
    faqs: Optional[List[str]] = Field(
        default=None,
        description="FAQ questions for FAQ schema / FAQ section."
    )

    # Informational extras
    prerequisites: Optional[List[str]] = Field(
        default=None,
        description="What the reader needs to know or have before reading (how-to, tutorial)."
    )
    key_takeaways: Optional[List[str]] = Field(
        default=None,
        description="3-5 bullet takeaways for the reader (case-study, white-paper, pillar)."
    )
    table_of_contents: bool = Field(
        default=False,
        description="Whether to include a table of contents (recommended for pillar content)."
    )

    # Media / links
    image_suggestions: List[ImageSuggestion] = Field(min_length=1)
    link_suggestions: List[LinkSuggestion] = Field(min_length=2)

    # Schema & strategy
    schema_type: Literal["Article", "HowTo", "FAQPage", "BlogPosting"] = Field(
        default="Article",
        description="Primary schema.org type."
    )
    target_audience: List[str]
    tone: Literal["Professional", "Conversational", "Authoritative"]
    target_word_count: int = Field(ge=800, le=5000)


# ---------------------------------------------------------------------------
# 2. COMMERCIAL — comparison, best-tools, alternatives, in-depth-review,
#                 pros-cons, product-roundup, buying-guide
# ---------------------------------------------------------------------------

class CommercialOutline(BaseModel):
    """Outline for commercial-investigation content — helps readers decide."""

    # Core
    title: str = Field(description="SEO-optimized title starting with the focus keyphrase.")
    slug_suggestion: str = Field(description="URL slug containing the focus keyphrase.")
    brief: str = Field(description="Content goal and value proposition.")
    focus_keyphrase: str = Field(description="Primary focus keyphrase (2-4 words).")
    keywords_to_include: conlist(str, min_length=1)

    # Structure
    sections: conlist(Section, min_length=4, max_length=8)
    faqs: Optional[List[str]] = Field(
        default=None,
        description="FAQ questions focusing on buyer objections."
    )

    # Commercial extras
    products_covered: List[str] = Field(
        description="Names of all products / tools / options evaluated in this piece."
    )
    evaluation_criteria: List[str] = Field(
        description="Criteria used to compare or evaluate (e.g., pricing, ease of use, support)."
    )
    verdict: str = Field(
        description="One-sentence overall recommendation or winner declaration."
    )
    comparison_table_included: bool = Field(
        default=True,
        description="Whether a comparison table section should be included."
    )

    # Media / links
    image_suggestions: List[ImageSuggestion] = Field(min_length=1)
    link_suggestions: List[LinkSuggestion] = Field(min_length=2)

    # Schema & strategy
    schema_type: Literal["Article", "ItemList", "Review"] = Field(
        default="Article",
        description="Primary schema.org type."
    )
    target_audience: List[str]
    tone: Literal["Professional", "Conversational", "Authoritative"]
    target_word_count: int = Field(ge=800, le=5000)


# ---------------------------------------------------------------------------
# 3. NAVIGATIONAL — brand-page, product-homepage, feature-overview,
#                   documentation, login-guide, contact-us,
#                   about-us, help-center
# ---------------------------------------------------------------------------

class NavigationalOutline(BaseModel):
    """Outline for navigational content — directs users or represents a brand."""

    # Core
    title: str = Field(description="Page title / brand or product name optimised for search.")
    slug_suggestion: str = Field(description="URL slug for this page.")
    brief: str = Field(description="Page purpose and primary user action expected.")
    focus_keyphrase: str = Field(description="Primary focus keyphrase (brand or product term).")
    keywords_to_include: conlist(str, min_length=1)

    # Structure
    sections: conlist(Section, min_length=3, max_length=8)
    faqs: Optional[List[str]] = Field(
        default=None,
        description="Short navigational FAQ answers."
    )

    # Navigational extras
    primary_cta: str = Field(
        description="The single primary call-to-action for this page (e.g., 'Start Free Trial')."
    )
    trust_signals: List[str] = Field(
        description="Trust signals to feature (testimonials, award badges, user counts, etc.)."
    )

    # Media / links
    image_suggestions: List[ImageSuggestion] = Field(min_length=1)
    link_suggestions: List[LinkSuggestion] = Field(min_length=2)

    # Schema & strategy
    schema_type: Literal["WebPage", "WebSite", "AboutPage", "ContactPage"] = Field(
        default="WebPage",
        description="Primary schema.org type."
    )
    target_audience: List[str]
    tone: Literal["Professional", "Conversational", "Authoritative"]
    target_word_count: int = Field(ge=300, le=3000)


# ---------------------------------------------------------------------------
# 4. TRANSACTIONAL — sales-page, pricing-page, signup-page, demo-page,
#                    coupon-page, checkout-page, landing-page, service-page
# ---------------------------------------------------------------------------

class TransactionalOutline(BaseModel):
    """Outline for transactional content — drives an immediate conversion."""

    # Core
    title: str = Field(description="Conversion-optimised headline / page title.")
    slug_suggestion: str = Field(description="URL slug for this page.")
    brief: str = Field(description="Offer description and single conversion goal.")
    focus_keyphrase: str = Field(description="Primary transactional keyphrase.")
    keywords_to_include: conlist(str, min_length=1)

    # Structure
    sections: conlist(Section, min_length=3, max_length=8)
    faqs: Optional[List[str]] = Field(
        default=None,
        description="FAQ questions addressing buyer objections."
    )

    # Transactional extras
    primary_cta: str = Field(
        description="The single primary call-to-action (e.g., 'Get Started Free')."
    )
    objections_addressed: List[str] = Field(
        description="Top buyer objections this page must resolve."
    )
    trust_signals: List[str] = Field(
        description="Trust signals to include (testimonials, guarantees, logos, stats)."
    )
    risk_reversal: str = Field(
        description="Risk-reversal statement (e.g., '30-day money-back guarantee')."
    )
    urgency_element: Optional[str] = Field(
        default=None,
        description="Genuine urgency element if applicable (e.g., limited offer, deadline)."
    )

    # Media / links
    image_suggestions: List[ImageSuggestion] = Field(min_length=1)
    link_suggestions: List[LinkSuggestion] = Field(min_length=2)

    # Schema & strategy
    schema_type: Literal["WebPage", "Product", "Service", "Offer"] = Field(
        default="WebPage",
        description="Primary schema.org type."
    )
    target_audience: List[str]
    tone: Literal["Professional", "Conversational", "Authoritative"]
    target_word_count: int = Field(ge=400, le=4000)


# ---------------------------------------------------------------------------
# Registry & helpers
# ---------------------------------------------------------------------------

_INTENT_TO_SCHEMA = {
    "informational": InformationalOutline,
    "commercial": CommercialOutline,
    "navigational": NavigationalOutline,
    "transactional": TransactionalOutline,
}


def get_outline_schema(content_type: str):
    """Return the Pydantic schema class for a given content_type slug.

    Resolves the parent intent first, then returns the correct schema.
    Falls back to ``InformationalOutline`` for unknown types.
    """
    intent = get_intent_for_content_type(content_type)
    return _INTENT_TO_SCHEMA.get(intent, InformationalOutline)
