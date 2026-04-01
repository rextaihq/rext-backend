from typing import Dict


DEFAULT_PATTERN = "educational"

CONTENT_TYPE_TO_PATTERN: Dict[str, str] = {
    # Informational
    "article": "educational",
    "blog": "educational",
    "how_to_guide": "educational",
    "how-to-guide": "educational",
    "tutorial": "educational",
    "explanatory_article": "educational",
    "definition_article": "educational",
    "troubleshooting_guide": "educational",
    "best_practices": "educational",
    "explainer": "educational",
    "faq": "educational",
    "pillar-content": "educational",
    "white-paper": "educational",
    "glossary": "educational",
    "resource-list": "educational",

    # List
    "checklist": "list",
    "best_of_list": "list",
    "tool_roundup": "list",
    "best-tools": "list",
    "product-roundup": "list",

    # Comparison / Commercial
    "comparison": "comparison",
    "product_comparison": "comparison",
    "vs_article": "comparison",
    "alternatives_article": "comparison",
    "pricing_comparison": "comparison",
    "pros_cons_article": "comparison",
    "buying_guide": "comparison",
    "alternatives": "comparison",
    "in-depth-review": "comparison",
    "pros-cons": "comparison",
    "buying-guide": "comparison",

    # Proof
    "case_study": "proof",
    "case-study": "proof",
    "product_review": "proof",

    # Conversion
    "landing_page": "conversion",
    "landing-page": "conversion",
    "sales_page": "conversion",
    "sales-page": "conversion",
    "pricing_page": "conversion",
    "pricing-page": "conversion",
    "offer_page": "conversion",
    "demo_booking_page": "conversion",
    "signup-page": "conversion",
    "demo-page": "conversion",
    "coupon-page": "conversion",
    "checkout-page": "conversion",
    "service-page": "conversion",

    # Navigational
    "homepage": "navigational",
    "product_page": "navigational",
    "feature_page": "navigational",
    "documentation_page": "navigational",
    "brand-page": "navigational",
    "product-homepage": "navigational",
    "feature-overview": "navigational",
    "documentation": "navigational",
    "login-guide": "navigational",
    "contact-us": "navigational",
    "about-us": "navigational",
    "help-center": "navigational",
}


def resolve_pattern(content_type: str) -> str:
    normalized = (content_type or "").strip().lower()
    if normalized in CONTENT_TYPE_TO_PATTERN:
        return CONTENT_TYPE_TO_PATTERN[normalized]

    normalized_underscore = normalized.replace("-", "_")
    if normalized_underscore in CONTENT_TYPE_TO_PATTERN:
        return CONTENT_TYPE_TO_PATTERN[normalized_underscore]

    return DEFAULT_PATTERN
