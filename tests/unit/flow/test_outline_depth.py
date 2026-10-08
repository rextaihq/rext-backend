"""Outlines come back with their main sections and whole budgets (revnix/rext-control#837).

Since an outline may nest H3s, the model returned one or two H2s with every other topic under
them, and gave every section the 80 to 120 words meant for an H2 that only introduces its H3s:
a blog planned at 700 to 800 words. The prompt says both rules; `outline_depth` holds them.
"""

import pytest

from src.flow.engines.content.generation.outline_depth import (
    fill_main_budgets,
    fit_budgets,
    hold_main_sections,
    hold_plan_inside_its_range,
    raise_subsections,
)
from src.flow.model.structure.outlines import plan_ceiling, target_word_count_range
from src.flow.model.structure.outlines.infomational.blog import ContentStructure
from src.flow.prompts.human.outline import outline_subsection_rule


def _section(heading, level="H2", words=200):
    return {
        "heading": heading,
        "heading_level": level,
        "description": f"What {heading} covers.",
        "key_points": [f"{heading} one", f"{heading} two"],
        "suggested_word_count": words,
    }


def _levels(sections):
    return [(section["heading"], section["heading_level"]) for section in sections]


# The outline a real run returned for "email newsletter ideas for small business".
NESTED = [
    _section("10 Creative Email Newsletter Ideas", "H2", 300),
    _section("Templates and Examples", "H3"),
    _section("What Topics Work Best", "H3"),
    _section("Funny Newsletter Ideas", "H3"),
    _section("Ideas for Customer Engagement", "H3"),
    _section("Seasonal and Holiday Themes", "H3"),
    _section("How to Measure Success", "H3"),
    _section("FAQ Section", "H2", 300),
]


def test_two_main_sections_with_everything_nested_become_main_sections():
    sections, raised = raise_subsections(NESTED)

    assert raised == 6
    assert [level for _, level in _levels(sections)] == ["H2"] * 8
    # Levels only: the headings, their order, their points and their budgets are the model's.
    assert [s["heading"] for s in sections] == [s["heading"] for s in NESTED]
    assert [s["key_points"] for s in sections] == [s["key_points"] for s in NESTED]
    assert NESTED[1]["heading_level"] == "H3"  # the input is not changed


def test_an_outline_with_its_main_sections_keeps_its_subsections():
    outline = [
        _section("Why plan"),
        _section("Choose the spot"),
        _section("Sun hours", "H3"),
        _section("Soil", "H3"),
        _section("Timing"),
        _section("Takeaways"),
    ]

    sections, raised = raise_subsections(outline)

    assert raised == 0 and _levels(sections) == _levels(outline)


def test_the_largest_family_is_raised_together_and_the_rest_stay_nested():
    outline = [
        _section("Tools"),
        _section("Free tools", "H3"),
        _section("Paid tools", "H3"),
        _section("Trials", "H3"),
        _section("Mistakes"),
        _section("One mistake", "H3"),
    ]

    sections, raised = raise_subsections(outline)

    assert raised == 3
    assert _levels(sections)[1:4] == [("Free tools", "H2"), ("Paid tools", "H2"), ("Trials", "H2")]
    assert _levels(sections)[5] == ("One mistake", "H3")


def test_never_more_than_eight_main_sections_and_nothing_invented():
    crowded = [_section("One")] + [_section(f"Part {n}", "H3") for n in range(1, 12)]
    sections, raised = raise_subsections(crowded)

    assert raised == 7
    assert sum(1 for s in sections if s["heading_level"] == "H2") == 8
    # The last seven are raised: the four left are still under the H2 they were written under.
    assert _levels(sections)[:5] == [
        ("One", "H2"),
        ("Part 1", "H3"),
        ("Part 2", "H3"),
        ("Part 3", "H3"),
        ("Part 4", "H3"),
    ]
    assert all(level == "H2" for _, level in _levels(sections)[5:])
    # Two H2s and no H3s to raise: left as it is.
    flat = [_section("One"), _section("Two")]
    assert raise_subsections(flat) == (flat, 0)


def test_a_raised_subsections_own_h4s_become_its_h3s():
    outline = [
        _section("Guide"),
        _section("Step one", "H3"),
        _section("A detail", "H4"),
        _section("Step two", "H3"),
        _section("Step three", "H3"),
    ]

    sections, _ = raise_subsections(outline)

    assert _levels(sections) == [
        ("Guide", "H2"),
        ("Step one", "H2"),
        ("A detail", "H3"),
        ("Step two", "H2"),
        ("Step three", "H2"),
    ]


