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
