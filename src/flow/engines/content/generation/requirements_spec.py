"""Builds a normalized RequirementsSpec from the approved outline.

Content types have materially different outline schemas (a landing-page
outline stores hero/problem/solution/benefits as nested dicts; a blog outline
stores a flat `sections` list) — this module is the one place that knows how
to map any of them to "what must appear in the final article," so the check
functions in validation.py stay generic.
"""

from __future__ import annotations

from typing import Optional, TypedDict

from src.flow.engines.content.generation.brand_placement_policy import (
    BrandPlacementPolicy,
    resolve_brand_placement_policy,
)
from src.flow.engines.content.generation.evidence_placement_policy import (
    EvidencePlacementPolicy,
    resolve_evidence_placement_policy,
)
from src.flow.engines.content.generation.outline_structure import (
    resolve_expected_headings,
    resolve_outline_structure,
    resolve_required_headings,
)


class RequirementsSpec(TypedDict, total=False):
    target_keyword: str
    expected_sections: list[str]
    # Subset of expected_sections whose schema field is non-Optional. A missing
    # one blocks regardless of overall coverage — a flat percentage cannot tell
    # "optional FAQ absent" from "no Solution section at all".
    required_sections: list[str]
    hero_context: Optional[dict]  # approved hero copy, verified by content not label
    hero_required: bool  # blocking for prefers_top types, warning otherwise
    approved_internal_links: list[dict]
    brand_context: Optional[dict]
    sourced_facts: list[dict]
    target_word_count: int
    cta_required: bool
    outline_cta: Optional[dict]
    brand_placement: (
        str  # "hero" | "body_only" — coarse signal, derived from brand_placement_policy
    )
    brand_placement_policy: BrandPlacementPolicy  # full per-content-type PLM policy
    evidence_placement: EvidencePlacementPolicy  # per-content-type citation-style policy


# CTA field-name patterns actually used across the outline Pydantic models
# (src/flow/model/structure/outlines/**), checked in priority order. Most
# informational types have none of these and correctly resolve to no CTA
# requirement. (container_key, field_key) — field_key=None means the
# container itself is expected to be a plain string.
_CTA_FIELD_PATHS: tuple[tuple[str, Optional[str]], ...] = (
    ("final_cta", "primary_cta"),
    ("cta", "primary_cta"),
    ("cta", None),
    ("hero", "primary_cta"),
    ("offer", "primary_cta"),
)


def resolve_outline_cta(outline: dict) -> Optional[dict]:
    """Best-effort extraction of the outline's declared CTA, across schemas.

    Not every content type has a CTA — this only fires when the outline
    itself declares one, so the requirement is driven by what was actually
    approved for this specific article rather than a hardcoded content-type
    list.
    """
    for container_key, field_key in _CTA_FIELD_PATHS:
        container = outline.get(container_key)
        if isinstance(container, dict) and field_key:
            text = container.get(field_key)
            if isinstance(text, str) and text.strip():
                return {"text": text.strip(), "source": f"{container_key}.{field_key}"}
        elif isinstance(container, str) and field_key is None and container.strip():
            return {"text": container.strip(), "source": container_key}
    return None


def _extract_brand_context(outline: dict) -> Optional[dict]:
    if not outline.get("promote_brand"):
        return None
    promo = outline.get("brand_voice_promotion") or {}
    brand_name = (promo.get("brand_name") or "").strip()
    if not brand_name:
        return None
    return {
        "brand_name": brand_name,
        "brand_url": (promo.get("brand_url") or "").strip(),
        "about": promo.get("about") or "",
        "selling_position": promo.get("selling_position") or "",
    }


def _expected_sections(outline: dict, content_type: str) -> list[str]:
    """Section/heading labels the approved outline expects.

    Derived from the SAME resolver the generation prompt is built from
    (outline_structure.py), so what the model is told to write and what
    validation checks for cannot drift apart — that drift is what let a
    landing page ship with no hero section and no one notice.

    Previously this read `normalize_outline()`'s blocks, which is a
    display-oriented projection: it dropped `hero`/`social_proof` for every
    page type, and for informational types it collapsed the real per-section
    headings into the single literal label "Structure" — a heading no article
    ever contains, so blog section validation was matching a phantom.
    """
    return resolve_expected_headings(resolve_outline_structure(outline, content_type))


def _hero_context(outline: dict) -> Optional[dict]:
    """The approved hero's own copy, for verifying it survived into the article.

    `hero` is deliberately excluded from expected_sections — an article never
    contains a literal "## Hero" heading, so requiring that label would fail
    every article. The consequence was that a missing hero became structurally
    invisible: the model could drop the block entirely and no check could see
    it. Verifying the hero's TEXT instead of its label closes that hole without
    reintroducing the phantom-heading problem.
    """
    hero = outline.get("hero")
    if not isinstance(hero, dict):
        return None
    headline = (hero.get("headline") or "").strip()
    subheadline = (hero.get("subheadline") or "").strip()
    if not headline and not subheadline:
        return None
    return {"headline": headline, "subheadline": subheadline}


def build_requirements_spec(outline: dict, content_type: str) -> RequirementsSpec:
    outline = outline or {}
    keywords_to_include = outline.get("keywords_to_include") or []
    focus_keyphrase = outline.get("focus_keyphrase") or (
        keywords_to_include[0] if keywords_to_include else ""
    )
    outline_cta = resolve_outline_cta(outline)
    placement_policy = resolve_brand_placement_policy(content_type)
    blocks = resolve_outline_structure(outline, content_type)

    return RequirementsSpec(
        target_keyword=focus_keyphrase,
        expected_sections=resolve_expected_headings(blocks),
        required_sections=resolve_required_headings(blocks),
        hero_context=_hero_context(outline),
        hero_required=placement_policy["prefers_top"],
        approved_internal_links=outline.get("internal_links") or [],
        brand_context=_extract_brand_context(outline),
        sourced_facts=outline.get("key_facts") or [],
        target_word_count=outline.get("target_word_count") or 0,
        cta_required=outline_cta is not None,
        outline_cta=outline_cta,
        brand_placement="hero" if placement_policy["prefers_top"] else "body_only",
        brand_placement_policy=placement_policy,
        evidence_placement=resolve_evidence_placement_policy(content_type),
    )