def test_an_outline_with_no_main_section_at_all_gets_them():
    orphans = [_section(f"Topic {n}", "H3") for n in range(1, 7)]

    sections, raised = raise_subsections(orphans)

    assert raised == 6 and {level for _, level in _levels(sections)} == {"H2"}
    # Subsections before the first section are main sections; the ones after it are its own.
    opening = [_section("Basics", "H3"), _section("Setup"), _section("Step", "H3")]
    assert _levels(raise_subsections(opening, least=1)[0]) == [
        ("Basics", "H2"),
        ("Setup", "H2"),
        ("Step", "H3"),
    ]


def test_a_detail_under_a_raised_subsection_is_never_raised_in_turn():
    pillar = [
        _section("Guide"),
        _section("Part one", "H3"),
        _section("Detail a", "H4"),
        _section("Detail b", "H4"),
        _section("Detail c", "H4"),
    ]

    sections, raised = raise_subsections(pillar)

    # One subsection to raise: two main sections is all this outline holds.
    assert raised == 1
    assert _levels(sections) == [
        ("Guide", "H2"),
        ("Part one", "H2"),
        ("Detail a", "H3"),
        ("Detail b", "H3"),
        ("Detail c", "H3"),
    ]


def test_an_outline_with_more_main_sections_than_the_ceiling_is_left_as_written():
    """The ceiling limits what is raised. A pillar page may hold more than eight H2s, and a
    blog with more is its schema's to refuse."""
    long_pillar = [_section(f"Chapter {n}") for n in range(1, 11)] + [_section("Aside", "H3")]

    sections, raised = raise_subsections(long_pillar)

    assert raised == 0 and _levels(sections) == _levels(long_pillar)


def test_a_section_without_subsections_gets_a_whole_budget():
    outline = [
        _section("Intro to the tools", "H2", 100),
        _section("Free tools", "H3", 100),
        _section("Pricing", "H2", 120),
        _section("Takeaways", "H2", 250),
    ]

    sections, lifted = fill_main_budgets(outline)

    assert lifted == 1
    # The H2 that introduces its H3s keeps its short budget; the H3 keeps its own.
    assert [s["suggested_word_count"] for s in sections] == [100, 100, 200, 250]


def test_a_generated_outline_is_held_in_place_and_stays_valid():
    outline = {"structure": {"sections": [dict(s, suggested_word_count=120) for s in NESTED]}}

    raised, lifted = hold_main_sections(outline)

    sections = outline["structure"]["sections"]
    assert (raised, lifted) == (6, 8)
    assert sum(s["suggested_word_count"] for s in sections) == 8 * 200
    ContentStructure(sections=sections)  # still a blog's structure: at most 8 H2s, 16 entries


@pytest.mark.parametrize(
    "outline",
    [
        {"steps": {"steps": [{"title": "Measure"}]}},
        {"structure": {"sections": [{"heading": "One"}, {"heading": "Two"}]}},
        {"structure": {"sections": []}},
        {},
    ],
)
def test_an_outline_without_levelled_sections_is_left_alone(outline):
    before = repr(outline)

    assert hold_main_sections(outline) == (0, 0)
    assert repr(outline) == before


@pytest.mark.parametrize(
    ("content_type", "count"), [("blog", "4 to 8"), ("pillar-content", "at least 4")]
)
def test_the_prompt_says_main_sections_come_first(content_type, count):
    rule = outline_subsection_rule(content_type)

    assert f"MAIN SECTIONS COME FIRST: {count} H2s, always." in rule
    assert "An H3 never stands in for a main section" in rule


def test_the_prompt_keeps_the_short_budget_for_an_h2_that_has_h3s_only():
    rule = outline_subsection_rule("blog")

    assert "An H2 that has H3s keeps a short budget of its own" in rule
    assert "An H2 WITHOUT H3s is a whole section and keeps a whole budget: 200 to 400 words" in rule
    # The types whose schema fixes the structure are told nothing about H2 counts.
    assert "MAIN SECTIONS COME FIRST" not in outline_subsection_rule("how-to-guide")


def test_the_five_outlines_measured_before_the_change_come_out_longer():
    """Budgets as five real outlines had them on 8 October (all H2s but where marked): each was
    planned at the type's minimum of 800 words or little more."""
    before = {
        "email newsletter ideas": [150, 100, 100, 120, 150],
        "benefits of standing desks": [120, 100, 100, 100],
        "remote work productivity tips": [125, ("H3", 100), ("H3", 100), 150, 150, 150, 100, 100],
    }
    for keyword, budgets in before.items():
        sections = [
            _section(f"{keyword} {index}", *(b if isinstance(b, tuple) else ("H2", b)))
            for index, b in enumerate(budgets)
        ]
        outline = {"structure": {"sections": sections}}

        hold_main_sections(outline)

        held = outline["structure"]["sections"]
        total = sum(s["suggested_word_count"] for s in held)
        assert sum(1 for s in held if s["heading_level"] == "H2") >= 4, keyword
        assert total >= 200 * 4, keyword
        assert total > sum(b[1] if isinstance(b, tuple) else b for b in budgets), keyword


