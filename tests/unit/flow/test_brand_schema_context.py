"""Regression tests for schema-level brand-integration context.

The property under test throughout: a generated content model carries the brand
placement rules for EXACTLY ONE content type — the one being generated — and
only when the user approved the promotion at outline review. Everything else is
a leak (another type's rules reaching the schema, or any brand text reaching a
brand-disabled run).

Note on assertions: these compare against the model's raw description strings,
never `json.dumps(...)` of the schema. The policy text is full of em-dashes and
quotes, which `json.dumps` escapes — matching against the encoded form silently
passes tests that are checking nothing.
"""

import pytest

from src.flow.engines.content.generation.brand_placement_policy import (
    BRAND_PLACEMENT_POLICY,
    build_brand_structural_injection,
    resolve_placement_instruction,
)
from src.flow.engines.content.generation.brand_schema_context import (
    resolve_brand_schema_context,
)
from src.flow.engines.content.generation.brand_slot import (
    SLOT_BLOCK_KEYS,
    apply_brand_slot_to_outline,
    describe_planning_leaks,
    scrub_planning_markers,
)
from src.flow.engines.content.generation.outline_structure import resolve_outline_structure
from src.flow.engines.content.generation.structured_body import (
    assemble_structured_payload,
    build_structured_content_model,
)
from src.flow.model.structure.contents import get_generated_content_model
from src.flow.model.structure.contents.base import EMPTY_SCHEMA_CONTEXT, SchemaContext

BRAND = "Acme"

_PROMO = {
    "brand_name": BRAND,
    "brand_url": "https://acme.io",
    "about": "Onboarding automation for support teams",
    "selling_position": "Halves new-hire ramp time",
    "recommended": True,
}


def _landing_outline(promote: bool) -> dict:
    return {
        "title": "Cut onboarding time",
        "promote_brand": promote,
        "brand_voice_promotion": dict(_PROMO),
        "hero": {"headline": "Onboard faster", "subheadline": "Ship in days"},
        "problem": {"pain_points": ["ramp is slow"]},
        "benefits": {"items": ["faster ramp"]},
        "final_cta": {"text": "Book a demo"},
    }


def _blog_outline(promote: bool) -> dict:
    return {
        "title": "Why onboarding stalls",
        "promote_brand": promote,
        "brand_voice_promotion": dict(_PROMO),
        "structure": {
            "sections": [
                {"heading": "Why ramp stalls", "key_points": ["unclear ownership"]},
                {"heading": "How to fix it", "key_points": ["write it down"]},
            ]
        },
    }


def _best_tools_outline(promote: bool) -> dict:
    return {
        "title": "Best onboarding tools",
        "promote_brand": promote,
        "brand_voice_promotion": dict(_PROMO),
        "rankings": [
            {
                "ranked_tools": [
                    {"rank": 1, "tool": {"name": "Rival", "description": "d"}},
                    {"rank": 2, "tool": {"name": "Other", "description": "d"}},
                ]
            }
        ],
    }


def _build(outline: dict, content_type: str):
    """The model the generation node would build for this outline."""
    approved = (
        apply_brand_slot_to_outline(outline, content_type)
        if outline.get("promote_brand")
        else outline
    )
    base = get_generated_content_model(content_type)
    return build_structured_content_model(approved, content_type, base)


def _schema_text(model) -> str:
    """Every description string the model puts in front of the writer."""
    schema = model.model_json_schema()
    parts = [model.__doc__ or "", schema.get("description", "")]
    parts += [
        prop.get("description", "")
        for prop in (schema.get("properties") or {}).values()
        if isinstance(prop, dict)
    ]
    return "\n".join(parts)


# ── brand approved: only this content type's rules ──────────────────────────


@pytest.mark.unit
def test_landing_page_schema_carries_only_landing_page_rules():
    model, blocks = _build(_landing_outline(True), "landing-page")
    text = _schema_text(model)
    policy = BRAND_PLACEMENT_POLICY["landing-page"]

    assert policy["placement"] in text
    assert policy["guardrail"] in text
    assert BRAND in text
    # The hero is where this type's policy puts the brand, and the directive must
    # travel with that field rather than sitting only in the model description.
    hero = model.model_json_schema()["properties"]["hero"]["description"]
    assert policy["placement"] in hero
    assert "hero" in [b.key for b in blocks]


