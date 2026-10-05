"""The brand prominence level chosen at the outline gate: prominent, subtle or none.

One per-article policy (the content type's, at the chosen level) is what the
writer, the humanize and repair passes, the schema directive and the brand
checks all read; an outline without a level keeps the content type's policy.
"""

import pytest

import src.flow.engines.content.review.outline as review_module
from src.flow.engines.content.generation.brand_placement_policy import (
    apply_brand_prominence,
    build_brand_structural_injection,
    recommended_brand_prominence,
    resolve_article_brand_policy,
    resolve_brand_placement_policy,
)
from src.flow.engines.content.generation.brand_schema_context import (
    resolve_brand_schema_context,
)
from src.flow.engines.content.generation.humanize_content import _build_brand_instruction
from src.flow.engines.content.generation.outline_structure import resolve_outline_structure
from src.flow.engines.content.generation.requirements_spec import build_requirements_spec
from src.flow.engines.content.generation.validation import check_brand_placement_policy

BRAND = "Acme Run"
PROMO = {
    "brand_name": BRAND,
    "brand_url": "https://acme.test",
    "about": "Acme Run fits running shoes to your gait in five minutes.",
    "selling_position": "Gait-matched fitting.",
    "recommended": True,
}


def _blog_outline(**extra):
    return {
        "title": "Running shoes for beginners",
        "structure": {
            "sections": [
                {"heading": "Why the right shoe matters", "heading_level": "H2"},
                {"heading": "How to get fitted", "heading_level": "H2"},
            ]
        },
        "promote_brand": True,
        "brand_voice_promotion": dict(PROMO),
        **extra,
    }


# --- the policy at each level --------------------------------------------------


@pytest.mark.parametrize("level", [None, "none", "loud", ""])
def test_no_level_keeps_the_content_types_policy(level):
    policy = resolve_brand_placement_policy("blog")

    assert apply_brand_prominence(policy, level) is policy


@pytest.mark.parametrize("content_type", ["blog", "landing-page", "best-tools"])
def test_subtle_is_one_early_body_mention_with_no_slot(content_type):
    policy = apply_brand_prominence(resolve_brand_placement_policy(content_type), "subtle")

    assert policy["intensity"] == "low"
    assert policy["prefers_top"] is False
    assert policy["hero_anchored"] is False
    assert "exactly one mention" in policy["guardrail"]
    assert "introduction" in policy["guardrail"] and "call to action" in policy["guardrail"]
    assert build_brand_structural_injection(content_type, BRAND, policy) == ""


def test_prominent_on_a_body_led_type_moves_the_brand_up():
    base = resolve_brand_placement_policy("blog")
    policy = apply_brand_prominence(base, "prominent")

    assert policy["intensity"] == "high"
    assert policy["prefers_top"] is True
    assert policy["placement"].startswith(base["placement"])
    assert "within the first 20% of the article" in policy["placement"]
    assert "closing call to action" in policy["placement"]
    assert "never the bare name or a link on a line of its own" in policy["placement"]
    # the blog's own guardrail keeps the brand out of the introduction; replaced
    assert policy["guardrail"] != base["guardrail"]
    assert "introduction" not in policy["guardrail"]


def test_prominent_on_a_brand_led_type_keeps_its_guardrail_and_intensity():
    base = resolve_brand_placement_policy("sales-page")
    policy = apply_brand_prominence(base, "prominent")

    assert policy["intensity"] == base["intensity"] == "maximal"
    assert policy["guardrail"] == base["guardrail"]


def test_prominent_uses_the_types_own_top_window():
    policy = apply_brand_prominence(resolve_brand_placement_policy("best-tools"), "prominent")

    assert "within the first 50% of the article" in policy["placement"]


def test_prominent_on_a_no_promotion_type_builds_on_its_fallback():
    base = resolve_brand_placement_policy("glossary")
    assert base["intensity"] == "none" and base["forced_fallback"]

    policy = apply_brand_prominence(base, "prominent")

    assert policy["placement"].startswith(base["forced_fallback"])
    assert policy["intensity"] == "high"
    assert policy["forced_fallback"] == ""


def test_the_article_policy_reads_the_outline():
    assert resolve_article_brand_policy("blog", _blog_outline())["intensity"] == "low"
    assert resolve_article_brand_policy("blog", _blog_outline(brand_prominence="prominent"))[
        "prefers_top"
    ]
    assert resolve_article_brand_policy("blog", None) == resolve_brand_placement_policy("blog")


@pytest.mark.parametrize(
    ("content_type", "recommended", "level"),
    [
        ("blog", True, "subtle"),
        ("explainer", True, "subtle"),
        ("landing-page", True, "prominent"),
        ("comparison", True, "prominent"),
        ("blog", False, "none"),
        ("landing-page", False, "none"),
    ],
)
def test_the_recommended_level_follows_the_types_nature(content_type, recommended, level):
    assert recommended_brand_prominence(content_type, recommended) == level


