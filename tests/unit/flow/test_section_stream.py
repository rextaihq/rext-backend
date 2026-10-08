"""The article's sections are read out of the writer's answer while it is written
(revnix/rext-control#773): the page looked for `body_markdown`, which only exists after the
answer ends, and showed no text for the whole wait."""

import json

import pytest

from src.flow.engines.content.generation.section_stream import SectionStream

SECTIONS = [("hero", 2), ("structure_1", 2), ("structure_2", 3), ("faqs", 2)]
ANSWER = {
    "title": "How to plan a garden",
    "introduction": "Plan before you dig.",
    "body_markdown": "",
    "facts": [{"claim": "Beds need sun", "source_url": "https://example.test/sun"}],
    "hero": {"heading": "Plan Your Garden", "markdown": "A plan saves a season."},
    "structure_1": {"heading": "Choose the Spot", "markdown": 'Sun matters. A "south" bed {wins}.'},
    "structure_2": {"heading": "Sun Hours", "markdown": "Six hours.\n\n- Count them\n- Twice"},
    "faqs": {"heading": "Questions", "markdown": "### When?\nIn spring."},
}


def _pieces(text, size):
    return [text[start : start + size] for start in range(0, len(text), size)]


def _feed_all(stream, pieces):
    return [section for piece in pieces for section in stream.feed(piece)]


@pytest.mark.parametrize("size", [1, 3, 7, 50, 10_000])
def test_each_section_is_returned_once_in_order_whatever_the_pieces(size):
    sections = _feed_all(SectionStream(SECTIONS), _pieces(json.dumps(ANSWER), size))

    assert [s["key"] for s in sections] == ["hero", "structure_1", "structure_2", "faqs"]
    assert [(s["index"], s["of"], s["level"]) for s in sections] == [
        (1, 4, 2),
        (2, 4, 2),
        (3, 4, 3),
        (4, 4, 2),
    ]
    assert sections[1] == {
        "type": "section",
        "phase": "draft",
        "key": "structure_1",
        "index": 2,
        "of": 4,
        "level": 2,
        "heading": "Choose the Spot",
        "markdown": 'Sun matters. A "south" bed {wins}.',
    }
    assert sections[2]["markdown"] == "Six hours.\n\n- Count them\n- Twice"


def test_a_section_is_returned_the_moment_it_closes_and_not_before():
    text = json.dumps(ANSWER)
    stream = SectionStream(SECTIONS)
    closes = text.index("A plan saves a season.") + len('A plan saves a season."}')

    assert stream.feed(text[: closes - 1]) == []
    assert [s["key"] for s in stream.feed(text[closes - 1 : closes])] == ["hero"]
    assert stream.feed(text[closes : closes + 5]) == []


def test_a_section_the_writer_left_out_is_passed_over():
    answer = {**ANSWER, "structure_1": None}

    sections = _feed_all(SectionStream(SECTIONS), _pieces(json.dumps(answer), 11))

    assert [s["key"] for s in sections] == ["hero", "structure_2", "faqs"]
    # An empty one is as missing as an absent one.
    empty = {**ANSWER, "structure_2": {"heading": "Sun Hours", "markdown": "  "}}
    keys = [s["key"] for s in _feed_all(SectionStream(SECTIONS), [json.dumps(empty)])]
    assert keys == ["hero", "structure_1", "faqs"]


def test_what_is_not_a_section_of_the_answer_is_never_returned():
    # The searches the writer makes arrive on the same stream, as do other objects.
    noise = '{"query": "garden beds"}{"structure_9": {"heading": "x", "markdown": "y"}}'
    stream = SectionStream(SECTIONS)

    assert stream.feed(noise) == []
    assert stream.feed(12) == [] and stream.feed("") == [] and stream.feed(None) == []
    assert [s["key"] for s in stream.feed(json.dumps(ANSWER))][0] == "hero"


def test_an_answer_past_any_articles_size_is_no_longer_read():
    stream = SectionStream(SECTIONS)

    assert stream.feed(" " * 400_001) == []
    assert stream.feed(json.dumps(ANSWER)) == []


def test_no_sections_no_events():
    assert SectionStream([]).feed(json.dumps(ANSWER)) == []


# -- Review round 1 --------------------------------------------------------------------------


