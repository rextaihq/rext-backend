from __future__ import annotations

import re
from typing import Final, Literal

from src.flow.model.structure.intent_suggestion import INTENT_TO_CONTENT_TYPES

# Canonical slugs used across the app (also sent to the frontend).
ContentType = Literal[
    # Informational
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
    "resource-list",
    # Commercial
    "comparison",
    "best-tools",
    "alternatives",
    "in-depth-review",
    "pros-cons",
    "product-roundup",
    "buying-guide",
    # Navigational
    "brand-page",
    "product-homepage",
    "feature-overview",
    "documentation",
    "login-guide",
    "contact-us",
    "about-us",
    "help-center",
    # Transactional
    "sales-page",
    "pricing-page",
    "signup-page",
    "demo-page",
    "coupon-page",
    "checkout-page",
    "landing-page",
    "service-page",
]


VALID_CONTENT_TYPES: Final[frozenset[str]] = frozenset(
    ct for lst in INTENT_TO_CONTENT_TYPES.values() for ct in lst
)

_ALIASES: Final[dict[str, str]] = {
    # Historical / generic aliases.
    "article": "blog",
    "blog-post": "blog",
    "blogpost": "blog",
    # Common separator variants.
    "howto-guide": "how-to-guide",
    "in-depthreview": "in-depth-review",
}


def normalize_content_type(value: str | None) -> str:
    """Return a canonical content type slug or raise ValueError."""
    if not value:
        raise ValueError("content_type is missing")

    v = str(value).strip().lower()
    v = v.replace("_", "-").replace(" ", "-")
    v = re.sub(r"-{2,}", "-", v).strip("-")
    v = _ALIASES.get(v, v)

    if v not in VALID_CONTENT_TYPES:
        valid = ", ".join(sorted(VALID_CONTENT_TYPES))
        raise ValueError(f"Unknown content_type={value!r}. Valid values: {valid}")

    return v

