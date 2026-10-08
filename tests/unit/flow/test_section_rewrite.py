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
    join_article,
    judge,
    keyphrase_plan,
    keyword_lines,
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
        "a heading was added"
    )
    taken, why = judge(part, f"## Fill the Calendar\n\n{_text(148)}", 150)
    assert taken is not None and why == ""


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


def test_an_answer_wrapped_in_a_fence_or_sent_in_pieces_is_read_as_its_text():
    fenced = SimpleNamespace(content="```markdown\n## Fill the Calendar\n\nText.\n```")
    pieces = SimpleNamespace(
        content=[{"type": "text", "text": "One. "}, {"type": "text", "text": "Two."}]
    )

    assert _plain_text(fenced) == "## Fill the Calendar\n\nText."
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


def _messages_for(part, index, low, high):
    return {"part": part, "index": index, "low": low, "high": high}


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
