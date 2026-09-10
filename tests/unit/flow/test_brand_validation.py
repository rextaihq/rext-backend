"""Decode-time brand validation on the generated content model.

The contract under test has two halves, and both matter:

  * the validator DOES enforce the approved brand rules — a response that omits
    the brand, or puts it where this content type's policy forbids, is rejected
    so the agent regenerates it;
  * it can never become a failure point — the rejection budget is small, it
    self-disarms once spent, and outside a granted budget it never raises at all.

The rules themselves are not restated here. The validator calls validation.py's
existing `check_brand_presence` and `check_brand_placement_policy`, so these
tests assert the wiring and the bounding, not the policy.
"""

import pytest
from pydantic import ValidationError

from src.flow.engines.content.generation.brand_slot import apply_brand_slot_to_outline
from src.flow.engines.content.generation.brand_validation import (
    brand_retry_budget,
    build_brand_spec_slice,
)
from src.flow.engines.content.generation.structured_body import build_structured_content_model
from src.flow.model.structure.contents import get_generated_content_model

BRAND = "Acme"
_PROMO = {
    "brand_name": BRAND,
    "brand_url": "https://acme.io",
    "about": "Onboarding automation for support teams",
    "selling_position": "Halves new-hire ramp time",
}

# Copy that satisfies the landing-page policy: the brand named in the hero, with
# a concrete claim drawn from the approved selling position.
_COMPLIANT_HERO = "Acme halves new-hire ramp time for support teams. Start today."
_BRANDLESS_HERO = "A better way to onboard your team. Start today."


def _landing_outline(promote: bool = True) -> dict:
    outline = {
        "title": "Cut onboarding time",
        "promote_brand": promote,
        "brand_voice_promotion": dict(_PROMO),
        "hero": {"headline": "Onboard faster", "subheadline": "Ship in days"},
        "problem": {"pain_points": ["ramp is slow"]},
        "benefits": {"items": ["faster ramp"]},
    }
    return apply_brand_slot_to_outline(outline, "landing-page") if promote else outline


def _landing_model(promote: bool = True):
    outline = _landing_outline(promote)
    return build_structured_content_model(
        outline, "landing-page", get_generated_content_model("landing-page")
    )


def _payload(blocks, hero_markdown: str, **overrides) -> dict:
    payload = {
        "title": "Cut onboarding time",
        "introduction": "Onboarding is hard for growing support teams.",
        "hero": {"heading": None, "markdown": hero_markdown},
    }
    for block in blocks:
        payload.setdefault(
            block.key, {"heading": block.heading, "markdown": "Some section copy here."}
        )
    payload.update(overrides)
    return payload


# ── 1. correct brand integration passes ─────────────────────────────────────


@pytest.mark.unit
def test_compliant_brand_integration_validates():
    model, blocks = _landing_model()
    with brand_retry_budget(1):
        obj = model.model_validate(_payload(blocks, _COMPLIANT_HERO))
    assert obj.title == "Cut onboarding time"


@pytest.mark.unit
def test_a_content_type_with_no_placement_rule_only_needs_presence():
    """glossary is intensity="none" — position is not graded, presence still is."""
    outline = apply_brand_slot_to_outline(
        {
            "promote_brand": True,
            "brand_voice_promotion": dict(_PROMO),
            "terms": [{"term": "Onboarding", "definition": "d"}],
        },
        "glossary",
    )
    model, blocks = build_structured_content_model(
        outline, "glossary", get_generated_content_model("glossary")
    )
    payload = {
        "title": "Glossary",
        "introduction": "Terms.",
        **{
            b.key: {"heading": b.heading, "markdown": f"For example, {BRAND} is one such tool."}
            for b in blocks
        },
    }
    with brand_retry_budget(1):
        assert model.model_validate(payload) is not None


# ── 2. missing or misplaced integration is detected ─────────────────────────


@pytest.mark.unit
def test_a_missing_brand_mention_is_rejected():
    model, blocks = _landing_model()
    with brand_retry_budget(1):
        with pytest.raises(ValidationError) as exc:
            model.model_validate(_payload(blocks, _BRANDLESS_HERO))

    message = str(exc.value)
    assert "BRAND REQUIREMENT NOT MET" in message
    assert BRAND in message


@pytest.mark.unit
def test_a_misplaced_brand_mention_is_rejected():
    """landing-page is hero-anchored: naming the brand only in a later section
    does not satisfy the policy, and the rejection must say so."""
    model, blocks = _landing_model()
    payload = _payload(
        blocks,
        _BRANDLESS_HERO,
        benefits={
            "heading": "Benefits",
            "markdown": f"{BRAND} halves new-hire ramp time for support teams.",
        },
    )
    with brand_retry_budget(1):
        with pytest.raises(ValidationError) as exc:
            model.model_validate(payload)

    assert "HERO" in str(exc.value)


