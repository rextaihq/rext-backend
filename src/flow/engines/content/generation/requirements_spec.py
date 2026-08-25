"""Builds a normalized RequirementsSpec from the approved outline.

Content types have materially different outline schemas (a landing-page
outline stores hero/problem/solution/benefits as nested dicts; a blog outline
stores a flat `sections` list) — this module is the one place that knows how
to map any of them to "what must appear in the final article," so the check
functions in validation.py stay generic.
"""

from __future__ import annotations

from typing import Any, Optional, TypedDict

from src.flow.engines.content.generation.brand_placement_policy import (
    BrandPlacementPolicy,
    resolve_brand_placement_policy,
)
from src.flow.engines.content.generation.evidence_placement_policy import (
    EvidencePlacementPolicy,
    resolve_evidence_placement_policy,
)
from src.flow.model.structure.outlines.render import normalize_outline


class RequirementsSpec(TypedDict, total=False):
    target_keyword: str
    expected_sections: list[str]
    approved_internal_links: list[dict]
    brand_context: Optional[dict]
    sourced_facts: list[dict]
    target_word_count: int
    cta_required: bool
    outline_cta: Optional[dict]
    brand_placement: str  # "hero" | "body_only" — coarse signal, derived from brand_placement_policy
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

    Two-tier: prefer genuine per-section headings when the schema has them
    (informational types — each SectionState has its own `heading`, intended
    to become an actual H2). Schemas with no flat `sections` list (most
    commercial/transactional/navigational types) fall back to the
    already-computed structural-block headings from `normalize_outline()`
    (src/flow/model/structure/outlines/render.py) — e.g. "Problem",
    "Solution", "Benefits" for a landing page — reusing its existing
    per-content-type dispatch rather than re-deriving it here.
    """
    sections = (
        outline.get("sections")
        or (outline.get("content_structure") or {}).get("sections")
        or (outline.get("_render") or {}).get("sections")
        or []
    )
    headings = [s.get("heading") for s in sections if isinstance(s, dict) and s.get("heading")]
    if headings:
        return headings

    render = outline.get("_render")
    if not isinstance(render, dict):
        render = normalize_outline(outline, content_type)
    return [block.get("heading") for block in (render.get("blocks") or []) if block.get("heading")]


def build_requirements_spec(outline: dict, content_type: str) -> RequirementsSpec:
    outline = outline or {}
    keywords_to_include = outline.get("keywords_to_include") or []
    focus_keyphrase = outline.get("focus_keyphrase") or (
        keywords_to_include[0] if keywords_to_include else ""
    )
    outline_cta = resolve_outline_cta(outline)
    placement_policy = resolve_brand_placement_policy(content_type)

    return RequirementsSpec(
        target_keyword=focus_keyphrase,
        expected_sections=_expected_sections(outline, content_type),
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