def test_fields_in_another_order_are_each_returned_with_their_own_place():
    """JSON's member order is the writer's: a section that closes out of turn is not lost."""
    shuffled = {key: ANSWER[key] for key in ("faqs", "title", "structure_2", "hero", "structure_1")}

    sections = _feed_all(SectionStream(SECTIONS), _pieces(json.dumps(shuffled), 9))

    assert [(s["key"], s["index"]) for s in sections] == [
        ("faqs", 4),
        ("structure_2", 3),
        ("hero", 1),
        ("structure_1", 2),
    ]
    assert {s["of"] for s in sections} == {4}


def test_a_new_answer_is_read_from_its_start():
    """The writer's answer was refused and it is asked again: what the page was sent from the
    refused one is sent again as the new answer has it, and the rest follows."""
    refused = json.dumps(ANSWER)
    again = json.dumps(
        {**ANSWER, "hero": {"heading": "Plan Your Garden", "markdown": "Measure first."}}
    )
    stream = SectionStream(SECTIONS)
    cut = refused.index('"structure_2"')

    assert [s["key"] for s in stream.feed(refused[:cut])] == ["hero", "structure_1"]
    stream.restart()
    sections = _feed_all(stream, _pieces(again, 13))

    assert [s["key"] for s in sections] == ["hero", "structure_1", "structure_2", "faqs"]
    assert sections[0]["markdown"] == "Measure first."


def test_restarting_reads_again_after_a_runaway_answer():
    stream = SectionStream(SECTIONS)
    assert stream.feed(" " * 400_001) == []

    stream.restart()

    assert len(stream.feed(json.dumps(ANSWER))) == 4


def _steps_draft(value):
    lines = [f"{n}. **{step['title']}.** {step['description']}" for n, step in enumerate(value, 1)]
    return ("Follow These Steps in Order", "\n".join(lines)) if lines else None


def test_a_section_a_typed_field_writes_is_returned_in_its_place():
    """A how-to guide's steps are a list of the answer's own, not a heading and its markdown:
    they are read as their draft says and counted where they stand in the article."""
    sections = [("hero", 2), ("steps", 2), ("faqs", 2)]
    answer = {
        "title": "How to plan a garden",
        # A typed field stands among the answer's first fields, before the written blocks.
        "steps": [
            {"title": "Measure", "description": 'Walk the plot. Note the "south" side [twice].'},
            {"title": "Sketch", "description": "Draw the beds {to scale}."},
        ],
        "hero": ANSWER["hero"],
        "faqs": ANSWER["faqs"],
    }
    stream = SectionStream(sections, typed={"steps": _steps_draft})

    returned = _feed_all(stream, _pieces(json.dumps(answer), 5))

    assert [(s["key"], s["index"], s["of"]) for s in returned] == [
        ("steps", 2, 3),
        ("hero", 1, 3),
        ("faqs", 3, 3),
    ]
    assert returned[0] == {
        "type": "section",
        "phase": "draft",
        "key": "steps",
        "index": 2,
        "of": 3,
        "level": 2,
        "heading": "Follow These Steps in Order",
        "markdown": (
            '1. **Measure.** Walk the plot. Note the "south" side [twice].\n'
            "2. **Sketch.** Draw the beds {to scale}."
        ),
    }


@pytest.mark.parametrize("value", [None, [], "", {"steps": []}])
def test_a_typed_section_with_nothing_to_show_is_never_returned(value):
    draft = {"verdict": lambda written: ("The Verdict", written) if written else None}
    stream = SectionStream([("hero", 2), ("verdict", 2)], typed={"verdict": draft["verdict"]})
    answer = {"verdict": value, "hero": ANSWER["hero"]}

    returned = _feed_all(stream, _pieces(json.dumps(answer), 4))

    assert [s["key"] for s in returned] == ["hero"]


def test_a_typed_section_written_as_text_is_returned_when_its_text_closes():
    draft = {"verdict": lambda written: ("The Verdict in a Few Words", written)}
    stream = SectionStream([("hero", 2), ("verdict", 2)], typed=draft)
    text = json.dumps({"verdict": 'Worth it, "mostly". {Really}', "hero": ANSWER["hero"]})
    closes = text.index("{Really}") + len('{Really}"')

    assert stream.feed(text[: closes - 1]) == []
    returned = stream.feed(text[closes - 1 :])

    assert [(s["key"], s["markdown"]) for s in returned] == [
        ("verdict", 'Worth it, "mostly". {Really}'),
        ("hero", "A plan saves a season."),
    ]