# -- A plan inside the range the product shows for its type (rext-control#837) -------------


def _planned(*budgets, levels=None):
    levels = levels or ["H2"] * len(budgets)
    return [
        {"heading": f"Part {n}", "heading_level": level, "suggested_word_count": words}
        for n, (level, words) in enumerate(zip(levels, budgets, strict=True), 1)
    ]


def test_a_plan_over_its_types_range_comes_down_by_the_same_share_everywhere():
    """Staging, 8 October: eight whole sections planned 2,150 words for a blog the product
    calls 800 to 2,000."""
    sections = _planned(350, 300, 300, 300, 250, 250, 200, 200)

    fitted, removed = fit_budgets(sections, 2000)

    budgets = [section["suggested_word_count"] for section in fitted]
    assert budgets == [320, 270, 270, 270, 230, 230, 200, 200]
    assert sum(budgets) <= 2000 and removed == 2150 - sum(budgets)
    # The plan keeps its shape, and what was given is not changed.
    assert budgets == sorted(budgets, reverse=True)
    assert sections[0]["suggested_word_count"] == 350


def test_a_plan_inside_its_range_is_left_alone():
    sections = _planned(300, 300, 400, 300, 300, 300)

    fitted, removed = fit_budgets(sections, 2000)

    assert removed == 0 and fitted == sections


def test_no_whole_section_is_taken_under_its_budget_and_no_subsection_under_half():
    levels = ["H2", "H3", "H3", "H2", "H2", "H2", "H2", "H2", "H2", "H2"]
    sections = _planned(120, 400, 400, 400, 400, 400, 400, 400, 400, 400, levels=levels)

    fitted, _ = fit_budgets(sections, 2000)

    budgets = [section["suggested_word_count"] for section in fitted]
    # 3,720 words asked: every budget gives the same share, down to its floor.
    assert budgets[0] == 100  # an H2 that only introduces its H3s: half a whole budget at least
    assert budgets[1:3] == [210, 210]
    assert all(words >= 200 for words in budgets[3:])


def test_a_section_without_a_budget_counts_as_a_whole_one_and_is_left_as_it_is():
    sections = _planned(400, 400, 400, 400, 400, 400)
    del sections[2]["suggested_word_count"]

    fitted, removed = fit_budgets(sections, 2000)

    assert "suggested_word_count" not in fitted[2]
    assert removed > 0
    assert sum(section.get("suggested_word_count", 200) for section in fitted) <= 2000


def test_only_a_type_whose_range_is_narrower_than_its_model_is_held():
    blog = {"structure": {"sections": _planned(400, 400, 400, 400, 400, 400)}}
    pillar = {"structure": {"sections": _planned(400, 400, 400, 400, 400, 400)}}

    assert plan_ceiling("blog") == 2000
    assert hold_plan_inside_its_range(blog, plan_ceiling("blog")) == 2400 - 1980
    assert sum(s["suggested_word_count"] for s in blog["structure"]["sections"]) == 1980
    # A type whose model declares its own range has no ceiling here: nothing is held.
    assert plan_ceiling("pillar-content") is None
    assert hold_plan_inside_its_range(pillar, plan_ceiling("pillar-content")) == 0
    assert sum(s["suggested_word_count"] for s in pillar["structure"]["sections"]) == 2400
    # An outline with no section list (a how-to's steps) has nothing to hold.
    assert hold_plan_inside_its_range({"steps": {"steps": []}}, 2000) == 0


def test_a_type_nobody_knows_is_given_the_blogs_model_and_held_as_a_blog():
    """Review round 1: the outline model falls back to the blog's for an unknown type."""
    assert plan_ceiling("newsletter-digest") == 2000
    assert target_word_count_range("newsletter-digest") == (800, 2000)


def test_the_range_an_approval_is_checked_against_is_the_products():
    """Review round 1: a client that asks for a 3,000-word blog at approval is not let past
    the range the outline step holds a blog's plan to. Every other type keeps its model's."""
    assert target_word_count_range("blog") == (800, 2000)
    assert target_word_count_range("pillar-content") == (4500, 6000)
    assert target_word_count_range("how-to-guide") == (1500, 3000)
    assert target_word_count_range("white-paper")[1] == 15000