@pytest.mark.unit
def test_blog_schema_carries_only_blog_rules():
    model, _ = _build(_blog_outline(True), "blog")
    text = _schema_text(model)

    assert BRAND_PLACEMENT_POLICY["blog"]["placement"] in text
    assert BRAND_PLACEMENT_POLICY["blog"]["guardrail"] in text
    assert BRAND_PLACEMENT_POLICY["landing-page"]["placement"] not in text


@pytest.mark.unit
@pytest.mark.parametrize(
    "content_type,outline_factory",
    [
        ("landing-page", _landing_outline),
        ("blog", _blog_outline),
        ("best-tools", _best_tools_outline),
    ],
)
def test_no_other_content_types_rules_leak_into_the_schema(content_type, outline_factory):
    model, _ = _build(outline_factory(True), content_type)
    text = _schema_text(model)

    leaked = [
        other
        for other, policy in BRAND_PLACEMENT_POLICY.items()
        if other != content_type and policy["placement"] in text
    ]
    assert leaked == [], f"{content_type} schema leaked rules from: {leaked}"


@pytest.mark.unit
def test_forced_fallback_is_used_for_a_no_promotion_content_type():
    """glossary is intensity="none" — an approved mention must still be placed,
    via forced_fallback, and must NOT quote the "no dedicated placement" text."""
    outline = {
        "promote_brand": True,
        "brand_voice_promotion": dict(_PROMO),
        "terms": [{"term": "Onboarding", "definition": "d"}],
    }
    model, _ = _build(outline, "glossary")
    text = _schema_text(model)
    policy = BRAND_PLACEMENT_POLICY["glossary"]

    assert policy["forced_fallback"] in text
    assert policy["placement"] not in text


# ── brand not approved: nothing injected ────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize(
    "content_type,outline_factory",
    [("landing-page", _landing_outline), ("blog", _blog_outline)],
)
def test_brand_not_approved_injects_nothing(content_type, outline_factory):
    model, _ = _build(outline_factory(False), content_type)
    text = _schema_text(model)

    assert BRAND not in text
    assert model.__doc__ is None
    for policy in BRAND_PLACEMENT_POLICY.values():
        assert policy["placement"] not in text


@pytest.mark.unit
def test_brand_not_approved_schema_matches_a_context_free_build():
    """The strongest form of "nothing changed": byte-identical schema."""
    outline = _landing_outline(False)
    base = get_generated_content_model("landing-page")

    with_resolver, _ = build_structured_content_model(outline, "landing-page", base)
    explicit_empty, _ = build_structured_content_model(
        outline, "landing-page", base, context=EMPTY_SCHEMA_CONTEXT
    )
    assert with_resolver.model_json_schema() == explicit_empty.model_json_schema()


@pytest.mark.unit
def test_promote_brand_without_a_brand_name_injects_nothing():
    outline = _landing_outline(True)
    outline["brand_voice_promotion"] = {"brand_name": "   "}
    blocks = resolve_outline_structure(outline, "landing-page")

    assert resolve_brand_schema_context(outline, "landing-page", blocks) is EMPTY_SCHEMA_CONTEXT


# ── the model cache must not mix the two ────────────────────────────────────


@pytest.mark.unit
def test_cache_never_hands_a_brand_model_to_a_brand_disabled_run():
    """Same content type, same block set — the only difference is the brand.

    Without the context signature in the cache key these two collide and the
    second build silently inherits the first's injected rules.
    """
    approved, _ = _build(_landing_outline(True), "landing-page")
    disabled, _ = _build(_landing_outline(False), "landing-page")

    assert approved is not disabled
    assert BRAND in _schema_text(approved)
    assert BRAND not in _schema_text(disabled)


@pytest.mark.unit
def test_cache_separates_two_different_brands():
    other = _landing_outline(True)
    other["brand_voice_promotion"] = {**_PROMO, "brand_name": "Globex"}

    acme, _ = _build(_landing_outline(True), "landing-page")
    globex, _ = _build(other, "landing-page")

    assert acme is not globex
    assert "Globex" not in _schema_text(acme)
    assert BRAND not in _schema_text(globex)


# ── the slot decision is published, not re-derived ──────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize(
    "content_type,outline_factory,expected_keys",
    [
        ("landing-page", _landing_outline, ["hero"]),
        ("blog", _blog_outline, ["structure"]),
        ("best-tools", _best_tools_outline, ["rankings"]),
    ],
)
def test_apply_brand_slot_records_the_block_it_wrote(content_type, outline_factory, expected_keys):
    approved = apply_brand_slot_to_outline(outline_factory(True), content_type)
    assert approved["brand_voice_promotion"][SLOT_BLOCK_KEYS] == expected_keys


