# src/config/content_patterns.py

CONTENT_TYPE_TO_PATTERN = {
    # INFORMATIONAL
    "how_to_guide": "educational",
    "tutorial": "educational",
    "explanatory_article": "educational",
    "definition_article": "educational",
    "troubleshooting_guide": "educational",
    "best_practices": "educational",

    # LIST
    "checklist": "list",
    "best_of_list": "list",
    "tool_roundup": "list",

    # COMPARISON
    "product_comparison": "comparison",
    "vs_article": "comparison",
    "alternatives_article": "comparison",
    "pricing_comparison": "comparison",
    "pros_cons_article": "comparison",
    "buying_guide": "comparison",

    # PROOF
    "case_study": "proof",
    "product_review": "proof",

    # CONVERSION
    "landing_page": "conversion",
    "sales_page": "conversion",
    "pricing_page": "conversion",
    "offer_page": "conversion",
    "demo_booking_page": "conversion",

    # NAVIGATIONAL
    "homepage": "navigational",
    "product_page": "navigational",
    "feature_page": "navigational",
    "documentation_page": "navigational",
}