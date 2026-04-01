INTENT_TO_CONTENT_TYPES = {
    "informational": [
        "how_to_guide",
        "tutorial",
        "explanatory_article",
        "definition_article",
        "faq_page",
        "troubleshooting_guide",
        "checklist",
        "best_practices",
        "case_study"
    ],
    
    "commercial": [
        "product_comparison",
        "vs_article",
        "best_of_list",
        "product_review",
        "alternatives_article",
        "pros_cons_article",
        "tool_roundup",
        "buying_guide",
        "pricing_comparison"
    ],
    
    "navigational": [
        "homepage",
        "brand_page",
        "product_page",
        "feature_page",
        "documentation_page",
        "support_page",
        "contact_page",
        "about_page",
        "login_page",
        "signup_page"
    ],
    
    "transactional": [
        "sales_page",
        "landing_page",
        "pricing_page",
        "checkout_page",
        "order_page",
        "subscription_page",
        "demo_booking_page",
        "quote_request_page",
        "download_page",
        "offer_page"
    ]
}

# Reverse lookup: content_type slug -> parent intent group
CONTENT_TYPE_TO_INTENT: dict[str, str] = {
    ct: intent
    for intent, types in INTENT_TO_CONTENT_TYPES.items()
    for ct in types
}


def get_intent_for_content_type(content_type: str) -> str:
    """Return the parent intent for a content_type slug.

    Falls back to ``'informational'`` for unknown types.
    """
    return CONTENT_TYPE_TO_INTENT.get(content_type, "informational")