@pytest.mark.unit
def test_recorded_slot_block_is_the_field_that_gets_the_directive():
    approved = apply_brand_slot_to_outline(_best_tools_outline(True), "best-tools")
    blocks = resolve_outline_structure(approved, "best-tools")
    context = resolve_brand_schema_context(approved, "best-tools", blocks)

    assert set(context.field_directives) == {"rankings"}


@pytest.mark.unit
def test_missing_slot_record_falls_back_without_inventing_a_body_placement():
    """A prefers_top type targets its opening block; a body-led type targets
    none, leaving placement to the policy text rather than a second guess."""
    landing = _landing_outline(True)  # never passed through apply_brand_slot
    landing_blocks = resolve_outline_structure(landing, "landing-page")
    landing_ctx = resolve_brand_schema_context(landing, "landing-page", landing_blocks)
    assert set(landing_ctx.field_directives) == {landing_blocks[0].key}

    blog = _blog_outline(True)
    blog_blocks = resolve_outline_structure(blog, "blog")
    blog_ctx = resolve_brand_schema_context(blog, "blog", blog_blocks)
    assert blog_ctx.field_directives == {}
    # The model-level contract still states the rules.
    assert BRAND_PLACEMENT_POLICY["blog"]["placement"] in blog_ctx.model_directive


# ── ranked-list types: the brand belongs in the comparison table too ────────


def _best_tools_with_matrix() -> dict:
    return {
        "promote_brand": True,
        "brand_voice_promotion": dict(_PROMO),
        "hero": {"headline": "Best onboarding tools", "subheadline": "How we picked"},
        "rankings": [
            {
                "category": "Onboarding",
                "ranked_tools": [
                    {
                        "rank": 1,
                        "tool": {"name": "Rival", "description": "d"},
                        "ranking_reason": "r",
                    },
                    {
                        "rank": 2,
                        "tool": {"name": "Other", "description": "d"},
                        "ranking_reason": "r",
                    },
                ],
            }
        ],
        "comparison_matrix": {
            "tools_compared": ["Rival", "Other"],
            "rows": [
                {"feature": "Pricing", "tool_values": ["$20/mo", "$35/mo"]},
                {"feature": "SSO", "tool_values": ["Yes", "No"]},
            ],
        },
    }


def _product_roundup_with_matrix() -> dict:
    return {
        "promote_brand": True,
        "brand_voice_promotion": dict(_PROMO),
        "best_picks": {
            "groups": [
                {"products": [{"rank": 1, "product": {"name": "Rival", "description": "d"}}]}
            ]
        },
        "comparison_matrix": {
            "products": ["Rival", "Other"],
            "rows": [{"feature": "Pricing", "values": ["$20/mo", "$35/mo"]}],
        },
    }


@pytest.mark.unit
def test_best_tools_puts_the_brand_in_the_comparison_table():
    approved = apply_brand_slot_to_outline(_best_tools_with_matrix(), "best-tools")
    matrix = approved["comparison_matrix"]

    assert matrix["tools_compared"][0] == BRAND
    assert matrix["tools_compared"] == [BRAND, "Rival", "Other"]


@pytest.mark.unit
def test_comparison_table_rows_stay_aligned_with_their_columns():
    """A name inserted without a value shifts every row, handing the brand a
    competitor's pricing — worse than the missing column it was fixing."""
    approved = apply_brand_slot_to_outline(_best_tools_with_matrix(), "best-tools")
    matrix = approved["comparison_matrix"]

    for row in matrix["rows"]:
        assert len(row["tool_values"]) == len(matrix["tools_compared"])
        assert BRAND in row["tool_values"][0]

    pricing = next(r for r in matrix["rows"] if r["feature"] == "Pricing")
    # The competitors keep their own values — nothing was reassigned.
    assert pricing["tool_values"][1:] == ["$20/mo", "$35/mo"]


@pytest.mark.unit
def test_product_roundup_uses_its_own_matrix_field_names():
    approved = apply_brand_slot_to_outline(_product_roundup_with_matrix(), "product-roundup")
    matrix = approved["comparison_matrix"]

    assert matrix["products"] == [BRAND, "Rival", "Other"]
    assert len(matrix["rows"][0]["values"]) == 3
    assert BRAND in matrix["rows"][0]["values"][0]


