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
    apply_brand_prominence,
    resolve_brand_placement_policy,
)
from src.flow.engines.content.generation.claim_integrity import (
    ClaimEvidence,
    build_claim_evidence,
)
from src.flow.engines.content.generation.evidence_placement_policy import (
    EvidencePlacementPolicy,
    resolve_evidence_placement_policy,
)
from src.flow.engines.content.generation.focus_keyword import (
    focus_keyword_from_outline,
    normalize_focus_keyword,
)
from src.flow.engines.content.generation.outline_structure import (
    resolve_expected_headings,
    resolve_outline_structure,
    resolve_required_headings,
)


class RequirementsSpec(TypedDict, total=False):
    # The user's own query, pinned onto the outline by generate_outline. Never a
    # model-invented substitute -- see focus_keyword.py.
    target_keyword: str
    # Explicit synonyms of the focus keyphrase, credited by the subheading
    # keyphrase check the way Yoast Premium credits its synonyms field. Read
    # from the outline's optional `keyphrase_synonyms`; empty unless something
    # upstream supplies them — never model-guessed here.
    keyphrase_synonyms: list[str]
    # The EXACT title the user selected at the topic-selection interrupt.
    # Read-only from that moment on: topic_generation is the only stage allowed
    # to repair a title, so every later stage compares against this and reverts
    # drift rather than re-optimizing. Empty only for runs that predate the
    # selection step.
    selected_title: str
    # Content type is needed by checks that resolve a per-type policy (keyword
    # density resolves a content-family modifier), so it travels with the spec
    # rather than being re-threaded through every check signature.
    content_type: str
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
    # Ground truth a factual claim in the article may rest on (search results,
    # approved brand info, author profile, outline entity names). Same for every
    # content type — see claim_integrity.py.
    claim_evidence: ClaimEvidence
    # Protected inline links the article has carried at any accepted stage
    # (see link_integrity.py / validation.protected_links). Recorded in
    # generation_meta by the nodes that rewrite prose, so a later stage can tell
    # "a valid link was removed" apart from "the link was never there".
    link_inventory: list[dict]


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


def build_requirements_spec(
    outline: dict,
    content_type: str,
    focus_keyword: str = "",
    selected_title: str = "",
    generation_meta: Optional[dict] = None,
) -> RequirementsSpec:
    """Normalize the approved outline into "what must appear in the article".

    `focus_keyword` overrides whatever the outline carries. generate_outline
    already pins the user's keyword onto the outline, so the two normally agree
    and the argument can be omitted; it exists for call sites that hold graph
    state (and therefore the authoritative keyword) but may be operating on an
    outline produced before pinning existed.

    `selected_title` is the user's locked title. It falls back to the outline's
    own `title`, which generate_outline stamps with the selected topic, so the
    two normally agree; passing it explicitly matters for call sites that hold
    graph state and can therefore see the selection directly.

    `generation_meta` is the writer run's captured ground truth (real search
    results, the author profile). Call sites that grade factual claims pass it;
    without it every price/statistic is treated as unverified, which is the safe
    direction to fail in.
    """
    outline = outline or {}
    keywords_to_include = outline.get("keywords_to_include") or []
    focus_keyphrase = (
        normalize_focus_keyword(focus_keyword)
        or focus_keyword_from_outline(outline)
        or (keywords_to_include[0] if keywords_to_include else "")
    )
    outline_cta = resolve_outline_cta(outline)
    # The content type's policy decides whether a hero is required; the
    # article's policy (at the brand prominence the user chose) decides where
    # the brand goes. A subtle mention on a landing page still needs its hero.
    type_policy = resolve_brand_placement_policy(content_type)
    placement_policy = apply_brand_prominence(type_policy, outline.get("brand_prominence"))
    blocks = resolve_outline_structure(outline, content_type)
    brand_context = _extract_brand_context(outline)

    return RequirementsSpec(
        target_keyword=focus_keyphrase,
        keyphrase_synonyms=[
            normalize_focus_keyword(s)
            for s in (outline.get("keyphrase_synonyms") or [])
            if normalize_focus_keyword(s)
        ],
        selected_title=selected_title or outline.get("title") or "",
        content_type=content_type or "",
        expected_sections=resolve_expected_headings(blocks),
        required_sections=resolve_required_headings(blocks),
        hero_context=_hero_context(outline),
        hero_required=type_policy["prefers_top"],
        approved_internal_links=outline.get("internal_links") or [],
        brand_context=brand_context,
        sourced_facts=outline.get("key_facts") or [],
        target_word_count=outline.get("target_word_count") or 0,
        cta_required=outline_cta is not None,
        outline_cta=outline_cta,
        brand_placement="hero" if placement_policy["prefers_top"] else "body_only",
        brand_placement_policy=placement_policy,
        evidence_placement=resolve_evidence_placement_policy(content_type),
        claim_evidence=build_claim_evidence(
            outline=outline,
            brand_context=brand_context,
            generation_meta=generation_meta,
        ),
        link_inventory=list((generation_meta or {}).get("link_inventory") or []),
    )
