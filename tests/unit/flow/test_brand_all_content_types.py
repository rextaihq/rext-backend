"""Brand-promotion coverage across every content type in the registry.

Parametrized over `CONTENT_TYPE_TO_MODEL` rather than a hand-written list, so a
newly added content type is covered the moment it is registered — the same
"derive, don't duplicate" rule the generation pipeline itself follows.

Outlines are synthesized from each type's own Pydantic outline schema, so these
tests exercise the real field names each schema declares instead of a fixture
that happens to look like a blog.
"""

import typing
from typing import Literal, Union, get_args, get_origin

import pytest
from pydantic import BaseModel

from src.flow.engines.content.generation.brand_placement_policy import BRAND_PLACEMENT_POLICY
from src.flow.engines.content.generation.brand_slot import (
    SLOT_BLOCK_KEYS,
    apply_brand_slot_to_outline,
)
from src.flow.engines.content.generation.structured_body import build_structured_content_model
from src.flow.model.structure.contents import get_generated_content_model
from src.flow.model.structure.outlines import CONTENT_TYPE_TO_MODEL, normalize_content_type

BRAND = "Acme"
_PROMO = {
    "brand_name": BRAND,
    "brand_url": "https://acme.io",
    "about": "Onboarding automation for support teams",
    "selling_position": "Halves new-hire ramp time",
}

ALL_CONTENT_TYPES = sorted(CONTENT_TYPE_TO_MODEL)


# ── outline synthesis from the schema itself ────────────────────────────────


def _unwrap(annotation):
    if get_origin(annotation) is Union:
        args = [a for a in get_args(annotation) if a is not type(None)]
        return args[0] if args else str
    return annotation


def _synth_model(model, depth=0) -> dict:
    if depth > 5:
        return {}
    return {
        name: _synth_value(field.annotation, name, depth)
        for name, field in model.model_fields.items()
    }


def _synth_value(annotation, name="field", depth=0):
    annotation = _unwrap(annotation)
    origin = get_origin(annotation)

    if origin is Literal:
        return get_args(annotation)[0]
    if origin in (list, typing.List):
        inner = get_args(annotation)
        if not inner:
            return [f"{name} one"]
        item = _unwrap(inner[0])
        if isinstance(item, type) and issubclass(item, BaseModel):
            return [_synth_model(item, depth + 1), _synth_model(item, depth + 1)]
        if get_origin(item) is Literal:
            return [get_args(item)[0]]
        if item is int:
            return [1, 2]
        return [f"{name} one", f"{name} two"]
    if origin in (dict, typing.Dict):
        return {"key": "value"}
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return _synth_model(annotation, depth + 1)
    if annotation is bool:
        return True
    if annotation is int:
        return 1200 if "count" in name else 3
    if annotation is float:
        return 4.5
    if name in ("slug", "slug_suggestion"):
        return "a-test-slug"
    return f"{name.replace('_', ' ')} text"


def _outline(content_type: str, promote: bool) -> dict:
    outline = _synth_model(CONTENT_TYPE_TO_MODEL[content_type])
    outline["title"] = f"Test {content_type}"
    outline["promote_brand"] = promote
    outline["brand_voice_promotion"] = dict(_PROMO)
    return outline


def _model_for(content_type: str, promote: bool):
    outline = _outline(content_type, promote)
    if promote:
        outline = apply_brand_slot_to_outline(outline, content_type)
    built = build_structured_content_model(
        outline, content_type, get_generated_content_model(content_type)
    )
    assert built is not None, f"{content_type}: no structured model could be derived"
    return outline, built[0]


def _all_descriptions(model) -> str:
    schema = model.model_json_schema()
    parts = [model.__doc__ or "", schema.get("description", "")]
    parts += [
        prop.get("description", "")
        for prop in (schema.get("properties") or {}).values()
        if isinstance(prop, dict)
    ]
    return "\n".join(parts)


# ── the invariants, for every content type ──────────────────────────────────


@pytest.mark.unit
def test_every_registered_content_type_has_a_placement_policy():
    missing = [
        ct for ct in ALL_CONTENT_TYPES if normalize_content_type(ct) not in BRAND_PLACEMENT_POLICY
    ]
    assert missing == []
    assert len(ALL_CONTENT_TYPES) == 34


@pytest.mark.unit
@pytest.mark.parametrize("content_type", ALL_CONTENT_TYPES)
def test_approved_brand_injects_this_types_own_rules(content_type):
    _, model = _model_for(content_type, promote=True)
    text = _all_descriptions(model)
    policy = BRAND_PLACEMENT_POLICY[normalize_content_type(content_type)]

    assert BRAND in text
    # intensity="none" types state their forced fallback instead of the
    # "no dedicated placement" text, which would read as permission to skip.
    expected = (
        policy["forced_fallback"]
        if policy["intensity"] == "none" and policy["forced_fallback"]
        else policy["placement"]
    )
    assert expected in text, f"{content_type}: own placement rule absent from schema"
    assert policy["guardrail"] in text