@pytest.mark.unit
def test_the_rejection_message_carries_an_actionable_instruction():
    model, blocks = _landing_model()
    with brand_retry_budget(1):
        with pytest.raises(ValidationError) as exc:
            model.model_validate(_payload(blocks, _BRANDLESS_HERO))

    message = str(exc.value)
    # The same structural anchor the prompt and schema already carry.
    assert "STRUCTURAL" in message
    assert "Rewrite the affected section" in message


# ── 3. it can never become a failure point ──────────────────────────────────


@pytest.mark.unit
def test_the_budget_is_spent_once_and_then_disarms():
    """The bound that makes this safe: one rejection, then the content is
    accepted and the existing repair loop takes over."""
    model, blocks = _landing_model()
    bad = _payload(blocks, _BRANDLESS_HERO)

    with brand_retry_budget(1):
        with pytest.raises(ValidationError):
            model.model_validate(bad)
        # Every subsequent attempt passes — no unbounded regeneration.
        assert model.model_validate(bad) is not None
        assert model.model_validate(bad) is not None


@pytest.mark.unit
def test_without_a_granted_budget_the_validator_never_raises():
    """Default-off: any caller that has not opted in is unaffected."""
    model, blocks = _landing_model()
    assert model.model_validate(_payload(blocks, _BRANDLESS_HERO)) is not None


@pytest.mark.unit
def test_a_zero_budget_never_raises():
    model, blocks = _landing_model()
    with brand_retry_budget(0):
        assert model.model_validate(_payload(blocks, _BRANDLESS_HERO)) is not None


@pytest.mark.unit
def test_a_malformed_payload_does_not_raise_a_brand_error():
    """A response bad enough to break assembly must fail on its own terms (or
    pass), never with a brand error — the validator swallows its own faults."""
    model, blocks = _landing_model()
    payload = _payload(blocks, _COMPLIANT_HERO)
    payload["introduction"] = None  # optional field, tolerated

    with brand_retry_budget(1):
        obj = model.model_validate(payload)
    assert obj is not None


@pytest.mark.unit
def test_a_warning_severity_placement_result_does_not_reject():
    """`check_brand_placement_policy` returns `warning` for softer cases, and
    repair_content ignores warnings. Rejecting on them would spend a whole
    regeneration on something the rest of the pipeline tolerates."""
    outline = apply_brand_slot_to_outline(
        {
            "promote_brand": True,
            "brand_voice_promotion": dict(_PROMO),
            "structure": {
                "sections": [
                    {"heading": "Why ramp stalls", "key_points": ["unclear ownership"]},
                    {"heading": "How to fix it", "key_points": ["write it down"]},
                ]
            },
        },
        "blog",
    )
    model, blocks = build_structured_content_model(
        outline, "blog", get_generated_content_model("blog")
    )
    # blog is body_only: a mention in the introduction is a warning, not blocking.
    payload = {
        "title": "Why onboarding stalls",
        "introduction": f"{BRAND} halves new-hire ramp time, which is why ramp stalls.",
        **{b.key: {"heading": b.heading, "markdown": "Body copy."} for b in blocks},
    }
    with brand_retry_budget(1):
        assert model.model_validate(payload) is not None


# ── 4. nothing about the existing structure changed ─────────────────────────


@pytest.mark.unit
def test_the_validator_adds_no_fields_and_removes_none():
    """It inspects the response; it does not reshape it."""
    approved, _ = _landing_model(promote=True)
    unapproved, _ = _landing_model(promote=False)

    assert set(approved.model_fields) == set(unapproved.model_fields)


@pytest.mark.unit
def test_no_validator_is_attached_when_the_brand_is_not_approved():
    model, blocks = _landing_model(promote=False)
    # No budget, no brand, no rejection — and nothing to disarm.
    assert model.model_validate(_payload(blocks, _BRANDLESS_HERO)) is not None
    with brand_retry_budget(1):
        assert model.model_validate(_payload(blocks, _BRANDLESS_HERO)) is not None


@pytest.mark.unit
def test_the_spec_slice_carries_only_brand_keys():
    """Sliced deliberately: the model is cached and reused across articles, so a
    whole spec in the closure would be read stale on the next one."""
    slice_ = build_brand_spec_slice(_landing_outline(), "landing-page")

    assert set(slice_) == {"brand_context", "brand_placement", "brand_placement_policy"}
    assert slice_["brand_context"]["brand_name"] == BRAND


@pytest.mark.unit
def test_no_spec_slice_when_the_brand_is_not_approved():
    assert build_brand_spec_slice(_landing_outline(promote=False), "landing-page") is None
