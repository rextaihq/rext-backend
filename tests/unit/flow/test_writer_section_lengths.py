"""The writer's plan fits what the checks accept (revnix/rext-control#787, #760 item 13).

Two things the writer was asked for that the checks then refused:

* a minimum per section taken from the target alone. Eleven sections at a 1,500-word target
  were each told "150 words at least", 1,650 before the introduction, where the check accepts
  1,680 with it. Staging articles came back at 2,119 words for 1,500 asked.
* a brand mention "inside the first 30% of the article", which nobody writing can measure.
  The one subtle mention landed at 31% and two repairs left it there.
"""

import copy
import re

import pytest

from src.flow.engines.agent.middleware.persona_middleware import PersonaInjectionMiddleware
from src.flow.engines.content.generation.brand_slot import (
    _slot_body_section,
    sections_inside_window,
)
from src.flow.engines.content.generation.requirements_spec import build_requirements_spec
from src.flow.engines.content.generation.structured_body import (
    early_body_sections,
    planned_section_count,
    planned_step_count,
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

    # Ten entries of 150 words behind an opening of 180: the third starts at 29% of the plan
    # and its middle is at 33%, past the window the check measures. Two are named, not the
    # three a count of sections gives.
    assert early_body_sections(outline, "blog", 0.3) == ["Step 1", "Step 2"]
    # A short plan still names a section to use.
    assert early_body_sections(_outline(sections=2), "blog", 0.3) == ["Step 1"]


def test_the_window_is_counted_in_planned_words_not_in_sections():
    """Review round 2: two long sections first, and the third of ten begins past the first
    30% of the body. Counted by sections it was inside, and the writer sent there failed."""
    long_start = [{**_section("Long 1"), "suggested_word_count": 400}] + [
        {**_section("Long 2"), "suggested_word_count": 400}
    ]
    rest = [_section(f"Part {n}") for n in range(3, 11)]

    # 2,000 planned words behind an opening of 200: the window ends at 660 words, the first
    # section's middle is at 400, the second's at 800.
    assert sections_inside_window(long_start + rest, 0.3) == 1
    # Four short sections first: they fit, and so does the long one after them, whose middle
    # (720 words in) is still inside a window that now ends at 756.
    short_start = [{**_section(f"Short {n}"), "suggested_word_count": 80} for n in range(1, 5)]
    assert sections_inside_window(short_start + long_start + rest, 0.3) == 5


@pytest.mark.parametrize("entries", range(1, 17))
def test_a_list_without_budgets_is_counted_by_its_sections(entries):
    sections = [{"heading": f"Part {n}"} for n in range(1, entries + 1)]

    assert sections_inside_window(sections, 0.3) == max(1, int(entries * 0.3))


def test_a_section_without_a_budget_weighs_what_the_others_do():
    sections = [_section(f"Part {n}") for n in range(1, 11)]
    for section in sections[:3]:
        del section["suggested_word_count"]

    assert sections_inside_window(sections, 0.3) == 2


@pytest.mark.parametrize("entries", range(1, 17))
def test_the_named_window_is_the_brand_slots_own_window(entries):
    """brand_slot.py reserves its section among the leading ones the window holds; naming any
    other set would give the writer two places for one mention. Whichever section suits the
    brand best, the slot is reserved in one that was named, and is then the one named."""
    sections = [_section(f"Part {n}") for n in range(1, entries + 1)]
    for number, section in enumerate(sections, 1):
        section["key_points"] = [f"topic{number} matters"]
    outline = {
        "title": "T",
        "hero": {"headline": "T", "subheadline": "S"},
        "structure": {"sections": sections},
        "faqs": {"faqs": [{"question": "Q?", "answer": "A."}]},
    }
    named = early_body_sections(outline, "blog", 0.3)
    assert named == [f"Part {n}" for n in range(1, sections_inside_window(sections, 0.3) + 1)]

    for suits in range(1, entries + 1):
        reserved_in = copy.deepcopy(outline)
        written = _slot_body_section(
            reserved_in, {"about": f"All about topic{suits}"}, "Acme Tools", "blog"
        )

        assert sections[written.section_index]["heading"] in named
        if suits <= len(named):
            assert written.section_index == suits - 1
        assert early_body_sections(reserved_in, "blog", 0.3) == [
            f"Part {written.section_index + 1}"
        ]


def test_a_reserved_brand_slot_is_the_one_section_named():
    from src.flow.engines.content.generation.brand_slot import SLOT_LINE_PREFIX

    outline = _outline(sections=9)
    outline["structure"]["sections"][2]["key_points"].append(
        f"{SLOT_LINE_PREFIX} Acme Tools here — the planner that maps sun hours."
    )

    assert early_body_sections(outline, "blog", 0.3) == ["Step 3"]


def test_a_slot_reserved_outside_the_section_list_is_left_to_speak_for_itself():
    from src.flow.engines.content.generation.brand_slot import SLOT_LINE_PREFIX

    outline = {
        "title": "How to plan a vegetable garden",
        "hero": {"headline": "How to plan a vegetable garden", "subheadline": "Before you dig."},
        "user_context": {"who_this_is_for": "First-time gardeners"},
        "prerequisites": {"items": [f"{SLOT_LINE_PREFIX} Acme Tools here."]},
        "summary": {"recap": "Plan, then dig."},
    }

    assert early_body_sections(outline, "how-to-guide", 0.3) == []


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


def _how_to(steps):
    return {
        "title": "How to plan a vegetable garden",
        "hero": {"headline": "How to plan a vegetable garden", "subheadline": "Before you dig."},
        "user_context": {"who_this_is_for": "First-time gardeners"},
        "prerequisites": {"items": ["A patch of ground"]},
        "steps": {
            "steps": [
                {"title": f"Do part {number} of the plan", "description": "How."}
                for number in range(1, steps + 1)
            ]
        },
        "summary": {"recap": "Plan, then dig."},
    }


def test_a_how_to_guides_steps_are_planned_inside_the_target_not_on_top_of_it():
    """Ten steps written in full are a thousand words nobody planned unless they have a share
    of the target: each weighs a third of a section (rext-control #817)."""
    outline = _how_to(10)
    assert planned_section_count(outline, "how-to-guide") == 4
    assert planned_step_count(outline, "how-to-guide") == 10

    prompt = PersonaInjectionMiddleware()._build_full_content_prompt(
        None, outline, target_word_count=1500, content_type="how-to-guide"
    )

    plan = plan_section_lengths(1500, 4 + 4)  # ten steps weigh as four sections (rounded up)
    assert f"about {plan.average_low}-{plan.average_high} words" in prompt
    per_step = f"about {plan.average_low // 3}-{plan.average_high // 3} words each ON AVERAGE"
    assert "Its 10 steps (the `step_1` to `step_10` fields)" in prompt and per_step in prompt
    # Every section and every step at its average keeps the body inside its range.
    assert 4 * plan.average_high + 10 * (plan.average_high // 3) <= plan.body_max
    # And a step still has room for several sentences: 47 to 62 words here.
    assert (plan.average_low // 3, plan.average_high // 3) == (47, 62)


def test_an_article_without_step_fields_is_told_nothing_about_steps():
    assert planned_step_count(_outline(), "blog") == 0
    assert "steps (the `step_1`" not in _prompt(_outline(), 1500)
    assert planned_step_count(_how_to(0), "how-to-guide") == 0


@pytest.mark.parametrize("content_type", ["documentation", "contact-us"])
def test_a_placement_that_is_not_an_early_body_section_is_told_none(content_type):
    """Documentation's one allowed mention is a closing note; a contact page's belongs in its
    opening block. Neither is sent to "an early body section", so neither is told which ones."""
    outline = _outline(sections=9, promote_brand=True, brand_voice_promotion=BRAND)

    assert "an early body section means" in _prompt(outline, 1500)
    told = PersonaInjectionMiddleware()._build_full_content_prompt(
        None, outline, target_word_count=1500, content_type=content_type
    )
    assert "PLACEMENT REQUIREMENT FOR THIS CONTENT TYPE" in told
    assert "an early body section means" not in told


def test_a_subtle_mention_is_told_its_sections_and_a_prominent_one_is_not():
    subtle = _outline(
        sections=9, promote_brand=True, brand_prominence="subtle", brand_voice_promotion=BRAND
    )
    prominent = {**subtle, "brand_prominence": "prominent"}

    told = _prompt(subtle, 1500)

    assert 'an early body section means: "Step 1" or "Step 2". The first mention' in told
    assert "goes there, in the first half of that section" in " ".join(told.split())
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


def test_a_heading_inside_a_fenced_example_is_no_section_to_send_the_repair_to():
    """Review round 2: a line of a code block that looks like an H2 is not one a reader sees."""
    filler = ("Sun hours decide what grows where. " * 12).strip()
    sections = "\n\n".join(f"## Step {number}\n\n{filler}" for number in range(1, 11))
    body = sections.replace(
        "## Step 2\n\n", "## Step 2\n\n```markdown\n## Not a Section\n```\n\n", 1
    ).replace("## Step 5\n\nSun hours", "## Step 5\n\nAcme Tools maps them for you. Sun hours", 1)
    outline = _outline(promote_brand=True, brand_prominence="subtle", brand_voice_promotion=BRAND)
    article = {"title": outline["title"], "introduction": "Plan.", "body_markdown": body}

    result = check_brand_placement_policy(article, build_requirements_spec(outline, "blog"))

    assert result["passed"] is False
    assert "Not a Section" not in result["detail"]
    assert 'that means the section "Step 2"' in result["detail"]


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
