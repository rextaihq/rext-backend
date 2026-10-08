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
from src.flow.engines.content.generation.repair_content import _BRAND_RELATED_CHECKS
from src.flow.engines.content.generation.requirements_spec import build_requirements_spec
from src.flow.engines.content.generation.validation import (
    _FINAL_REPAIRABLE_BRAND_CHECKS,
    CHECK_REGISTRY,
    FINAL_VALIDATE_CHECKS,
    check_brand_placement_policy,
    check_brand_prominence,
    check_brand_url_accuracy,
)

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


# --- the chosen level is checked, not only asked for ------------------------------


def _article(intro_brand=False, early_body=False, late_body=False, closing=False):
    filler = "Plain running advice without any product. " * 25
    sections = []
    for i in range(6):
        text = filler
        if i == 0 and early_body:
            text = f"{BRAND} fits running shoes to your gait in five minutes. " + text
        if i == 3 and late_body:
            text = text + f"{BRAND} also helps here. "
        sections.append(f"## Section {i}\n\n{text}")
    body = "\n\n".join(sections)
    if closing:
        body += f"\n\nIf you want a fitted pair today, {BRAND} matches shoes to your gait in five minutes."
    intro = f"{BRAND} fits running shoes to your gait." if intro_brand else "An introduction."
    return {"introduction": intro, "body_markdown": body}


def _prominence_check(level, **article):
    spec = build_requirements_spec(_blog_outline(brand_prominence=level), "blog")
    return check_brand_prominence(_article(**article), spec)


def test_subtle_allows_exactly_one_mention():
    assert _prominence_check("subtle", early_body=True)["passed"]

    result = _prominence_check("subtle", early_body=True, late_body=True)
    assert not result["passed"]
    assert result["severity"] == "blocking"
    assert "exactly once" in result["detail"] and "2 times" in result["detail"]


def test_prominent_needs_the_closing_mention():
    result = _prominence_check("prominent", intro_brand=True, early_body=True)
    assert not result["passed"]
    assert result["severity"] == "blocking"
    assert "closing call to action" in result["detail"]

    assert _prominence_check("prominent", intro_brand=True, closing=True)["passed"]


def test_a_repair_after_the_rewrite_is_not_kept_when_it_makes_a_subtle_mention_two():
    """Replayed on a real draft (rext-control#787): asked to move a Subtle article's one
    mention earlier, the repair after the rewrite added a second one in the earlier section.
    The place then passed, the repair was kept, and the article named the brand twice."""
    from src.flow.engines.content.generation.humanize_content import _repair_fixed

    spec = build_requirements_spec(_blog_outline(brand_prominence="subtle"), "blog")
    too_late = _article(late_body=True)
    placement = check_brand_placement_policy(too_late, spec)
    assert not placement["passed"] and check_brand_prominence(too_late, spec)["passed"]

    moved = _article(early_body=True)
    added = _article(early_body=True, late_body=True)
    assert check_brand_placement_policy(added, spec)["passed"]  # the place alone is fixed

    assert _repair_fixed(moved, too_late, placement, spec["brand_context"], spec, [])
    assert not _repair_fixed(added, too_late, placement, spec["brand_context"], spec, [])


def test_a_repair_after_the_rewrite_is_not_kept_when_the_first_mention_loses_its_link():
    from src.flow.engines.content.generation.humanize_content import _repair_fixed

    def linked(article):
        late = f"{BRAND} also helps here."
        return {
            **article,
            "body_markdown": article["body_markdown"].replace(
                late, f"[{BRAND}](https://acme.test) also helps here."
            ),
        }

    # No level chosen: nothing limits the mentions, and the link is still the first one's.
    spec = build_requirements_spec(_blog_outline(), "blog")
    before = linked(_article(late_body=True))
    with_a_bare_mention_first = linked(_article(early_body=True, late_body=True))
    placement = {"name": "brand_placement_policy", "passed": False}
    assert check_brand_placement_policy(with_a_bare_mention_first, spec)["passed"]
    assert check_brand_url_accuracy(before, spec)["passed"]
    assert not check_brand_url_accuracy(with_a_bare_mention_first, spec)["passed"]

    assert not _repair_fixed(
        with_a_bare_mention_first, before, placement, spec["brand_context"], spec, []
    )


def test_no_level_is_not_checked():
    assert _prominence_check(None, early_body=True, late_body=True)["passed"]


def test_the_check_runs_before_and_after_humanizing_and_is_repaired():
    assert check_brand_prominence in CHECK_REGISTRY
    assert check_brand_prominence in FINAL_VALIDATE_CHECKS
    assert "brand_prominence" in _FINAL_REPAIRABLE_BRAND_CHECKS
    assert "brand_prominence" in _BRAND_RELATED_CHECKS
