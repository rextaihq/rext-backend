INTENT_TO_CONTENT_TYPES ={
    "informational": [
        "blog",
        "how-to-guide",
        "explainer",
        "pillar-content",
        "checklist",
        "tutorial",
        "faq",
        "white-paper",
        "case-study",
        "glossary",
        "resource-list"
    ],
    "commercial": [
        "comparison",
        "best-tools",
        "alternatives",
        "in-depth-review",
        "pros-cons",
        "product-roundup",
        "buying-guide"
    ],
    "navigational": [
        "brand-page",
        "product-homepage",
        "feature-overview",
        "documentation",
        "login-guide",
        "contact-us",
        "about-us",
        "help-center"
    ],
    "transactional": [
        "sales-page",
        "pricing-page",
        "signup-page",
        "demo-page",
        "coupon-page",
        "checkout-page",
        "landing-page",
        "service-page"
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
    return CONTENT_TYPE_TO_INTENT.get(content_type, "")
