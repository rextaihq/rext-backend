"""The writer's plan fits what the checks accept (revnix/rext-control#787, #760 item 13).

Two things the writer was asked for that the checks then refused:

* a minimum per section taken from the target alone. Eleven sections at a 1,500-word target
  were each told "150 words at least", 1,650 before the introduction, where the check accepts
  1,680 with it. Staging articles came back at 2,119 words for 1,500 asked.
* a brand mention "inside the first 30% of the article", which nobody writing can measure.
  The one subtle mention landed at 31% and two repairs left it there.
"""

import re

import pytest

from src.flow.engines.agent.middleware.persona_middleware import PersonaInjectionMiddleware
from src.flow.engines.content.generation.requirements_spec import build_requirements_spec
from src.flow.engines.content.generation.structured_body import (
    early_body_sections,
    planned_section_count,
)
from src.flow.engines.content.generation.validation import check_brand_placement_policy
from src.flow.engines.content.generation.word_count_utils import (
    compute_word_target_band,
    plan_section_lengths,
)

BRAND = {
    "brand_name": "Acme Tools",
    "brand_url": "https://www.acme.test/",
    "about": "Acme Tools makes a planner for vegetable gardens.",
    "selling_position": "The planner that maps sun hours.",
}


def _section(heading, level="H2"):
    return {
        "heading": heading,
        "heading_level": level,
        "description": f"What {heading} covers.",
        "key_points": [f"{heading} point one"],
        "suggested_word_count": 150,
    }


def _outline(sections=8, **extra):
    return {
        "title": "How to plan a vegetable garden",
        "hero": {"headline": "How to plan a vegetable garden", "subheadline": "Before you dig."},
        "structure": {
            "sections": [
                *[_section(f"Step {number}") for number in range(1, sections + 1)],
                _section("A detail of the last step", "H3"),
            ]
        },
        "faqs": {"faqs": [{"question": "When do I start?", "answer": "In spring."}]},
        "final_cta": {"primary_cta": "Start planning today"},
        **extra,
    }


def _prompt(outline, target):
    return PersonaInjectionMiddleware()._build_full_content_prompt(
        None, outline, target_word_count=target, content_type="blog"
    )


# --- the lengths ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("target", "sections"), [(600, 12), (800, 7), (1500, 11), (2000, 10), (3000, 8)]
)
def test_every_section_at_its_floor_still_fits_the_band(target, sections):
    plan = plan_section_lengths(target, sections)
    low, high = compute_word_target_band(target)

    assert (plan.total_min, plan.total_max) == (low, high)
    assert plan.section_min * sections + plan.intro_words <= low
    # The average the writer is told keeps the whole inside the band.
    assert plan.average_high * sections + plan.intro_words <= high
    assert plan.average_low * sections + plan.intro_words >= low
    assert plan.subsection_min <= plan.section_min


def test_the_old_floor_alone_was_more_than_the_band_accepts():
    plan = plan_section_lengths(1500, 11)

    # A tenth of the target per section: 150 x 11 + the introduction is past 1,680.
    assert 150 * 11 + plan.intro_words > plan.total_max
    assert plan.section_min == 78


def test_a_floor_that_already_fits_is_not_raised_and_no_count_keeps_the_old_one():
    assert plan_section_lengths(3000, 4).section_min == 300
    assert plan_section_lengths(1500, 0).section_min == 150


def test_the_writer_is_told_floors_that_fit_this_articles_sections():
    outline = _outline(sections=9)
    sections = planned_section_count(outline, "blog")
    prompt = _prompt(outline, 1500)

    # The opening, nine sections and the FAQ; not the H3, and not the call to action.
    assert sections == 11
    floor = int(re.search(r"Every H2 section: minimum (\d+) words", prompt).group(1))
    low, high = compute_word_target_band(1500)
    assert floor * sections + 180 <= low
    average = re.search(r"has 11 H2 sections: about (\d+)-(\d+) words each ON AVERAGE", prompt)
    assert average and int(average.group(2)) * sections + 180 <= high
    assert f"OVER {high} words fails the same check" in prompt
    assert f"only while the total is under {low} words" in prompt