@pytest.mark.unit
def test_brand_already_in_the_table_is_not_duplicated():
    outline = _best_tools_with_matrix()
    outline["comparison_matrix"]["tools_compared"] = ["Rival", BRAND]
    approved = apply_brand_slot_to_outline(outline, "best-tools")

    assert approved["comparison_matrix"]["tools_compared"].count(BRAND) == 1
    for row in approved["comparison_matrix"]["rows"]:
        assert len(row["tool_values"]) == 2  # untouched


@pytest.mark.unit
def test_missing_comparison_matrix_still_slots_the_ranking():
    """Soft-fail: an outline without a matrix keeps working."""
    outline = _best_tools_with_matrix()
    outline.pop("comparison_matrix")
    approved = apply_brand_slot_to_outline(outline, "best-tools")

    assert approved["brand_voice_promotion"][SLOT_BLOCK_KEYS] == ["rankings"]
    assert approved["rankings"][0]["ranked_tools"][0]["tool"]["name"] == BRAND


@pytest.mark.unit
def test_comparison_table_field_receives_the_brand_directive():
    approved = apply_brand_slot_to_outline(_best_tools_with_matrix(), "best-tools")
    assert approved["brand_voice_promotion"][SLOT_BLOCK_KEYS] == ["rankings", "comparison_matrix"]

    model, _ = build_structured_content_model(
        approved, "best-tools", get_generated_content_model("best-tools")
    )
    props = model.model_json_schema()["properties"]
    assert "BRAND PLACEMENT" in props["comparison_matrix"]["description"]
    assert "BRAND PLACEMENT" in props["rankings"]["description"]


@pytest.mark.unit
@pytest.mark.parametrize("content_type", ["best-tools", "product-roundup"])
def test_ranked_list_anchor_names_the_comparison_table(content_type):
    """The anchor is the single source of truth reused by the prompt, the schema,
    humanize and repair — so naming the table once covers all four."""
    anchor = build_brand_structural_injection(content_type, BRAND)
    assert "comparison table" in anchor
    assert "rank 1" in anchor


# ── the existing rules are unchanged ────────────────────────────────────────

_EXPECTED_INTENSITIES = {
    "blog": "low",
    "how-to-guide": "low",
    "explainer": "low",
    "pillar-content": "low",
    "checklist": "low",
    "tutorial": "low",
    "faq": "none",
    "white-paper": "moderate",
    "case-study": "high",
    "glossary": "none",
    "resource-list": "low",
    "comparison": "high",
    "best-tools": "high",
    "product-roundup": "high",
    "alternatives": "high",
    "in-depth-review": "high",
    "pros-cons": "high",
    "buying-guide": "moderate",
    "brand-page": "maximal",
    "product-homepage": "maximal",
    "feature-overview": "high",
    "documentation": "none",
    "login-guide": "none",
    "help-center": "none",
    "contact-us": "low",
    "about-us": "moderate",
    "sales-page": "maximal",
    "pricing-page": "high",
    "signup-page": "low",
    "demo-page": "moderate",
    "coupon-page": "high",
    "checkout-page": "low",
    "landing-page": "maximal",
    "service-page": "high",
}


@pytest.mark.unit
def test_brand_placement_policy_table_is_unchanged():
    """Guards the single source of truth against incidental edits."""
    assert {k: v["intensity"] for k, v in BRAND_PLACEMENT_POLICY.items()} == _EXPECTED_INTENSITIES
    assert len(BRAND_PLACEMENT_POLICY) == 34
    for content_type, policy in BRAND_PLACEMENT_POLICY.items():
        assert policy["placement"].strip(), content_type
        assert policy["guardrail"].strip(), content_type
        if policy["intensity"] == "none":
            assert policy["forced_fallback"].strip(), content_type


@pytest.mark.unit
@pytest.mark.parametrize("content_type", sorted(BRAND_PLACEMENT_POLICY))
def test_resolve_placement_instruction_matches_the_policy(content_type):
    policy = BRAND_PLACEMENT_POLICY[content_type]
    text, forced = resolve_placement_instruction(policy)

    if policy["intensity"] == "none" and policy["forced_fallback"]:
        assert forced is True
        assert text == policy["forced_fallback"]
    else:
        assert forced is False
        assert text == policy["placement"]


# ── the carrier itself ──────────────────────────────────────────────────────


@pytest.mark.unit
def test_empty_schema_context_is_falsy_and_inert():
    assert not EMPTY_SCHEMA_CONTEXT
    assert EMPTY_SCHEMA_CONTEXT.signature == ()
    assert EMPTY_SCHEMA_CONTEXT.describe_field("hero", "base text") == "base text"
    assert EMPTY_SCHEMA_CONTEXT.compose_doc("Base doc.") == "Base doc."


