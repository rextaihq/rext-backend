from __future__ import annotations

import re

from src.flow.model.structure.intent_suggestion import INTENT_TO_CONTENT_TYPES

_ALIASES: dict[str, str] = {
    # Common spacing/punctuation variants
    "how to guide": "how-to-guide",
    "how-to guide": "how-to-guide",
    "how_to_guide": "how-to-guide",
    "howto guide": "how-to-guide",
    "howto": "how-to-guide",
    "landing page": "landing-page",
    "landingpage": "landing-page",
    "product comparison": "comparison",
    "compare": "comparison",
    "comarision": "comparison",
    "comparision": "comparison",
    "review": "in-depth-review",
    "article": "blog",
    "blog post": "blog",
    "blogpost": "blog",
}

_ALLOWED_CONTENT_TYPES: set[str] = {
    ct for types in INTENT_TO_CONTENT_TYPES.values() for ct in types
}


def normalize_content_type_slug(raw: str | None) -> str:
    """Normalize human / UI / model content-type strings to canonical kebab-case slugs."""
    if not raw:
        return ""

    s = str(raw).strip().lower()
    if not s:
        return ""

    if s in _ALIASES:
        candidate = _ALIASES[s]
        return candidate if candidate in _ALLOWED_CONTENT_TYPES else ""

    # Turn separators into hyphens
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"[^a-z0-9-]+", "", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")

    candidate = _ALIASES.get(s, s)
    return candidate if candidate in _ALLOWED_CONTENT_TYPES else ""