# --- where an early mention goes ------------------------------------------------------


def test_the_early_body_sections_are_named_from_the_plan():
    outline = _outline(sections=9)

    # Eleven sections, the first 30%: three of them, the opening left out.
    assert early_body_sections(outline, "blog", 0.3) == ["Step 1", "Step 2"]
    # A short plan still names a section to use.
    assert early_body_sections(_outline(sections=2), "blog", 0.3) == ["Step 1"]


def test_a_block_a_typed_field_owns_is_no_section_of_the_body():
    """A how-to guide's steps are written through the content model's own `steps` field, not
    as a prose block: they are neither counted nor named as a place for the mention."""
    outline = {
        "title": "How to plan a vegetable garden",
        "hero": {"headline": "How to plan a vegetable garden", "subheadline": "Before you dig."},
        "user_context": {"who_this_is_for": "First-time gardeners"},
        "prerequisites": {"items": ["A patch of ground"]},
        "steps": {"steps": [{"title": "Measure the plot", "instruction": "Use a tape."}]},
        "summary": {"recap": "Plan, then dig."},
    }

    assert planned_section_count(outline, "how-to-guide") == 4
    assert early_body_sections(outline, "how-to-guide", 0.3) == ["User Context"]


def test_a_type_that_takes_no_promotion_is_not_told_an_early_section():
    """Documentation's one allowed mention is a closing note, and its position is not graded."""
    outline = _outline(sections=9, promote_brand=True, brand_voice_promotion=BRAND)

    assert "an early body section means" in _prompt(outline, 1500)
    told = PersonaInjectionMiddleware()._build_full_content_prompt(
        None, outline, target_word_count=1500, content_type="documentation"
    )
    assert "an early body section means" not in told


def test_a_subtle_mention_is_told_its_sections_and_a_prominent_one_is_not():
    subtle = _outline(
        sections=9, promote_brand=True, brand_prominence="subtle", brand_voice_promotion=BRAND
    )
    prominent = {**subtle, "brand_prominence": "prominent"}

    told = _prompt(subtle, 1500)

    assert 'an early body section means: "Step 1" or "Step 2"' in told
    assert "an early body section means" not in _prompt(prominent, 1500)


def test_a_late_first_mention_is_told_which_sections_are_early_enough():
    sections = "\n\n".join(
        f"## Step {number}\n\n" + ("Sun hours decide what grows where. " * 12).strip()
        for number in range(1, 11)
    )
    body = sections.replace(
        "## Step 5\n\nSun hours", "## Step 5\n\nAcme Tools maps them for you. Sun hours", 1
    )
    outline = _outline(promote_brand=True, brand_prominence="subtle", brand_voice_promotion=BRAND)
    article = {
        "title": outline["title"],
        "introduction": "Plan before you dig.",
        "body_markdown": body,
    }

    result = check_brand_placement_policy(article, build_requirements_spec(outline, "blog"))

    assert result["passed"] is False
    assert "first appears at 39% through the body" in result["detail"]
    # Steps 1 to 3 end inside the first 30%; the opening one is left out.
    assert 'that means the section "Step 2" or "Step 3"' in result["detail"]


def test_when_the_first_section_is_longer_than_the_window_the_repair_is_sent_to_its_opening():
    body = (
        "## Step 1\n\n"
        + ("Sun hours decide what grows where. " * 40).strip()
        + " Acme Tools maps them for you.\n\n## Step 2\n\n"
        + ("Soil comes next. " * 20).strip()
    )
    outline = _outline(promote_brand=True, brand_prominence="subtle", brand_voice_promotion=BRAND)
    article = {
        "title": outline["title"],
        "introduction": "Plan before you dig.",
        "body_markdown": body,
    }

    result = check_brand_placement_policy(article, build_requirements_spec(outline, "blog"))

    assert result["passed"] is False
    assert 'that means the opening paragraphs of "Step 1"' in result["detail"]