@pytest.mark.unit
@pytest.mark.parametrize("content_type", ALL_CONTENT_TYPES)
def test_no_other_content_types_rules_reach_the_schema(content_type):
    _, model = _model_for(content_type, promote=True)
    text = _all_descriptions(model)
    normalized = normalize_content_type(content_type)

    leaked = [
        other
        for other, policy in BRAND_PLACEMENT_POLICY.items()
        if other != normalized and policy["placement"] in text
    ]
    assert leaked == [], f"{content_type} leaked rules from {leaked}"


@pytest.mark.unit
@pytest.mark.parametrize("content_type", ALL_CONTENT_TYPES)
def test_unapproved_brand_injects_nothing(content_type):
    _, model = _model_for(content_type, promote=False)
    text = _all_descriptions(model)

    assert BRAND not in text
    assert model.__doc__ is None
    for policy in BRAND_PLACEMENT_POLICY.values():
        assert policy["placement"] not in text


@pytest.mark.unit
@pytest.mark.parametrize("content_type", ALL_CONTENT_TYPES)
def test_cache_keeps_approved_and_unapproved_models_apart(content_type):
    _, approved = _model_for(content_type, promote=True)
    _, unapproved = _model_for(content_type, promote=False)

    assert approved is not unapproved
    assert BRAND in _all_descriptions(approved)
    assert BRAND not in _all_descriptions(unapproved)


@pytest.mark.unit
@pytest.mark.parametrize("content_type", ALL_CONTENT_TYPES)
def test_a_reserved_slot_always_becomes_a_targeted_field(content_type):
    """Whenever a structural slot IS reserved, the field holding it must be the
    field carrying the directive — that link is the whole point of publishing
    the slot decision rather than re-deriving it."""
    outline, model = _model_for(content_type, promote=True)
    recorded = (outline.get("brand_voice_promotion") or {}).get(SLOT_BLOCK_KEYS) or []
    if not recorded:
        pytest.skip(f"{content_type}: no structural slot reserved for this schema")

    props = model.model_json_schema()["properties"]
    directed = {
        key for key, prop in props.items() if "BRAND PLACEMENT" in (prop.get("description") or "")
    }
    assert directed == {k for k in recorded if k in props}


# ── current slot-targeting behavior, recorded so changes are deliberate ─────

# Types whose outline schema exposes a container `brand_slot` knows how to write
# into. The rest still receive the full rules through the model-level directive
# (asserted above) — they just have no single field to pin them to, because
# `_slot_body_section` only understands `structure.sections` / `sections` and
# those schemas name their section containers differently (`steps`, `terms`,
# `phases`, ...). Extending that writer would move types out of this list; if you
# do, update this map in the same commit.
_EXPECTED_SLOTS = {
    "about-us": ["hero"],
    "alternatives": ["differentiation", "hero"],
    "best-tools": ["rankings", "comparison_matrix"],
    "blog": ["structure"],
    "brand-page": ["hero"],
    "buying-guide": ["requirement_framework", "comparison_matrix"],
    "case-study": ["hero"],
    "comparison": ["hero"],
    "demo-page": ["hero"],
    "feature-overview": ["hero"],
    "in-depth-review": ["hero"],
    "landing-page": ["hero"],
    "pillar-content": ["structure"],
    "product-homepage": ["hero"],
    "product-roundup": ["best_picks", "comparison_matrix"],
    "pros-cons": ["pros"],
    "sales-page": ["hero"],
    "service-page": ["hero"],
    "white-paper": ["solution"],
}


@pytest.mark.unit
@pytest.mark.parametrize("content_type", ALL_CONTENT_TYPES)
def test_structural_slot_matches_recorded_behavior(content_type):
    outline = apply_brand_slot_to_outline(_outline(content_type, True), content_type)
    recorded = (outline.get("brand_voice_promotion") or {}).get(SLOT_BLOCK_KEYS)

    assert recorded == _EXPECTED_SLOTS.get(content_type), (
        f"{content_type}: slot targeting changed — update _EXPECTED_SLOTS deliberately"
    )


@pytest.mark.unit
@pytest.mark.parametrize("content_type", sorted(_EXPECTED_SLOTS))
def test_types_with_a_slot_name_the_brand_in_the_approved_outline(content_type):
    """The slot write must actually put the brand into the plan, not merely
    record that it meant to."""
    outline = apply_brand_slot_to_outline(_outline(content_type, True), content_type)
    recorded = outline["brand_voice_promotion"][SLOT_BLOCK_KEYS]

    touched = "\n".join(str(outline.get(key)) for key in recorded)
    assert BRAND in touched


@pytest.mark.unit
@pytest.mark.parametrize("content_type", ALL_CONTENT_TYPES)
def test_applying_the_slot_twice_changes_nothing(content_type):
    """Outline approval can be re-entered from a LangGraph checkpoint, so a
    second pass must not insert the brand a second time — a duplicated ranked
    entry or a doubled table column would corrupt the approved plan."""
    once = apply_brand_slot_to_outline(_outline(content_type, True), content_type)
    twice = apply_brand_slot_to_outline(once, content_type)

    assert once == twice
