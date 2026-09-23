"""Regression tests: an outline schema must not manufacture placeholder copy.

Two defects, both found by running all 34 content types through the pipeline:

1. `resolve_outline_cta` documents that it fires "only when the outline itself
   declares one, so the requirement is driven by what was actually approved for
   this specific article rather than a hardcoded content-type list." Three
   commercial hero schemas defeated that with a Pydantic DEFAULT: when the
   outline model omitted `primary_cta`, Pydantic supplied "Try Product" /
   "Try Our Product", `resolve_outline_cta` read it as an approved CTA, the
   generation prompt ordered the writer to reproduce "this exact CTA text"
   verbatim, and `check_cta_presence` blocked until it did — publishing a CTA
   that names no product at all. Nobody approved that string; a default is not
   an approval.

2. `product_names.PRODUCT_NAME_GUIDANCE` exists so the "name a REAL product"
   rule "is read at the moment the name is decoded rather than a thousand
   tokens earlier in the prompt". It was wired into `comparison` only, leaving
   every other placeholder-prone type (alternatives, best-tools,
   product-roundup, in-depth-review, pros-cons, buying-guide, resource-list)
   with bare, undescribed `name: str` fields.
"""

from __future__ import annotations

import json

import pytest

from src.flow.engines.content.generation.requirements_spec import resolve_outline_cta
from src.flow.model.structure.outlines import CONTENT_TYPE_TO_MODEL, get_outline_model
from src.flow.model.structure.outlines.product_names import find_placeholder_names_in_text

# Types whose hero used to manufacture a CTA naming an anonymous "Product".
_HERO_CTA_TYPES = (
    "in-depth-review",
    "pros-cons",
    "alternatives",
    "product-roundup",
    "buying-guide",
    "comparison",
    "best-tools",
)

# Types that describe specific, named products and must carry the rule on the
# name field itself.
_PRODUCT_NAMING_TYPES = (
    "comparison",
    "alternatives",
    "best-tools",
    "product-roundup",
    "in-depth-review",
    "pros-cons",
    "buying-guide",
    "resource-list",
)

_GUIDANCE_MARKER = "NEVER invent a generic stand-in"


def _hero_with_only_required_fields(content_type: str) -> dict:
    """The hero an outline model produces when it omits every optional field."""
    hero_cls = get_outline_model(content_type).model_fields["hero"].annotation
    required = {
        name: ("placeholder-free" if field.annotation is str else [])
        for name, field in hero_cls.model_fields.items()
        if field.is_required()
    }
    return hero_cls(**required).model_dump()


@pytest.mark.parametrize("content_type", _HERO_CTA_TYPES)
def test_omitted_hero_cta_never_becomes_an_approved_product_placeholder(content_type):
    cta = resolve_outline_cta({"hero": _hero_with_only_required_fields(content_type)})
    text = (cta or {}).get("text", "")
    # Either no CTA is claimed at all, or the default is real, publishable copy —
    # never a stand-in for a product the article never names.
    assert "Try Product" not in text
    assert "Try Our Product" not in text


@pytest.mark.parametrize("content_type", _PRODUCT_NAMING_TYPES)
def test_product_name_fields_carry_the_real_name_rule(content_type):
    schema = json.dumps(get_outline_model(content_type).model_json_schema())
    assert _GUIDANCE_MARKER in schema, (
        f"{content_type}'s outline schema has product/tool name fields with no "
        f"placeholder guidance — the rule must reach the field the model decodes."
    )


def test_no_outline_schema_ships_a_placeholder_entity_as_a_default():
    """No content type's schema defaults contain a detectable placeholder entity."""
    offenders = {}
    for content_type in CONTENT_TYPE_TO_MODEL:
        schema = get_outline_model(content_type).model_json_schema()
        defaults = json.dumps(
            [
                definition.get("default")
                for definition in _walk_properties(schema)
                if isinstance(definition.get("default"), str)
            ]
        )
        found = find_placeholder_names_in_text(defaults)
        if found:
            offenders[content_type] = found
    assert not offenders, offenders


def _walk_properties(node):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "properties" and isinstance(value, dict):
                yield from (v for v in value.values() if isinstance(v, dict))
            yield from _walk_properties(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_properties(item)