@pytest.mark.unit
def test_schema_context_appends_field_text_and_prepends_model_text():
    context = SchemaContext(
        model_directive="CONTRACT.", field_directives={"hero": "RULE."}, signature=("x",)
    )
    assert context
    assert context.describe_field("hero", "base") == "base\n\nRULE."
    assert context.describe_field("problem", "base") == "base"
    assert context.compose_doc("Base doc.") == "CONTRACT.\n\nBase doc."
    assert context.compose_doc("") == "CONTRACT."


# ── non-blocking reinforcement: guidance, never a failure point ─────────────
#
# The agent wraps the generated model in `ToolStrategy(..., handle_errors=True)`,
# where a Pydantic ValidationError is not a clean failure — LangChain feeds the
# error back to the model and REGENERATES THE WHOLE ARTICLE, bounded only by the
# graph's recursion limit. So nothing added for brand adherence may ever raise.


@pytest.mark.unit
def test_a_missing_brand_mention_never_raises():
    """The carve-out, stated as a test.

    A response that ignores the brand entirely must still validate. If this ever
    raises, every miss becomes a full article regeneration instead of a repair.
    """
    model, blocks = _build(_landing_outline(True), "landing-page")
    payload = {
        "title": "Onboarding, explained",
        "introduction": "No brand named anywhere in this article.",
        "body_markdown": "Still nothing.",
        **{b.key: {"heading": None, "markdown": "Generic copy."} for b in blocks},
    }

    obj = model.model_validate(payload)  # must not raise
    assert obj.title == "Onboarding, explained"


# ── planning-marker scrub ───────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize(
    "text",
    [
        "| Acme | [Acme — fill from brand info] | $20 |",
        "Ramp is slow. Work in the approved mention of Acme here — Halves ramp. Next.",
        "Acme as an applied solution component.",
    ],
)
def test_unambiguous_planning_markers_are_removed(text):
    cleaned, removed = scrub_planning_markers(text)

    assert removed >= 1
    assert "fill from brand info" not in cleaned
    assert "Work in the approved mention" not in cleaned
    assert "as an applied solution component" not in cleaned


@pytest.mark.unit
def test_the_scrub_keeps_the_surrounding_sentence():
    cleaned, _ = scrub_planning_markers(
        "Ramp is slow. Work in the approved mention of Acme here — Halves ramp. Next point."
    )
    assert cleaned == "Ramp is slow. Next point."


@pytest.mark.unit
@pytest.mark.parametrize(
    "text",
    [
        "Our Featured pick this year is genuinely excellent.",
        "Totally clean prose with no planning markers at all.",
        "",
    ],
)
def test_legitimate_copy_survives_the_scrub_untouched(text):
    """Shipping a leaked marker is cosmetic; deleting real copy is not."""
    cleaned, removed = scrub_planning_markers(text)

    assert removed == 0
    assert cleaned == text


@pytest.mark.unit
def test_ambiguous_markers_are_reported_but_not_removed():
    text = "Our Featured pick this year is Acme."
    assert describe_planning_leaks(text) == ["Featured pick"]
    assert scrub_planning_markers(text)[0] == text


@pytest.mark.unit
def test_assembly_scrubs_body_and_introduction():
    _, blocks = _build(_landing_outline(True), "landing-page")
    content = {
        "title": "T",
        "introduction": "Intro. Work in the approved mention of Acme here — x. Rest.",
        "hero": {"heading": None, "markdown": "Acme helps. [Acme — fill from brand info] More."},
        **{b.key: {"heading": None, "markdown": "copy"} for b in blocks if b.key != "hero"},
    }
    payload = assemble_structured_payload(content, blocks)

    assert payload["introduction"] == "Intro. Rest."
    assert "fill from brand info" not in payload["body_markdown"]
    assert "Acme helps." in payload["body_markdown"]


@pytest.mark.unit
def test_a_payload_with_no_markers_is_left_alone():
    _, blocks = _build(_landing_outline(True), "landing-page")
    content = {
        "title": "T",
        "introduction": "A perfectly ordinary introduction.",
        **{b.key: {"heading": None, "markdown": "Ordinary copy."} for b in blocks},
    }
    payload = assemble_structured_payload(content, blocks)

    assert payload["introduction"] == "A perfectly ordinary introduction."