# --- the spec and the checks follow the level -----------------------------------


def test_spec_carries_the_articles_policy_but_the_types_hero_rule():
    subtle_landing = build_requirements_spec(
        _blog_outline(brand_prominence="subtle"), "landing-page"
    )
    assert subtle_landing["brand_placement"] == "body_only"
    assert subtle_landing["brand_placement_policy"]["prominence"] == "subtle"
    assert subtle_landing["hero_required"] is True  # the landing page still needs its hero

    prominent_blog = build_requirements_spec(_blog_outline(brand_prominence="prominent"), "blog")
    assert prominent_blog["brand_placement"] == "hero"
    assert prominent_blog["hero_required"] is False


def _article_with_brand_in_the_introduction():
    body = "\n\n".join(
        f"## Section {i}\n\n" + "Plain running advice without any product. " * 30 for i in range(6)
    )
    return {
        "introduction": f"{BRAND} fits running shoes to your gait in five minutes, so start there.",
        "body_markdown": body,
    }


def test_the_brand_check_grades_the_chosen_level():
    article = _article_with_brand_in_the_introduction()

    prominent = check_brand_placement_policy(
        article, build_requirements_spec(_blog_outline(brand_prominence="prominent"), "blog")
    )
    subtle = check_brand_placement_policy(
        article, build_requirements_spec(_blog_outline(brand_prominence="subtle"), "blog")
    )

    assert prominent["passed"]
    assert not subtle["passed"]  # a subtle mention does not open the article


# --- the prompts read it ---------------------------------------------------------


def test_humanize_allows_several_mentions_only_when_prominent():
    def instruction(level):
        return _build_brand_instruction(
            brand_name=BRAND,
            brand_url="",
            content_type="blog",
            policy=resolve_article_brand_policy("blog", _blog_outline(brand_prominence=level)),
        )

    assert "carries approved mentions" in instruction("prominent")
    assert "within the first 20% of the article" in instruction("prominent")
    assert "carries one approved mention" in instruction("subtle")
    assert "exactly one mention" in instruction("subtle")


def test_schema_directive_leaves_room_for_more_mentions_when_prominent():
    def directive(level):
        outline = _blog_outline(brand_prominence=level)
        outline["brand_voice_promotion"]["slot_block_keys"] = ["structure"]
        blocks = resolve_outline_structure(outline, "blog")
        return resolve_brand_schema_context(outline, "blog", blocks).model_directive

    assert "One mention belongs in `structure`" in directive("prominent")
    assert "The mention belongs in `structure`" in directive(None)


# --- the gate ----------------------------------------------------------------------


def _approve(monkeypatch, response, recommended=True):
    payloads, slots = [], []

    def _interrupt(payload):
        payloads.append(payload)
        return response

    def _slot(outline, content_type):
        slots.append(content_type)
        return outline

    monkeypatch.setattr(review_module, "interrupt", _interrupt)
    monkeypatch.setattr(review_module, "apply_brand_slot_to_outline", _slot)
    outline = _blog_outline()
    outline["brand_voice_promotion"]["recommended"] = recommended
    outline.pop("promote_brand")
    result = review_module.review_outline({"content": {"outline": outline, "content_type": "blog"}})
    return payloads[0], result["content"]["outline"], slots


def test_gate_payload_recommends_a_level(monkeypatch):
    payload, _, _ = _approve(monkeypatch, {"action": "approve"})
    assert payload["recommended_brand_prominence"] == "subtle"

    payload, _, _ = _approve(monkeypatch, {"action": "approve"}, recommended=False)
    assert payload["recommended_brand_prominence"] == "none"


@pytest.mark.parametrize(
    ("response", "promote", "level", "slotted"),
    [
        ({"brand_prominence": "prominent"}, True, "prominent", True),
        ({"brand_prominence": "subtle"}, True, "subtle", False),
        ({"brand_prominence": "none", "promote_brand": True}, False, "none", False),
        ({"promote_brand": False}, False, None, False),
        ({"promote_brand": True}, True, None, True),
        ({}, True, None, True),  # the recommendation
        ({"brand_prominence": "loud", "promote_brand": False}, False, None, False),
    ],
)
def test_gate_stores_the_level_and_reserves_a_slot_unless_subtle(
    monkeypatch, response, promote, level, slotted
):
    _, outline, slots = _approve(monkeypatch, {"action": "approve", **response})

    assert outline["promote_brand"] is promote
    assert outline["brand_prominence"] == level
    assert bool(slots) is slotted
