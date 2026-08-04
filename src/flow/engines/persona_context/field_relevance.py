"""Content-type field-relevance weighting for Persona/Brand context.

Mirrors the pattern already proven in ``src/flow/image_generation/content_type_mapper.py``:
score how relevant each AuthorPersona/Brand/BrandVoice/Audience field is per
content type, then project only the relevant fields into the generation
prompt instead of dumping every field into every article regardless of
content type (the gap identified in the persona/brand-voice redesign).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Optional


class FieldRelevance(IntEnum):
    UNUSED = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    VERY_HIGH = 4


# ---------------------------------------------------------------------------
# Content-type -> search-intent group
# ---------------------------------------------------------------------------

INFORMATIONAL_TYPES = {
    "blog", "how-to-guide", "explainer", "pillar-content", "checklist",
    "tutorial", "faq", "white-paper", "case-study", "glossary", "resource-list",
}
COMMERCIAL_TYPES = {
    "comparison", "best-tools", "alternatives", "in-depth-review",
    "pros-cons", "product-roundup", "buying-guide",
}
NAVIGATIONAL_TYPES = {
    "brand-page", "product-homepage", "feature-overview", "documentation",
    "login-guide", "contact-us", "about-us", "help-center",
}
TRANSACTIONAL_TYPES = {
    "sales-page", "pricing-page", "signup-page", "demo-page",
    "coupon-page", "checkout-page", "landing-page", "service-page",
}


def _normalize(content_type: str) -> str:
    return (content_type or "").strip().lower().replace("_", "-").replace(" ", "-")


def intent_group(content_type: str) -> str:
    """Return one of informational | commercial | navigational | transactional."""
    normalized = _normalize(content_type)
    if normalized in COMMERCIAL_TYPES:
        return "commercial"
    if normalized in NAVIGATIONAL_TYPES:
        return "navigational"
    if normalized in TRANSACTIONAL_TYPES:
        return "transactional"
    return "informational"


# ---------------------------------------------------------------------------
# Group-level defaults (Phase 6 matrix)
# ---------------------------------------------------------------------------

_VH, _H, _M, _L, _U = (
    FieldRelevance.VERY_HIGH, FieldRelevance.HIGH, FieldRelevance.MEDIUM,
    FieldRelevance.LOW, FieldRelevance.UNUSED,
)

AUTHOR_PERSONA_RELEVANCE: dict[str, dict[str, FieldRelevance]] = {
    "informational": {
        "full_name": _H, "professional_title": _H, "areas_of_expertise": _VH,
        "experience_type": _H, "credentials": _H, "years_of_experience": _H,
        "employer": _M, "bio": _H, "social_profiles": _H,
        "writing_voice": _VH, "avatar_url": _M,
    },
    "commercial": {
        "full_name": _M, "professional_title": _M, "areas_of_expertise": _H,
        "experience_type": _M, "credentials": _M, "years_of_experience": _M,
        "employer": _L, "bio": _M, "social_profiles": _M,
        "writing_voice": _VH, "avatar_url": _L,
    },
    "navigational": {
        "full_name": _L, "professional_title": _L, "areas_of_expertise": _L,
        "experience_type": _L, "credentials": _L, "years_of_experience": _L,
        "employer": _L, "bio": _M, "social_profiles": _M,
        "writing_voice": _H, "avatar_url": _M,
    },
    "transactional": {
        "full_name": _L, "professional_title": _L, "areas_of_expertise": _U,
        "experience_type": _U, "credentials": _U, "years_of_experience": _U,
        "employer": _U, "bio": _U, "social_profiles": _U,
        "writing_voice": _H, "avatar_url": _U,
    },
}

# Per-content-type overrides — win over the group default for listed fields only.
AUTHOR_PERSONA_OVERRIDES: dict[str, dict[str, FieldRelevance]] = {
    "case-study": {k: _VH for k in AUTHOR_PERSONA_RELEVANCE["informational"]},
    "white-paper": {k: _VH for k in AUTHOR_PERSONA_RELEVANCE["informational"]},
    "about-us": {"bio": _VH, "social_profiles": _VH, "avatar_url": _VH, "full_name": _VH},
    **{
        ct: {k: _U for k in AUTHOR_PERSONA_RELEVANCE["informational"]}
        for ct in ("faq", "checklist", "checkout-page", "login-guide", "coupon-page")
    },
}

BRAND_RELEVANCE: dict[str, dict[str, FieldRelevance]] = {
    "informational": {
        "about": _M, "customer_profile": _L, "selling_position": _L,
        "competitors": _L, "content_pillar": _H, "target_audience_summary": _M,
    },
    "commercial": {
        "about": _M, "customer_profile": _M, "selling_position": _H,
        "competitors": _VH, "content_pillar": _M, "target_audience_summary": _H,
    },
    "navigational": {
        "about": _H, "customer_profile": _L, "selling_position": _M,
        "competitors": _U, "content_pillar": _L, "target_audience_summary": _L,
    },
    "transactional": {
        "about": _M, "customer_profile": _H, "selling_position": _VH,
        "competitors": _M, "content_pillar": _U, "target_audience_summary": _H,
    },
}

BRAND_OVERRIDES: dict[str, dict[str, FieldRelevance]] = {
    "comparison": {"competitors": _VH}, "alternatives": {"competitors": _VH},
    "best-tools": {"competitors": _VH}, "pros-cons": {"competitors": _VH},
    "brand-page": {"about": _VH, "selling_position": _VH},
    "product-homepage": {"about": _VH, "selling_position": _VH},
    **{
        ct: {k: _L for k in BRAND_RELEVANCE["informational"]}
        for ct in ("documentation", "help-center", "login-guide")
    },
}

# Voice fields are intentionally near-universal — Very High everywhere, with
# two documented exceptions (cta_style / humor_tolerance).
BRAND_VOICE_RELEVANCE: dict[str, dict[str, FieldRelevance]] = {
    group: {
        "tone_attributes": _VH, "formality_level": _VH, "reading_level": _H,
        "point_of_view": _H, "sentence_length_preference": _M,
        "preferred_terms": _VH, "banned_terms": _VH,
        "humor_tolerance": _M, "cta_style": (_VH if group == "transactional" else (_L if group == "informational" else _M)),
    }
    for group in ("informational", "commercial", "navigational", "transactional")
}

BRAND_VOICE_OVERRIDES: dict[str, dict[str, FieldRelevance]] = {
    ct: {"cta_style": _U} for ct in ("documentation", "faq", "glossary", "help-center")
} | {
    ct: {"humor_tolerance": _L} for ct in ("legal", "documentation", "checkout-page")
}

AUDIENCE_RELEVANCE: dict[str, dict[str, FieldRelevance]] = {
    "informational": {
        "demographics": _M, "psychographics": _L, "pain_points": _H,
        "goals": _H, "behaviors": _M, "objections": _L, "buying_stage": _U,
    },
    "commercial": {
        "demographics": _H, "psychographics": _VH, "pain_points": _VH,
        "goals": _H, "behaviors": _M, "objections": _VH, "buying_stage": _H,
    },
    "navigational": {
        "demographics": _L, "psychographics": _U, "pain_points": _L,
        "goals": _L, "behaviors": _U, "objections": _U, "buying_stage": _U,
    },
    "transactional": {
        "demographics": _H, "psychographics": _VH, "pain_points": _H,
        "goals": _M, "behaviors": _H, "objections": _VH, "buying_stage": _VH,
    },
}


def _resolve(
    group_table: dict[str, dict[str, FieldRelevance]],
    override_table: dict[str, dict[str, FieldRelevance]],
    content_type: str,
) -> dict[str, FieldRelevance]:
    normalized = _normalize(content_type)
    resolved = dict(group_table[intent_group(content_type)])
    resolved.update(override_table.get(normalized, {}))
    return resolved


def resolve_author_persona_relevance(content_type: str) -> dict[str, FieldRelevance]:
    return _resolve(AUTHOR_PERSONA_RELEVANCE, AUTHOR_PERSONA_OVERRIDES, content_type)


def resolve_brand_relevance(content_type: str) -> dict[str, FieldRelevance]:
    return _resolve(BRAND_RELEVANCE, BRAND_OVERRIDES, content_type)


def resolve_brand_voice_relevance(content_type: str) -> dict[str, FieldRelevance]:
    return _resolve(BRAND_VOICE_RELEVANCE, BRAND_VOICE_OVERRIDES, content_type)


def resolve_audience_relevance(content_type: str) -> dict[str, FieldRelevance]:
    return dict(AUDIENCE_RELEVANCE[intent_group(content_type)])


# ---------------------------------------------------------------------------
# Projection
# ---------------------------------------------------------------------------

@dataclass
class ContentPersonaContext:
    """Only the fields relevant to this content type, ready to render into a prompt."""

    author_persona_fields: dict[str, Any] = field(default_factory=dict)
    brand_fields: dict[str, Any] = field(default_factory=dict)
    brand_voice_fields: dict[str, Any] = field(default_factory=dict)
    audience_fields: dict[str, Any] = field(default_factory=dict)


def _project(entity: Any, relevance: dict[str, FieldRelevance], min_relevance: FieldRelevance) -> dict[str, Any]:
    if entity is None:
        return {}
    projected: dict[str, Any] = {}
    for field_name, score in relevance.items():
        if score < min_relevance:
            continue
        value = getattr(entity, field_name, None)
        if value in (None, "", [], {}):
            continue
        projected[field_name] = value
    return projected


def build_content_context(
    content_type: str,
    *,
    brand: Optional[Any] = None,
    brand_voice: Optional[Any] = None,
    author_persona: Optional[Any] = None,
    audience: Optional[Any] = None,
    min_relevance: FieldRelevance = FieldRelevance.MEDIUM,
) -> ContentPersonaContext:
    """Project Brand/BrandVoice/AuthorPersona/Audience down to the fields
    that matter for this content type (Medium+ relevance by default).

    Voice fields (tone/formality/vocabulary) stay Very-High/High relevance
    for virtually every content type by design — this is what closes the
    gap where BrandVoice was never read during content generation at all.
    """
    return ContentPersonaContext(
        author_persona_fields=_project(author_persona, resolve_author_persona_relevance(content_type), min_relevance),
        brand_fields=_project(brand, resolve_brand_relevance(content_type), min_relevance),
        brand_voice_fields=_project(brand_voice, resolve_brand_voice_relevance(content_type), min_relevance),
        audience_fields=_project(audience, resolve_audience_relevance(content_type), min_relevance),
    )
