"""Resolve the schema.org types an article's JSON-LD should declare.

Why this is its own module
--------------------------
`GeneratedContent.schema_markup.schema_type` defaulted to the literal string
`"Article"` for all 34 content types, and the outline's own `schema_type` field
is overwritten by `generate_outline` with a *display name* (`"Blog"`,
`"How To Guide"`) which is not a schema.org type at all. So the writer model was
choosing JSON-LD types unguided, and a how-to shipped as `Article` instead of
`HowTo`, losing the rich result it qualifies for.

Content type -> schema.org type is a stable, declarative mapping with no
dependency on generation, validation, or persistence, so it lives on its own
rather than inside a 1000-line generation module.
"""

from __future__ import annotations

from src.flow.model.structure.outlines import normalize_content_type

# Primary schema.org @type per content type. Values are real schema.org types
# (https://schema.org/docs/full.html) — not display names.
_PRIMARY_TYPE: dict[str, str] = {
    # Informational
    "blog": "BlogPosting",
    "how-to-guide": "HowTo",
    "tutorial": "HowTo",
    "checklist": "HowTo",
    "explainer": "Article",
    "pillar-content": "Article",
    "faq": "FAQPage",
    "white-paper": "Report",
    "case-study": "Article",
    "glossary": "DefinedTermSet",
    "resource-list": "ItemList",
    # Commercial
    "comparison": "Article",
    "best-tools": "ItemList",
    "alternatives": "ItemList",
    "in-depth-review": "Review",
    "pros-cons": "Review",
    "product-roundup": "ItemList",
    "buying-guide": "Article",
    # Navigational
    "brand-page": "AboutPage",
    "product-homepage": "WebPage",
    "feature-overview": "WebPage",
    "documentation": "TechArticle",
    "login-guide": "TechArticle",
    "contact-us": "ContactPage",
    "about-us": "AboutPage",
    "help-center": "WebPage",
    # Transactional
    "sales-page": "WebPage",
    "pricing-page": "WebPage",
    "signup-page": "WebPage",
    "demo-page": "WebPage",
    "coupon-page": "WebPage",
    "checkout-page": "CheckoutPage",
    "landing-page": "WebPage",
    "service-page": "Service",
}

_DEFAULT_TYPE = "Article"


def resolve_primary_schema_type(content_type: str) -> str:
    """The main schema.org @type for this content type."""
    return _PRIMARY_TYPE.get(normalize_content_type(content_type), _DEFAULT_TYPE)


def resolve_schema_types(outline: dict, content_type: str) -> list[str]:
    """Every schema.org @type this article should emit, primary first.

    A page can legitimately qualify for more than one. The common case is an
    article that also carries a real FAQ block: Google reads `FAQPage` from the
    same document, so both belong in the JSON-LD graph. `FAQPage` is only added
    when the approved outline actually has questions — emitting it for an
    article with no FAQ section is structured-data spam and risks a manual
    action.
    """
    from src.flow.model.structure.outlines.render import extract_outline_faqs

    primary = resolve_primary_schema_type(content_type)
    types = [primary]

    if primary != "FAQPage" and extract_outline_faqs(outline or {}):
        types.append("FAQPage")

    return types


def format_schema_guidance_for_prompt(outline: dict, content_type: str) -> str:
    """Prompt text telling the writer exactly which JSON-LD types to emit."""
    types = resolve_schema_types(outline, content_type)
    primary = types[0]

    lines = [
        "========================",
        "STRUCTURED DATA (JSON-LD)",
        "========================",
        f"Set `schema_markup.schema_type` to exactly: {primary}",
    ]
    if len(types) > 1:
        secondary = ", ".join(types[1:])
        lines.append(
            f"The article also qualifies for: {secondary}. Emit a JSON-LD @graph "
            f"containing {primary} plus {secondary}, so both are machine-readable "
            f"from one block."
        )
    lines.append(
        "Populate `schema_markup.schema_data` with valid JSON-LD as a JSON string. "
        "Every field in it must reflect content that actually appears in the "
        "article — never mark up claims, ratings, or questions the body does not contain."
    )
    return "\n".join(lines)


__all__ = [
    "resolve_primary_schema_type",
    "resolve_schema_types",
    "format_schema_guidance_for_prompt",
]
