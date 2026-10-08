"""The rewrite, one section at a time (revnix/rext-control#787).

Told a whole article's length, the rewrite's model wrote to a length of its own: a draft that
was right at 1,493 words was saved at 2,019. Told one section's, it keeps to it. The article is
split at its H2s, each part is rewritten on its own and all at once, and a part whose rewrite
cannot be used is kept as it was drafted.
"""

import asyncio
from types import SimpleNamespace

import pytest

from src.flow.engines.content.generation.generation_brief import brief_for_stage
from src.flow.engines.content.generation.requirements_spec import build_requirements_spec
from src.flow.engines.content.generation.section_rewrite import (
    INTRODUCTION,
    MAX_AT_ONCE,
    OPENING,
    SECTION,
    Part,
    _plain_text,
    accept,
    brand_lines,
    call_to_action_lines,
    hold_the_range,
    join_article,
    judge,
    keyphrase_plan,
    keyword_lines,
    lost_lines,
    rewrite_parts,
    secondary_plan,
    split_article,
    stated_range,
    wanted_scale,
    words,
)
from src.flow.prompts.human.humanize import get_section_rewrite_prompt

SENTENCE = "Plan one week at a time and keep the list short. "


def _text(count: int) -> str:
    """Prose of exactly ``count`` words."""
    return " ".join((SENTENCE * (count // 10 + 1)).split()[:count])


BODY = (
    "![A calendar on a desk](https://img.test/calendar.png)\n\n"
    f"## Plan the Month\n\n{_text(120)}\n\n"
    "```markdown\n## Not a Section\n```\n\n"
    f"### A Detail of the Plan\n\n{_text(60)}\n\n"
    f"## Fill the Calendar\n\n{_text(150)}\n\n"
    f"## Review It on Fridays\n\n{_text(90)}"
)
INTRO = _text(70)


def test_an_article_is_split_at_its_h2s_and_put_back_as_it_was():
    parts = split_article(INTRO, BODY)

    assert [part.kind for part in parts] == [INTRODUCTION, OPENING, SECTION, SECTION, SECTION]
    assert [part.heading for part in parts[2:]] == [
        "## Plan the Month",
        "## Fill the Calendar",
        "## Review It on Fridays",
    ]
    # A line of a fenced example that looks like an H2 starts no part, and an H3 stays with
    # its section.
    assert "## Not a Section" in parts[2].text and "### A Detail of the Plan" in parts[2].text
    assert join_article(parts) == (INTRO, BODY)


def test_a_long_section_is_rewritten_one_sub_section_at_a_time():
    """A list article is one H2 with ten H3s: told that part's length (1,522 words on staging)
    the model wrote to a length of its own, as it does for a whole article."""
    ideas = "\n\n".join(f"### Idea {n}\n\n{_text(110)}" for n in range(1, 6))
    body = (
        f"## Five Ideas Worth Trying\n\n{_text(45)}\n\n{ideas}\n\n"
        f"## A Short One\n\n### Its Only Detail\n\n{_text(90)}"
    )

    parts = split_article("", body)

    assert [part.heading for part in parts] == [
        "## Five Ideas Worth Trying",
        "### Idea 1",
        "### Idea 2",
        "### Idea 3",
        "### Idea 4",
        "### Idea 5",
        # Short enough to be one call, its H3 with it.
        "## A Short One",
    ]
    assert [part.level for part in parts] == [2, 3, 3, 3, 3, 3, 2]
    assert parts[1].title == "Idea 1" and "### Idea 2" not in parts[1].text
    assert join_article(parts) == ("", body)


def test_a_sub_sections_rewrite_may_add_no_heading_of_its_level_or_above():
    part = Part(SECTION, "### Idea 1", f"### Idea 1\n\n{_text(110)}")

    assert accept(part, f"### A Better Idea\n\n{_text(108)}", 110).startswith("### Idea 1\n")
    assert accept(part, f"### Idea 1\n\n{_text(50)}\n\n### Idea 1b\n\n{_text(50)}", 110) is None
    assert accept(part, f"## Ideas\n\n### Idea 1\n\n{_text(100)}", 110) is None


def test_a_body_with_no_h2_is_one_part_and_an_empty_article_none():
    assert [part.kind for part in split_article("", "Only prose here.")] == [OPENING]
    assert split_article("", "") == []
    assert join_article(split_article("An introduction.", "")) == ("An introduction.", "")


@pytest.mark.parametrize(
    ("total", "target", "scale"),
    [
        # Inside the range it is checked against (1,320 to 1,680): the length it has.
        (1493, 1500, 1.0),
        (1330, 1500, 1.0),
        # Outside it, either way: to the target.
        (1800, 1500, 1500 / 1800),
        (1250, 1500, 1500 / 1250),
        # Never by more than a quarter either way.
        (2019, 1500, 0.75),
        (3000, 1500, 0.75),
        (800, 1500, 1.25),
        (0, 1500, 1.0),
        (1500, 0, 1.0),
    ],
)
def test_how_far_the_rewrite_moves_the_articles_length(total, target, scale):
    assert wanted_scale(total, target) == pytest.approx(scale)


def test_a_part_is_told_a_range_a_little_under_the_length_wanted_from_it():
    """The model comes back about an eighth over the middle of the range it is given."""
    low, high = stated_range(180)

    assert (low, high) == (144, 169)
    assert stated_range(1) == (1, 2)
    # Asked to cut, it cuts less than it is told, so a part that must come down is told lower.
    assert stated_range(180, cutting=True) == (128, 153)


def _section(count: int, heading: str = "## Fill the Calendar") -> Part:
    return Part(SECTION, heading, f"{heading}\n\n{_text(count)}")


def test_a_rewritten_section_keeps_the_heading_it_was_drafted_with():
    part = _section(150)

    reworded = accept(part, f"## Filling Up Your Calendar\n\n{_text(148)}", 150)
    without = accept(part, _text(148), 150)
    with_a_preamble = accept(
        part, f"Here is the section.\n\n## Fill the Calendar\n\n{_text(140)}", 150
    )

    assert reworded.splitlines()[0] == "## Fill the Calendar"
    assert "Filling Up" not in reworded
    assert without.startswith("## Fill the Calendar\n\n")
    assert with_a_preamble.startswith("## Fill the Calendar") and "Here is" not in with_a_preamble


@pytest.mark.parametrize(
    ("rewritten", "why"),
    [
        ("", "nothing came back"),
        (
            f"## Fill the Calendar\n\n{_text(80)}\n\n## A New Section\n\n{_text(60)}",
            "a section added",
        ),
        (f"## Fill the Calendar\n\n{_text(190)}", "more than a fifth over what was wanted"),
        (f"## Fill the Calendar\n\n{_text(70)}", "under six tenths of it"),
    ],
)
def test_a_rewrite_that_cannot_be_used_keeps_the_part_as_drafted(rewritten, why):
    assert accept(_section(150), rewritten, 150) is None, why


def test_a_rewrite_that_lost_a_link_or_an_image_keeps_the_part_as_drafted():
    """On a replay a part came back without its internal link; put back afterwards, the link
    landed at the article's end on a line of its own."""
    heading = "## Fill the Calendar"
    link = "[a planning guide](https://site.test/guides/planning/)"
    image = "![A calendar](https://img.test/calendar.png)"
    part = Part(SECTION, heading, f"{heading}\n\n{image}\n\n{_text(100)} See {link}. {_text(40)}")

    without_the_link = f"{heading}\n\n{image}\n\n{_text(140)}"
    without_the_image = f"{heading}\n\n{_text(100)} See {link}. {_text(40)}"
    reworded_anchor = (
        f"{heading}\n\n{image}\n\n{_text(98)} Read [this guide to planning]"
        f"(https://site.test/guides/planning) first. {_text(38)}"
    )

    assert accept(part, without_the_link, 145) is None
    assert accept(part, without_the_image, 145) is None
    # The anchor's words are the rewrite's to choose; the address is not.
    assert accept(part, reworded_anchor, 145) is not None


def test_a_part_asked_to_come_down_is_too_long_only_when_it_is_longer_than_it_was():
    """Replayed on two real drafts 40% over their target: a list of tools, a table and the
    questions each came back a little shorter than drafted, over the guard, and were kept as
    drafted, a third over what was wanted of them: 746 words nobody cut. A part no longer
    than it was drafted does the length no harm; one that grew when asked to shrink does."""
    part = _section(150)
    wanted = words(part.text) * 0.75

    shorter_but_over_the_guard = f"## Fill the Calendar\n\n{_text(146)}"
    assert words(shorter_but_over_the_guard) > wanted * 1.2
    assert accept(part, shorter_but_over_the_guard, wanted) is not None
    assert accept(part, f"## Fill the Calendar\n\n{_text(116)}", wanted) is not None
    assert accept(part, f"## Fill the Calendar\n\n{_text(156)}", wanted) is None


def test_a_part_kept_as_drafted_says_why():
    """The reason goes to the log beside the part's number: the replay above was read from it."""
    part = _section(150)

    assert judge(part, "", 150) == (None, "came back empty")
    assert judge(part, f"## Fill the Calendar\n\n{_text(190)}", 150) == (
        None,
        "too long (194 words for 150 wanted)",
    )
    assert judge(part, f"## Fill the Calendar\n\n{_text(70)}", 150)[1].startswith("too short")
    assert judge(part, f"## One\n\n{_text(70)}\n\n## Two\n\n{_text(70)}", 150)[1] == (
        "its headings changed"
    )
    taken, why = judge(part, f"## Fill the Calendar\n\n{_text(148)}", 150)
    assert taken is not None and why == ""


def test_a_sections_sub_headings_are_the_drafted_ones_whatever_came_back():
    """Review round 1: only a section's own heading was put back. Under it a sub-heading could
    be reworded, dropped, added or moved, and nothing after the rewrite compares them with the
    outline the person approved."""
    heading = "## Plan the Month"
    part = Part(
        SECTION,
        heading,
        f"{heading}\n\n{_text(60)}\n\n### Pick the Themes\n\n{_text(50)}\n\n"
        f"### Set the Dates\n\n{_text(50)}",
    )

    def back(*sub_headings, own=heading):
        blocks = [f"{own}\n\n{_text(58)}"] if own else [_text(58)]
        return "\n\n".join(blocks + [f"{sub}\n\n{_text(48)}" for sub in sub_headings])

    reworded = accept(part, back("### Choosing Your Themes", "### When to Publish"), 168)
    own_left_off = accept(part, back("### Pick the Themes", "### Set the Dates", own=""), 168)

    assert [line for line in reworded.splitlines() if line.startswith("#")] == [
        heading,
        "### Pick the Themes",
        "### Set the Dates",
    ]
    assert own_left_off.startswith(f"{heading}\n\n") and "### Set the Dates" in own_left_off
    for changed, why in (
        (back("### Pick the Themes"), "one dropped"),
        (back("### Pick the Themes", "### Set the Dates", "### One More"), "one added"),
        (back("### Pick the Themes", "## Set the Dates"), "one raised to a section"),
    ):
        assert judge(part, changed, 168)[1] == "its headings changed", why
    # The parts with no heading of their own take none, of any level.
    introduction = Part(INTRODUCTION, "", _text(70))
    assert accept(introduction, f"{_text(30)}\n\n### A Detail\n\n{_text(36)}", 70) is None


def test_a_heading_of_any_level_is_held_down_to_a_pillar_pages_h4s():
    """Review round 2: a pillar page's outline has H4 entries, and only H2 and H3 were read:
    an H4 could be reworded or dropped unseen. Every heading line is held, of any level."""
    heading = "## Plan the Month"
    part = Part(
        SECTION,
        heading,
        f"{heading}\n\n{_text(50)}\n\n### Pick the Themes\n\n{_text(40)}\n\n"
        f"#### For a Small Team\n\n{_text(40)}",
    )

    def back(*under):
        return "\n\n".join([f"{heading}\n\n{_text(48)}"] + [f"{h}\n\n{_text(38)}" for h in under])

    reworded = accept(part, back("### Pick the Themes", "#### When the Team Is Small"), 140)

    assert "#### For a Small Team" in reworded and "When the Team Is Small" not in reworded
    assert judge(part, back("### Pick the Themes"), 140)[1] == "its headings changed"
    assert judge(part, back("### Pick the Themes", "### For a Small Team"), 140)[1] == (
        "its headings changed"
    )
    # A title line put on top of a part is a heading too.
    introduction = Part(INTRODUCTION, "", _text(70))
    assert accept(introduction, f"# The Article\n\n{_text(66)}", 70) is None
    # A line of a fenced example that looks like a heading is not one.
    fenced = f"{heading}\n\n{_text(40)}\n\n```markdown\n## Not a Section\n```\n\n{_text(40)}"
    assert accept(Part(SECTION, heading, fenced), fenced, 90) is not None


def test_an_image_stays_an_image_as_often_as_it_stood():
    """Review round 1: an image turned into a link still points where it did, and one of two
    alike is gone without its address being; the links' own check does not read images."""
    heading = "## Fill the Calendar"
    image = "![A calendar](https://img.test/calendar.png)"
    part = Part(SECTION, heading, f"{heading}\n\n{image}\n\n{_text(100)}\n\n{image}\n\n{_text(40)}")

    as_a_link = f"{heading}\n\n[A calendar](https://img.test/calendar.png)\n\n{_text(98)}\n\n{image}\n\n{_text(40)}"
    one_gone = f"{heading}\n\n{image}\n\n{_text(138)}"
    both_there = f"{heading}\n\n{image}\n\n{_text(96)}\n\n{image}\n\n{_text(42)}"

    assert judge(part, as_a_link, 150)[1] == "a link or an image was lost"
    assert judge(part, one_gone, 150)[1] == "a link or an image was lost"
    assert accept(part, both_there, 150) is not None


def test_a_list_or_a_table_keeps_its_items():
    """Review round 1: the message asks that lists stay lists with their items, and nothing
    held it: a step dropped from a how-to, or a table's row, took its facts with it."""
    heading = "## Set It Up"
    steps = "1. Open the planner.\n2. Pick a month.\n3. Add each post."
    bullets = "- Themes\n- Dates\n- Owners"
    table = "| Tool | Price |\n|---|---|\n| Planner | $9 |\n| Sheets | $0 |"
    part = Part(
        SECTION,
        heading,
        f"{heading}\n\n{_text(40)}\n\n{steps}\n\n{bullets}\n\n{table}\n\n{_text(40)}",
    )

    def back(steps=steps, bullets=bullets, table=table):
        return f"{heading}\n\n{_text(38)}\n\n{steps}\n\n{bullets}\n\n{table}\n\n{_text(38)}"

    reworded = back(steps="1. Start the planner.\n2. Choose your month.\n3. Put in each post.")
    assert accept(part, reworded, words(part.text)) is not None
    for changed, why in (
        (back(steps="1. Open the planner.\n2. Add each post."), "a step dropped"),
        (back(bullets="Themes, dates and owners all go in."), "a list told as prose"),
        (back(table="| Tool | Price |\n|---|---|\n| Planner | $9 |"), "a row dropped"),
    ):
        assert judge(part, changed, words(part.text))[1] == "a list or a table lost items", why


def test_the_part_that_carries_the_call_to_action_keeps_its_words():
    """Review round 1: the brief's call-to-action line is the whole article's and goes to no
    part, so the one part that holds it could reword it away from the call to action saved
    with the article. That part is told, and held to it."""
    heading = "## Start Today"
    cta = "Start planning your garden today"
    part = Part(
        SECTION, heading, f"{heading}\n\n{_text(60)} [{cta}](https://site.test/start). {_text(20)}"
    )

    told = call_to_action_lines(part.text, cta)
    kept = f"{heading}\n\n{_text(56)} Ready? [{cta}](https://site.test/start). {_text(20)}"
    reworded = f"{heading}\n\n{_text(58)} [Begin your garden plan now](https://site.test/start). {_text(20)}"

    assert f'carries the article\'s call to action, "{cta}"' in told
    assert (
        call_to_action_lines(_text(80), cta) == "" and call_to_action_lines(part.text, None) == ""
    )
    assert accept(part, kept, 88, keep=[cta]) is not None
    assert judge(part, reworded, 88, keep=[cta])[1] == "the call to action's words changed"
    # A part that never held it is not held to it.
    assert (
        accept(_section(150), f"## Fill the Calendar\n\n{_text(148)}", 150, keep=[cta]) is not None
    )


def test_the_introduction_and_the_opening_take_no_heading():
    introduction = Part(INTRODUCTION, "", _text(70))

    assert accept(introduction, _text(68), 70) == _text(68)
    assert accept(introduction, f"## An Introduction\n\n{_text(66)}", 70) is None


def test_a_part_keeps_the_keyphrase_uses_it_has_and_gains_none():
    text = "A content calendar template saves a week. Use one content calendar template per team."

    kept = keyword_lines(text, "content calendar template", ["editorial calendar", "per team"])
    absent = keyword_lines("Plan the month first.", "content calendar template", ["per team"])

    assert "appears 2 time(s) in this part's text. Keep it exactly 2 time(s) in the text" in kept
    # Only the secondary keywords this part holds: each is asked of the part that has it.
    assert "Keep each of these phrases as written, at least once: per team." in kept
    assert "editorial calendar" not in kept
    assert absent == (
        '- The phrase "content calendar template" is not in this part\'s text. Do not add it.'
    )
    assert keyword_lines(text, "", None) == ""


def test_a_headings_use_of_the_keyphrase_is_not_counted_as_the_texts():
    """On staging a section whose heading holds the phrase, told "keep it once", came back with
    it once more in its text."""
    section = (
        "## Content Calendar Template Basics\n\n"
        "Start small. A content calendar template earns its keep in week two."
    )
    heading_only = "## Content Calendar Template Basics\n\nStart small and plan one week."

    told = keyword_lines(section, "content calendar template", None)
    told_heading_only = keyword_lines(heading_only, "content calendar template", None)

    assert "appears 1 time(s) in this part's text (its heading has the phrase too" in told
    assert "Keep it exactly 1 time(s) in the text" in told
    assert "is not in this part's text (its heading has the phrase too" in told_heading_only
    assert told_heading_only.endswith("Do not add it.")


KEYPHRASE = "content calendar template"


def _with_uses(count: int, uses: int) -> str:
    """Prose of ``count`` words that holds the keyphrase ``uses`` times."""
    phrase = f"A {KEYPHRASE} helps. "
    return " ".join((phrase * uses + SENTENCE * (count // 10 + 1)).split()[:count])


def _planned_article(uses_by_part: list[int]) -> list[Part]:
    sizes = [80, 200, 320, 260, 180]
    return [
        Part(SECTION, f"## Part {n}", f"## Part {n}\n\n{_with_uses(size, uses)}")
        for n, (size, uses) in enumerate(zip(sizes, uses_by_part, strict=True), 1)
    ]


def _range_for(parts: list[Part], scale: float = 1.0) -> tuple[int, int]:
    from src.flow.engines.content.generation.keyword_density import resolve_density_policy

    total = sum(words(part.text) for part in parts)
    policy = resolve_density_policy(round(total * scale), "blog", 3)
    return policy["min_occurrences"], policy["max_occurrences"]


def test_an_article_with_the_least_uses_it_needs_is_planned_one_more_in_its_longest_part():
    """On staging a how-to had exactly the least it needed; the rewrite added fifty words, the
    count stayed, and the density check failed."""
    least, most = _range_for(_planned_article([0, 0, 0, 0, 0]))
    assert most > least
    spread = [1] * least + [0] * (5 - least) if least <= 5 else [least, 0, 0, 0, 0]
    parts = _planned_article(spread)

    plan = keyphrase_plan(parts, KEYPHRASE, "blog", 1.0)

    assert sum(plan.values()) == least + 1
    # The one more goes to the longest part, where it reads least forced.
    assert plan[2] == spread[2] + 1
    assert {i: n for i, n in plan.items() if i != 2} == {i: spread[i] for i in (0, 1, 3, 4)}


def test_an_article_inside_its_keyphrase_range_keeps_every_use_where_it_is():
    least, most = _range_for(_planned_article([0, 0, 0, 0, 0]))
    spread = [1, 1, 1, 1, max(0, least + 1 - 4)]
    parts = _planned_article(spread)

    assert keyphrase_plan(parts, KEYPHRASE, "blog", 1.0) == dict(enumerate(spread))
    assert keyphrase_plan(parts, "", "blog", 1.0) == {}


def test_an_article_with_the_keyphrase_too_often_is_planned_fewer_where_it_has_the_most():
    least, most = _range_for(_planned_article([0, 0, 0, 0, 0]))
    spread = [1, 1, most + 1, 1, 0]
    parts = _planned_article(spread)

    plan = keyphrase_plan(parts, KEYPHRASE, "blog", 1.0)

    assert sum(plan.values()) == most
    assert plan[2] < spread[2] and plan[0] <= 1


def test_the_plan_reaches_the_count_wanted_however_the_uses_are_spread():
    """Review round 1: each part was moved by one at most, so an article with all its excess in
    one section stayed over, and one that needed more than it has parts stayed under."""
    least, most = _range_for(_planned_article([0, 0, 0, 0, 0]))

    all_in_one = _planned_article([0, 0, most + 3, 0, 0])
    plan = keyphrase_plan(all_in_one, KEYPHRASE, "blog", 1.0)
    assert sum(plan.values()) == most and plan[2] == most

    none_at_all = _planned_article([0, 0, 0, 0, 0])
    plan = keyphrase_plan(none_at_all, KEYPHRASE, "blog", 1.0)
    assert sum(plan.values()) == min(least + 1, most)


def test_the_plan_counts_the_keyphrase_where_the_check_does():
    """Review round 2: the density check also counts the title and the meta fields, where the
    keyphrase always stands. Planned from the body alone, an article at the top of its range
    was still given one more, and failed by what the title and the meta add."""
    least, most = _range_for(_planned_article([0, 0, 0, 0, 0]))
    elsewhere = f"A {KEYPHRASE} for your team\nA {KEYPHRASE} for your team\nUse a {KEYPHRASE}."
    in_the_body = most - 3
    spread = [0, in_the_body // 2, in_the_body - in_the_body // 2, 0, 0]
    parts = _planned_article(spread)

    with_them = keyphrase_plan(parts, KEYPHRASE, "blog", 1.0, elsewhere=elsewhere)
    over = keyphrase_plan(
        _planned_article([0, in_the_body, 2, 0, 0]), KEYPHRASE, "blog", 1.0, elsewhere=elsewhere
    )

    # At the most the article may have, title and meta counted: every use stays where it is.
    assert with_them == dict(enumerate(spread))
    # Two over, title and meta counted: two come out of the body, where it has the most.
    assert sum(over.values()) + 3 == most


def test_a_part_is_told_plainly_when_its_uses_are_to_change():
    text = f"Start small. A {KEYPHRASE} earns its keep in week two."

    more = keyword_lines(text, KEYPHRASE, None, wanted_uses=2)
    fewer = keyword_lines(text, KEYPHRASE, None, wanted_uses=0)
    same = keyword_lines(text, KEYPHRASE, None, wanted_uses=1)

    assert "The article needs it once more: use it exactly 2 time(s) in the text" in more
    assert "The article has it too often: use it exactly 0 time(s) in the text" in fewer
    assert "Keep it exactly 1 time(s) in the text" in same


def test_a_part_keeps_the_brand_mentions_it_has_and_brings_in_none():
    brand = {"brand_name": "Acme Tools", "brand_url": "https://www.acme.test/"}
    named = "Teams use [Acme Tools](https://www.acme.test/) to map the month."

    assert 'names "Acme Tools" 1 time(s)' in brand_lines(
        named, brand_context=brand, excluded_brand=None
    )
    assert "Its link (https://www.acme.test/) stays" in brand_lines(
        named, brand_context=brand, excluded_brand=None
    )
    assert brand_lines("Plan the month.", brand_context=brand, excluded_brand=None) == (
        '- This part does not name "Acme Tools". Do not bring it in.'
    )
    # The user chose no mention: said to every part, whether it names the brand or not.
    assert 'Do not name "Acme Tools"' in brand_lines(
        "Plan the month.", brand_context=None, excluded_brand=brand
    )
    assert brand_lines("Plan the month.", brand_context=None, excluded_brand=None) == ""


def test_a_rewrite_that_changes_how_often_the_brand_is_named_keeps_the_part_as_drafted():
    """A Subtle article names the brand once, a part is told to keep what it has and bring in
    none, and nothing held it to that: a mention added, dropped or doubled would have gone into
    the article and failed the level the user chose, after the last repair."""
    brand = {"brand_name": "Acme Tools", "brand_url": "https://www.acme.test/"}
    heading = "## Fill the Calendar"
    mention = "Teams use [Acme Tools](https://www.acme.test/) to map the month."
    named = Part(SECTION, heading, f"{heading}\n\n{_text(70)} {mention} {_text(70)}")
    plain = _section(150)

    kept = f"{heading}\n\n{_text(66)} Most teams map the month with [Acme Tools](https://www.acme.test/). {_text(66)}"
    doubled = f"{heading}\n\n{_text(60)} {mention} Acme Tools also sends reminders. {_text(60)}"
    dropped = f"{heading}\n\n{_text(70)} Teams use [a planner](https://www.acme.test/) for it. {_text(66)}"
    link_moved = (
        f"{heading}\n\n{_text(60)} Teams use Acme Tools to map the month. {_text(60)} "
        "See [the planner](https://www.acme.test/) for more."
    )
    brought_in = f"{heading}\n\n{_text(140)} Acme Tools can help here."

    assert accept(named, kept, 150, brand=brand) is not None
    assert judge(named, doubled, 150, brand=brand)[1] == "the brand's mentions changed"
    assert judge(named, dropped, 150, brand=brand)[1] == "the brand's mentions changed"
    assert judge(named, link_moved, 150, brand=brand)[1] == "the brand's mention lost its link"
    assert judge(plain, brought_in, 150, brand=brand)[1] == "the brand's mentions changed"
    # The user chose no mention: a part may lose the name, never gain it.
    assert judge(plain, brought_in, 150, excluded=brand)[1] == (
        "a brand the article leaves out was named"
    )
    assert (
        accept(named, f"{heading}\n\n{_text(140)}", 150, excluded=brand) is None
    )  # its link went too
    # With no brand on the article, the name is a word like any other.
    assert accept(plain, brought_in, 150) is not None


def test_a_secondary_keyword_the_draft_missed_is_given_to_the_section_nearest_to_it():
    """Replayed on three real drafts: the whole-article rewrite, told "each at least once", put
    in the secondary keywords the writer had missed; told only what each part held, the
    rewrite by section left all of them out."""
    parts = split_article(
        _text(60),
        f"## Plan the Month\n\n{_text(80)} An editorial calendar helps.\n\n"
        f"## Pick Email Newsletter Tools\n\n{_text(90)}\n\n"
        f"## A Note\n\n{_text(20)}\n\n"
        f"## Review It on Fridays\n\n{_text(120)}",
    )
    keywords = ["editorial calendar", "email newsletter examples", "content audit checklist"]

    plan = secondary_plan(parts, keywords)

    # The one the draft has is nobody's to add; the one whose words a section already uses
    # goes there; one with no words anywhere goes to the longest section.
    assert plan == {2: ["email newsletter examples"], 4: ["content audit checklist"]}
    told = keyword_lines(parts[2].text, "", keywords, new_phrases=plan[2])
    assert (
        '- The article does not use "email newsletter examples" yet. Use it once in this part, '
        "word for word, in a sentence where it reads naturally."
    ) in told
    assert secondary_plan(parts, ["editorial calendar"]) == {}
    assert secondary_plan(parts, None) == {}


def test_missed_phrases_go_one_to_a_section_before_a_second_to_any_and_two_at_most():
    """On a replay two phrases went to the one section nearest to both; it grew a fifth past
    its length bringing them in, and was kept as drafted without either."""
    crm = "Compare each CRM before you choose one for a startup team."
    parts = split_article(
        "", f"## Choose a CRM\n\n{crm} {_text(80)}\n\n## Plan the Rollout\n\n{_text(120)}"
    )

    spread = secondary_plan(parts, ["how to choose crm", "top crm software"])
    crowded = secondary_plan(
        parts, ["content audit", "style guide", "brief template", "tone of voice", "house rules"]
    )

    # Both are nearest to the first section: it takes the first, the other section the second.
    assert spread == {0: ["how to choose crm"], 1: ["top crm software"]}
    assert sorted(len(phrases) for phrases in crowded.values()) == [2, 2]
    assert "house rules" not in sum(crowded.values(), [])


def test_no_section_is_asked_to_bring_in_more_than_two_phrases():
    parts = split_article("", f"## Plan the Month\n\n{_text(80)}\n\n## A Note\n\n{_text(20)}")

    plan = secondary_plan(parts, ["content audit", "style guide", "brief template"])

    # One section long enough to be rewritten: two go to it, the third stays missed.
    assert plan == {0: ["content audit", "style guide"]}
    assert "Use each once in this part" in keyword_lines(
        parts[0].text, "", None, new_phrases=plan[0]
    )


def test_a_part_is_told_of_the_phrases_and_mentions_a_reader_sees_in_it():
    """Review round 3 of the rewrite: the part's message counted in the raw text, the checks
    and the guard count what a reader sees. A phrase written with emphasis inside it was not
    named to its part, and a one-word brand whose link's address holds its name was said to
    be named twice."""
    emphasised = "Keep a content **calendar** for the quarter and review it monthly."
    brand = {"brand_name": "Acme", "brand_url": "https://acme.test/"}
    linked = "Teams use [Acme](https://acme.test/) to map the month."

    assert "Keep each of these phrases as written, at least once: content calendar." in (
        keyword_lines(emphasised, "", ["content calendar", "style guide"])
    )
    told = brand_lines(linked, brand_context=brand, excluded_brand=None)
    assert 'names "Acme" 1 time(s)' in told and "Its link (https://acme.test/) stays" in told
    # What the part is told is what it is held to.
    part = Part(SECTION, "## Plan", f"## Plan\n\n{_text(60)} {linked} {_text(60)}")
    same = f"## Plan\n\n{_text(58)} Most teams map the month with [Acme](https://acme.test/). {_text(58)}"
    assert accept(part, same, words(part.text), brand=brand) is not None


def test_an_answer_wrapped_in_a_fence_or_sent_in_pieces_is_read_as_its_text():
    fenced = SimpleNamespace(content="```markdown\n## Fill the Calendar\n\nText.\n```")
    pieces = SimpleNamespace(
        content=[{"type": "text", "text": "One. "}, {"type": "text", "text": "Two."}]
    )

    assert _plain_text(fenced) == "## Fill the Calendar\n\nText."
    # Review round 1: a tilde fence is a fence too; left on, the section went in as a code block.
    tilde = SimpleNamespace(content="~~~markdown\n## Fill the Calendar\n\nText.\n~~~")
    assert _plain_text(tilde) == "## Fill the Calendar\n\nText."
    assert _plain_text(pieces) == "One. Two."


class _Model:
    """Answers each part as ``answer(text)`` says, and counts how many calls ran at once."""

    def __init__(self, answer):
        self.answer, self.asked, self.running, self.most_at_once = answer, [], 0, 0

    async def ainvoke(self, messages):
        self.asked.append(messages)
        self.running += 1
        self.most_at_once = max(self.most_at_once, self.running)
        await asyncio.sleep(0)
        self.running -= 1
        reply = self.answer(messages)
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(content=reply)


def _messages_for(part, index, low, high, lost=()):
    return {"part": part, "index": index, "low": low, "high": high, "lost": lost}


async def test_every_part_is_rewritten_at_once_and_the_article_keeps_its_length():
    parts = split_article(INTRO, BODY)
    model = _Model(lambda m: m["part"].text.replace("Plan one week", "Map one week"))

    rewritten, counts = await rewrite_parts(
        parts, model=model, messages_for=_messages_for, word_target=500
    )

    # The image line that opens the body is too short to be worth a call.
    assert [m["part"].kind for m in model.asked] == [INTRODUCTION, SECTION, SECTION, SECTION]
    assert model.most_at_once == 4
    assert counts == {
        "parts": 5,
        "rewritten": 4,
        "kept": 1,
        "words_before": sum(words(part.text) for part in parts),
        "words_after": sum(words(part.text) for part in parts),
    }
    assert "Map one week" in join_article(rewritten)[1] and rewritten[1] is parts[1]
    # 496 words for 500 asked: inside its range, so each part is asked for its own length.
    assert [(m["low"], m["high"]) for m in model.asked] == [
        stated_range(words(m["part"].text)) for m in model.asked
    ]


async def test_an_article_over_its_range_asks_every_part_for_less():
    parts = split_article(INTRO, BODY)
    total = sum(words(part.text) for part in parts)
    model = _Model(lambda m: m["part"].text)

    await rewrite_parts(
        parts, model=model, messages_for=_messages_for, word_target=round(total / 1.3)
    )

    for asked in model.asked:
        # Down to the target, and told lower than that again.
        assert asked["high"] < words(asked["part"].text) * 0.75


async def test_a_part_that_fails_or_comes_back_too_long_is_kept_as_drafted_and_the_rest_go_on():
    parts = split_article(INTRO, BODY)

    def answer(messages):
        part = messages["part"]
        if part.heading == "## Fill the Calendar":
            return RuntimeError("the model call failed")
        if part.heading == "## Review It on Fridays":
            return part.text + " " + _text(60)  # two thirds longer than it went in
        return part.text.replace("Plan one week", "Map one week")

    rewritten, counts = await rewrite_parts(
        parts, model=_Model(answer), messages_for=_messages_for, word_target=500
    )

    assert counts["rewritten"] == 2 and counts["kept"] == 3
    assert rewritten[3] is parts[3] and rewritten[4] is parts[4]
    assert counts["words_after"] == counts["words_before"]


async def test_a_part_that_comes_back_naming_the_brand_anew_is_kept_as_drafted():
    parts = split_article(INTRO, BODY)
    brand = {"brand_name": "Acme Tools", "brand_url": "https://www.acme.test/"}

    def answer(messages):
        part = messages["part"]
        reworded = part.text.replace("Plan one week", "Map one week")
        if part.heading == "## Fill the Calendar":
            return f"{reworded} Acme Tools can help."
        return reworded

    rewritten, _ = await rewrite_parts(
        parts, model=_Model(answer), messages_for=_messages_for, word_target=500, brand=brand
    )

    index = next(i for i, part in enumerate(parts) if part.heading == "## Fill the Calendar")
    assert rewritten[index] is parts[index]
    assert not any("Acme Tools" in part.text for part in rewritten)
    assert any("Map one week" in part.text for part in rewritten)


def _rewritten(parts, grow):
    """Each part as a rewrite ``grow`` words longer (or shorter) than it was drafted."""
    return [
        Part(part.kind, part.heading, " ".join(part.text.split()[: words(part.text) + change]))
        if change < 0
        else Part(part.kind, part.heading, f"{part.text} {_text(change)}" if change else part.text)
        for part, change in zip(parts, grow, strict=True)
    ]


def test_parts_each_a_little_long_do_not_take_the_article_out_of_its_range():
    """Review round 1: a part may come back a fifth over what was wanted of it and an article
    is allowed 12%, so every part 15% long was an article outside its range that no part's
    guard saw. The parts that grew the most go back to their drafts until it is inside."""
    parts = [_section(200, f"## Part {n}") for n in range(1, 6)]
    target = sum(words(part.text) for part in parts)  # 1,015: inside its range as drafted
    most = round(target * 1.12)

    all_long = _rewritten(parts, [30, 34, 26, 32, 28])  # each about 15% over: 1,165 in all
    held = hold_the_range(parts, all_long, target)

    assert sum(words(part.text) for part in all_long) > most
    assert sum(words(part.text) for part in held) <= most
    # The largest growth went back first, and no more parts than it took.
    assert held[1] is parts[1] and held[2] is all_long[2]
    assert sum(1 for before, after in zip(parts, held, strict=True) if after is before) == 1

    # Inside the range, every rewrite stays; and one that came out short gets back the parts
    # that shrank the most.
    fine = _rewritten(parts, [10, -10, 5, 0, -5])
    assert hold_the_range(parts, fine, target) == fine
    all_short = _rewritten(parts, [-40, -50, -30, -45, -35])
    held = hold_the_range(parts, all_short, target)
    assert sum(words(part.text) for part in held) >= round(target * 0.88)
    assert held[1] is parts[1] and held[2] is all_short[2]


async def test_the_articles_range_is_held_after_every_part_is_back():
    parts = split_article("", "\n\n".join(f"## Part {n}\n\n{_text(200)}" for n in range(1, 6)))
    target = sum(words(part.text) for part in parts)

    def answer(messages):
        return f"{messages['part'].text} {_text(36)}"  # every part 18% over, inside its own guard

    rewritten, counts = await rewrite_parts(
        parts, model=_Model(answer), messages_for=_messages_for, word_target=target
    )

    assert counts["words_after"] <= round(target * 1.12)
    assert 0 < counts["kept"] < len(parts)


async def test_a_part_that_came_back_without_a_link_is_asked_once_more_and_told_which():
    """Replayed on real drafts: a list of products lost one of its links in round after round,
    was kept as drafted each time, and was the part an over-long article most needed shortened.
    Told which address it left out, the model keeps it; asked twice at most."""
    heading = "## Fill the Calendar"
    link = "[a planning guide](https://site.test/guides/planning/)"
    with_link = Part(SECTION, heading, f"{heading}\n\n{_text(100)} See {link}. {_text(40)}")
    parts = [with_link, _section(120, "## Review It on Fridays")]

    def forgetful_once(messages):
        part = messages["part"]
        if part is with_link and not messages["lost"]:
            return f"{heading}\n\n{_text(140)}"
        return part.text.replace("Plan one week", "Map one week")

    def forgetful_always(messages):
        part = messages["part"]
        return f"{heading}\n\n{_text(140)}" if part is with_link else part.text

    once, always = _Model(forgetful_once), _Model(forgetful_always)
    total = sum(words(part.text) for part in parts)
    rewritten, counts = await rewrite_parts(
        parts, model=once, messages_for=_messages_for, word_target=total
    )
    kept, _ = await rewrite_parts(
        parts, model=always, messages_for=_messages_for, word_target=total
    )

    # Asked again with the address it left out, and the answer that kept it is used.
    assert [m["lost"] for m in once.asked if m["part"] is with_link] == [
        (),
        ("https://site.test/guides/planning",),
    ]
    assert "Map one week" in rewritten[0].text and link in rewritten[0].text
    assert counts["kept"] == 0
    # Left out twice: the part stays as drafted, and is not asked a third time.
    assert len([m for m in always.asked if m["part"] is with_link]) == 2
    assert kept[0] is with_link
    told = lost_lines(("https://site.test/guides/planning",))
    assert told.startswith(
        "- Your last answer to this left out: https://site.test/guides/planning."
    )
    # Review round 1: a link belongs in a sentence; an image stays where it stands.
    assert "inside a sentence; every image stays where it stands, unchanged." in told
    assert lost_lines(()) == ""


async def test_the_second_ask_is_one_call_and_names_what_the_guard_found_missing(monkeypatch):
    """Review round 1: the second ask went through the watched call's own second attempt, so a
    part could be requested a third time; and what it had left out was read from the raw
    answer, where a link put before the part's heading still stood, so that part was asked
    again without being told which link."""
    import src.flow.engines.content.generation.section_rewrite as section_rewrite

    heading = "## Fill the Calendar"
    link = "[a planning guide](https://site.test/guides/planning/)"
    part = Part(SECTION, heading, f"{heading}\n\n{_text(100)} See {link}. {_text(40)}")
    asked = []

    async def watched(model, messages, *, stage, attempts=2):
        asked.append((messages["lost"], attempts))
        # The link stands before the heading: the guard drops what stands there.
        return SimpleNamespace(content=f"See {link} first.\n\n{heading}\n\n{_text(140)}")

    monkeypatch.setattr(section_rewrite, "ainvoke_watched", watched)

    rewritten, _ = await rewrite_parts(
        [part, _section(60, "## Review It")],
        model=None,
        messages_for=_messages_for,
        word_target=words(part.text) + 64,
    )

    # Each part once with the watched call's own two attempts; then the one part again, told
    # the address the guard found missing, as a single attempt. Left out twice: kept as drafted.
    assert ((), 2) in asked
    assert (("https://site.test/guides/planning",), 1) in asked
    assert len([call for call in asked if call[0]]) == 1
    assert rewritten[0] is part


async def test_an_answer_refused_for_its_length_that_also_lost_a_link_is_asked_once_more():
    """Review round 2: the guard names the first thing wrong with an answer, its length before
    its links, so an answer both too long and without a link was kept as drafted with no
    second ask."""
    heading = "## Fill the Calendar"
    link = "[a planning guide](https://site.test/guides/planning/)"
    part = Part(SECTION, heading, f"{heading}\n\n{_text(100)} See {link}. {_text(40)}")

    def answer(messages):
        if messages["part"] is not part:
            return messages["part"].text
        if messages["lost"]:
            return f"{heading}\n\n{_text(98)} Read {link} first. {_text(40)}"
        return f"{heading}\n\n{_text(200)}"  # a third too long, and the link is gone

    model = _Model(answer)
    rewritten, _ = await rewrite_parts(
        [part, _section(60, "## Review It")],
        model=model,
        messages_for=_messages_for,
        word_target=words(part.text) + 64,
    )

    assert [m["lost"] for m in model.asked if m["part"] is part] == [
        (),
        ("https://site.test/guides/planning",),
    ]
    assert link in rewritten[0].text and rewritten[0] is not part


def test_a_part_that_is_the_list_of_sources_is_told_of_the_brand_named_in_it():
    """Review round 2: the article's brand checks leave the sources out of their count, so a
    part that is the sources and names the brand there was told it does not name it, and was
    not held to keeping it."""
    brand = {"brand_name": "Acme", "brand_url": "https://acme.test/"}
    heading = "## Sources"
    sources = (
        f"{heading}\n\n- Acme, [The planning report](https://acme.test/report), 2026.\n"
        "- [A study of calendars](https://research.test/calendars), 2025.\n\n" + _text(40)
    )
    part = Part(SECTION, heading, sources)

    assert 'names "Acme" 1 time(s)' in brand_lines(
        sources, brand_context=brand, excluded_brand=None
    )
    without = sources.replace("- Acme, [The planning report]", "- [The planning report]")
    assert judge(part, without, words(sources), brand=brand)[1] == "the brand's mentions changed"
    assert accept(part, sources.replace("2026.", "2026 edition."), words(sources), brand=brand)


async def test_a_long_article_never_has_more_than_a_few_calls_running():
    body = "\n\n".join(f"## Section {n}\n\n{_text(60)}" for n in range(1, 25))
    model = _Model(lambda m: m["part"].text)

    _, counts = await rewrite_parts(
        split_article("", body), model=model, messages_for=_messages_for, word_target=1440
    )

    assert counts["rewritten"] == 24
    assert model.most_at_once == MAX_AT_ONCE


def test_one_part_reads_the_brief_without_what_belongs_to_the_whole_article():
    """Said to each of ten parts, "each keyword at least once" and "one mention early in the
    body" would be asked for ten times: a part is told its own keyword uses and mentions."""
    outline = {
        "title": "How to use a content calendar template",
        "focus_keyphrase": "content calendar template",
        "keywords_to_include": ["content calendar template", "editorial calendar"],
        "target_audience": ["Marketing leads"],
        "tone": "Practical",
        "target_word_count": 1500,
        "brand_prominence": "subtle",
        "promote_brand": True,
        "brand_voice_promotion": {
            "brand_name": "Acme Tools",
            "brand_url": "https://www.acme.test/",
        },
        "final_cta": {"primary_cta": "Start planning today"},
    }
    spec = build_requirements_spec(outline, "blog", focus_keyword="content calendar template")

    part = brief_for_stage(spec, outline, stage="section")
    whole = brief_for_stage(spec, outline, stage="rewrite")

    assert "Rewrite the part's words; the brief stands." in part
    for line in ("- Content type: blog", "- Written for: Marketing leads", "- Tone: Practical"):
        assert line in part and line in whole
    for whole_article_only in (
        "- Length:",
        "- Focus keyphrase",
        "- Secondary keywords",
        "- Brand:",
        "- Call to action",
    ):
        assert whole_article_only in whole and whole_article_only not in part


def test_the_message_for_one_part_says_which_part_and_its_own_length():
    messages = get_section_rewrite_prompt().format_messages(
        voice_instruction="",
        brief="THE ARTICLE'S BRIEF",
        title="How to use a content calendar template",
        sections="1. Plan the Month\n2. Fill the Calendar",
        which='the section "Fill the Calendar", with everything under it.',
        brand_instruction="",
        keyword_instruction="",
        words=150,
        low=120,
        high=141,
        text="## Fill the Calendar\n\nText with {braces} in it.",
    )

    human = messages[-1].content
    assert 'YOU ARE REWRITING: the section "Fill the Calendar"' in human
    assert "this part has 150 words. Return between 120 and 141 words" in human
    assert human.rstrip().endswith("Text with {braces} in it.")
    assert "2. Fill the Calendar" in human
