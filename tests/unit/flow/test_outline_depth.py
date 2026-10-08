"""Outlines come back with their main sections and whole budgets (revnix/rext-control#837).

Since an outline may nest H3s, the model returned one or two H2s with every other topic under
them, and gave every section the 80 to 120 words meant for an H2 that only introduces its H3s:
a blog planned at 700 to 800 words. The prompt says both rules; `outline_depth` holds them.
"""

import pytest

from src.flow.engines.content.generation.outline_depth import (
    fill_main_budgets,
    hold_main_sections,
    raise_subsections,
)
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


@pytest.mark.parametrize("content_type", ["blog", "pillar-content"])
def test_the_prompt_says_main_sections_come_first(content_type):
    rule = outline_subsection_rule(content_type)

    assert "MAIN SECTIONS COME FIRST: 4 to 8 H2s, always." in rule
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
