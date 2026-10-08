"""A generated title doesn't end on filler or on a word left hanging (G65, rext-control #560).

Staging, 2026-10-08, four title sets on main: "...Understanding Best Practices Now", "...at Work
Today", "...How Does It Work Easily?" (the recommended one), "...A Simple Explanation for You"
and "...Examples to Enhance Your" were offered, each with all its checks green. The prompts say
what filler is; the model still reaches the minimum length with it. So the title step looks at
the ending itself: a filler word goes where the title stands without it, and an ending that has
to be written anew goes to the repair. Never a rule of validity: the customer's own title is
theirs.
"""

from unittest.mock import AsyncMock

import pytest

from src.flow.engines.content.generation import topic_generation as tg
from src.flow.engines.content.generation.seo_title_rules import (
    title_ending_problem,
    title_is_valid,
    without_filler_ending,
)
from src.flow.model.structure.topics import SEOTopic, SEOTopics

KEYPHRASE = "what is compound interest"


@pytest.mark.parametrize(
    ("title", "keyphrase", "problem"),
    [
        # The six of the staging runs.
        (
            "How To Repot A Houseplant: Understanding Best Practices Now",
            "how to repot a houseplant",
            "filler:now",
        ),
        (
            "Understanding the Benefits of Standing Desks at Work Today",
            "benefits of standing desks",
            "filler:today",
        ),
        ("What Is Compound Interest and How Does It Work Easily?", KEYPHRASE, "filler:easily"),
        ("What Is Compound Interest? A Simple Explanation for You", KEYPHRASE, "filler:for you"),
        ("What Is Compound Interest? Examples to Enhance Your", KEYPHRASE, "unfinished:your"),
        (
            "Why Email Marketing Still Works: What to Do Right Now",
            "email marketing",
            "filler:right now",
        ),
        (
            "Email Marketing for Small Shops: Tools, Costs and the",
            "email marketing",
            "unfinished:the",
        ),
        (
            "How To Start A Podcast On YouTube: Essential Tips Here",
            "how to start a podcast",
            "filler:here",
        ),
        # Endings that say something.
        (
            "How To Repot A Houseplant: Step-By-Step Guide For 2026",
            "how to repot a houseplant",
            None,
        ),
        ("What Is Compound Interest? Impact on Your Savings Over Time", KEYPHRASE, None),
        ("How to Find the CRM Software That Is Right for You", "crm software", None),
        ("What Compound Interest Really Means for You", "compound interest", None),
        # A modal can close a title nobody cut.
        ("Content Marketing on a Tiny Budget: Yes, You Can", "content marketing", None),
        # The keyphrase's own last words are the customer's.
        ("Everything Small Teams Should Know About What to Do Now", "what to do now", None),
        ("Small Business Marketing Ideas You Can Start Today", "start today", None),
        ("Small Business Marketing Ideas You Can Start Today", "start-today", None),
        # "for you" completes a participle as it completes "right" or "made".
        ("Compound Interest Calculators and Guides Designed for You", "compound interest", None),
        ("Compound Interest Explained: A Savings Plan Made for You", "compound interest", None),
        # A preposition whose object is missing...
        (
            "Compound Interest: How Your Savings Grow Over Time With",
            "compound interest",
            "unfinished:with",
        ),
        ("What Is Compound Interest? Five Examples to Compare With", KEYPHRASE, "unfinished:with"),
        # ...but not after a verb that takes it, in a question that strands it, in a pair, or
        # when it is an adverb as often as a preposition.
        ("Compound Interest Explained: What to Look For", "compound interest", None),
        ("Compound Interest Calculators: Who Are They For?", "compound interest", None),
        ("Kitchen Remodel Ideas on a Budget: Before and After", "kitchen remodel ideas", None),
        ("Email Marketing Tools Your Whole Team Can Rely On", "email marketing", None),
        ("Email Marketing in 2026: What Lies Beyond", "email marketing", None),
        # "in", "on" and "about" need an object too, where no verb takes them.
        (
            "Compound Interest: Five Ways to Grow Your Savings in",
            "compound interest",
            "unfinished:in",
        ),
        ("Compound Interest: What Banks Stay Quiet About", "compound interest", None),
        ("Email Marketing Software: Where Your Readers Sign In", "email marketing", None),
        ("Email Marketing in 2026: What Is Really Going On", "email marketing", None),
        # A question word licenses the preposition only in its own half of the clause.
        (
            "What Compound Interest Is and How Your Savings Grow With",
            "compound interest",
            "unfinished:with",
        ),
        # Common verbs that end on their preposition.
        ("Compound Interest Tools Your Whole Team Can Work With", "compound interest", None),
        ("Compound Interest Lessons Every Saver Can Learn From", "compound interest", None),
        # A mark that stands alone hides no ending.
        (
            "Compound Interest: Why Starting Early Matters Today ?",
            "compound interest",
            "filler:today",
        ),
        # A title of few words is judged like any other; one word has no ending.
        (
            "Pneumonoultramicroscopicsilicovolcanoconiosis Today",
            "pneumonoultramicroscopicsilicovolcanoconiosis",
            "filler:today",
        ),
        ("Here", "", None),
        # Scripts without spaces.
        ("複利とは何か：基本概念、用途、使用方法", "複利とは", None),
        ("", "", None),
    ],
)
def test_what_is_a_weak_ending(title, keyphrase, problem):
    assert title_ending_problem(title, keyphrase) == problem


def test_a_weak_ending_is_no_reason_to_refuse_a_title():
    # The customer may write or pick such a title: validity is the length and the keyphrase.
    for title in (
        "What Is Compound Interest and How Does It Work Easily?",
        "What Is Compound Interest? Examples to Enhance Your",
    ):
        assert title_ending_problem(title, KEYPHRASE)
        assert title_is_valid(title, KEYPHRASE)


@pytest.mark.parametrize(
    ("title", "keyphrase", "shorter"),
    [
        (
            "How To Repot A Houseplant: Understanding Best Practices Now",
            "how to repot a houseplant",
            "How To Repot A Houseplant: Understanding Best Practices",
        ),
        (
            "Understanding the Benefits of Standing Desks at Work Today",
            "benefits of standing desks",
            "Understanding the Benefits of Standing Desks at Work",
        ),
        # A question keeps its mark.
        (
            "What Is Compound Interest and Does It Help Savers Today?",
            KEYPHRASE,
            "What Is Compound Interest and Does It Help Savers?",
        ),
        # Without the word the title is too short: the ending has to be written anew.
        ("What Is Compound Interest and How Does It Work Easily?", KEYPHRASE, None),
        # Two words, and a word left hanging, are the repair's.
        ("What Is Compound Interest? A Simple Explanation for You", KEYPHRASE, None),
        ("What Is Compound Interest? Examples to Enhance Your", KEYPHRASE, None),
        # What is left would end on a word left hanging.
        ("What Is Compound Interest? Growth for Your Savings and Now", KEYPHRASE, None),
        # Nothing to drop.
        ("What Is Compound Interest? Impact on Your Savings Over Time", KEYPHRASE, None),
    ],
)
def test_a_filler_word_is_dropped_only_where_the_title_stands_without_it(title, keyphrase, shorter):
    assert without_filler_ending(title, keyphrase) == shorter
    if shorter:
        assert title_is_valid(shorter, keyphrase)
        assert title_ending_problem(shorter, keyphrase) is None


@pytest.mark.parametrize(
    ("title", "keyphrase", "lifted"),
    [
        # The two that staging still showed after the first change: 48 and 49 characters
        # without their word, under the 50 a title needs.
        (
            "Exploring The Amazing Benefits Of Standing Desks Today",
            "benefits of standing desks",
            "Exploring The Amazing Benefits Of Standing Desks: A Guide",
        ),
        (
            "How to Start a Podcast with Top Hosting Platforms Today",
            "how to start a podcast",
            "How to Start a Podcast with Top Hosting Platforms: A Guide",
        ),
        # After a colon, an ending without one.
        (
            "How To Start A Podcast On YouTube: Essential Tips Here",
            "how to start a podcast",
            "How To Start A Podcast On YouTube: Essential Tips Explained",
        ),
        # A question keeps its mark at the end: nothing is put after it.
        ("What Is Compound Interest and How Does It Work Easily?", KEYPHRASE, None),
        # ...nor after a clause that closed on a mark of its own.
        ("What Is Compound Interest and How Does It Work? Today", KEYPHRASE, None),
        # A title that stands without its word is left without it, as before.
        (
            "A Complete Guide to Email Marketing for Small Shops Today",
            "email marketing",
            "A Complete Guide to Email Marketing for Small Shops",
        ),
    ],
)
def test_a_title_left_short_by_its_filler_word_is_lifted_with_a_short_neutral_ending(
    title, keyphrase, lifted
):
    assert without_filler_ending(title, keyphrase) == lifted
    if lifted:
        assert title_is_valid(lifted, keyphrase)
        assert title_ending_problem(lifted, keyphrase) is None


def test_a_filler_word_that_closes_a_bracket_is_not_cut_out_of_it():
    """Dropping "Here" would leave "(Start": the ending is written anew by the repair."""
    title = "Compound Interest Clearly Explained for Savers (Start Here)"
    assert title_ending_problem(title, "compound interest") == "filler:here"
    assert without_filler_ending(title, "compound interest") is None


def test_a_mark_set_apart_goes_with_the_dropped_word():
    title = "What Is Compound Interest? Understanding Its Formula Now ?"
    assert (
        without_filler_ending(title, KEYPHRASE)
        == "What Is Compound Interest? Understanding Its Formula?"
    )


GOOD = [
    "What Is Compound Interest? Understanding Its Formula",
    "What Is Compound Interest? Impact on Your Savings Over Time",
    "What Is Compound Interest? A Plain Guide for First Savers",
    "What Is Compound Interest? Five Examples With Real Numbers",
]


def _set(*titles):
    return SEOTopics(
        topics=[SEOTopic(title=title, recommended=index == 0) for index, title in enumerate(titles)]
    )


def _model(*answers):
    model = AsyncMock()
    model.ainvoke.side_effect = list(answers)
    return model


async def _titles(model):
    results = await tg._generate_and_validate_topics(
        model=model, messages=[], query=KEYPHRASE, keyphrase=KEYPHRASE
    )
    assert results is not None
    return [topic.title for topic in results.topics]


def test_the_fixtures_are_valid_titles_that_end_well():
    for title in GOOD:
        assert title_is_valid(title, KEYPHRASE), title
        assert title_ending_problem(title, KEYPHRASE) is None, title


@pytest.mark.asyncio
async def test_a_filler_word_goes_without_a_second_call_to_the_model():
    weak = "What Is Compound Interest and Does It Help Savers Today?"
    model = _model(_set(weak, *GOOD))

    titles = await _titles(model)

    assert titles[0] == "What Is Compound Interest and Does It Help Savers?"
    assert titles[1:] == GOOD
    assert model.ainvoke.call_count == 1


@pytest.mark.asyncio
async def test_an_ending_that_has_to_be_written_anew_goes_to_the_repair():
    filler = "What Is Compound Interest? A Simple Explanation for You"
    cut = "What Is Compound Interest? Examples to Enhance Your"
    rewritten = "What Is Compound Interest? A Simple Explanation in 5 Steps"
    finished = "What Is Compound Interest? Examples From Savings Accounts"
    model = _model(_set(filler, cut, *GOOD[:3]), _set(rewritten, finished, *GOOD[:3]))

    titles = await _titles(model)

    assert titles == [rewritten, finished, *GOOD[:3]]
    assert model.ainvoke.call_count == 2
    sent = "\n".join(str(message.content) for message in model.ainvoke.call_args.args[0])
    assert "ending_filler:for you" in sent
    assert "ending_unfinished:your" in sent
    assert "TITLE ENDINGS:" in sent
    assert "finishes its thought with something specific to the topic" in sent
    # Only the two weak ones were sent for repair.
    assert GOOD[0] not in sent


@pytest.mark.asyncio
async def test_a_repair_that_ends_no_better_or_breaks_the_title_leaves_it_as_it_was():
    filler = "What Is Compound Interest? A Simple Explanation for You"
    cut = "What Is Compound Interest? Examples to Enhance Your"
    still_filler = "What Is Compound Interest? A Simple Explanation Right Now"
    too_short = "What Is Compound Interest?"
    model = _model(_set(filler, cut, *GOOD[:3]), _set(still_filler, too_short, *GOOD[:3]))

    titles = await _titles(model)

    # Both stay: a valid title is never dropped for its ending.
    assert titles == [filler, cut, *GOOD[:3]]


@pytest.mark.asyncio
async def test_a_failed_repair_call_leaves_the_set_as_it_was():
    filler = "What Is Compound Interest? A Simple Explanation for You"
    model = _model(_set(filler, *GOOD), RuntimeError("the model is away"))

    assert await _titles(model) == [filler, *GOOD]


@pytest.mark.asyncio
async def test_an_invalid_title_and_a_weak_ending_go_to_one_repair_together():
    filler = "What Is Compound Interest? A Simple Explanation for You"
    short = "What Is Compound Interest"
    rewritten = "What Is Compound Interest? A Simple Explanation in 5 Steps"
    lengthened = "What Is Compound Interest and Why Savers Care About It"
    model = _model(_set(filler, short, *GOOD[:3]), _set(rewritten, lengthened, *GOOD[:3]))

    titles = await _titles(model)

    assert titles == [rewritten, lengthened, *GOOD[:3]]
    assert model.ainvoke.call_count == 2


@pytest.mark.asyncio
async def test_a_rewrite_of_a_broken_title_loses_its_filler_too():
    """The title broke the rules, so its ending was never on the list of weak ones. Its
    rewrite is valid and ends on a filler word: the word is dropped, as in any title."""
    short = "What Is Compound Interest"
    rewritten = "What Is Compound Interest? Understanding Its Formula Now"
    model = _model(_set(short, *GOOD[1:4]), _set(rewritten, *GOOD[1:4]))

    titles = await _titles(model)

    assert titles == [GOOD[0], *GOOD[1:4]]


@pytest.mark.asyncio
async def test_a_broken_title_takes_a_valid_rewrite_even_one_that_ends_weakly():
    """A valid title beats one that breaks the rules: the last net may drop a topic it can't
    mend. Dropping this filler word would leave the title too short, so it stays."""
    short = "What Is Compound Interest"
    rewritten = "What Is Compound Interest and How Does It Work Easily?"
    assert title_is_valid(rewritten, KEYPHRASE)
    model = _model(_set(short, *GOOD[:3]), _set(rewritten, *GOOD[:3]))

    titles = await _titles(model)

    assert titles == [rewritten, *GOOD[:3]]


@pytest.mark.asyncio
async def test_a_title_left_short_is_lifted_without_a_second_call_to_the_model():
    short_of_it = "What Is Compound Interest in Simple Terms for You Now"
    assert without_filler_ending(short_of_it, KEYPHRASE)
    model = _model(_set(short_of_it, *GOOD))

    titles = await _titles(model)

    assert titles[0] == without_filler_ending(short_of_it, KEYPHRASE)
    assert tg._weak_ending_indexes(_set(*titles), KEYPHRASE) == []
    assert model.ainvoke.call_count == 1


@pytest.mark.asyncio
async def test_a_repair_never_gives_a_topic_another_topics_title():
    """The repair answers with a title another topic already has, or with one that would
    become it once its filler word is mended: the set keeps its five different choices."""
    twin = "What Is Compound Interest in Simple Terms for You: A Guide"
    weak = "What Is Compound Interest? A Simple Explanation for You"
    model = _model(
        _set(twin, weak, *GOOD[:3]),
        _set(twin, "What Is Compound Interest in Simple Terms for You Now", *GOOD[:3]),
    )

    titles = await _titles(model)

    assert len({title.casefold() for title in titles}) == len(titles)
    assert titles[0] == twin


def test_two_topics_are_not_made_one_by_dropping_a_filler_word():
    """Two choices that differ by the filler word alone: the longer keeps its word, and its
    ending is left to the repair."""
    plain = "What Is Compound Interest? Understanding Its Formula"
    topics = _set(plain, f"{plain} Now", *GOOD[1:3])

    tg._drop_filler_endings(topics, KEYPHRASE)

    assert [topic.title for topic in topics.topics][:2] == [plain, f"{plain} Now"]
    assert tg._weak_ending_indexes(topics, KEYPHRASE) == [1]


def test_the_title_step_logs_no_title(monkeypatch):
    """A title carries the customer's keyphrase: the log names the topic's place only."""
    logged = []
    monkeypatch.setattr(tg.logger, "info", lambda *args, **kwargs: logged.append((args, kwargs)))
    topics = _set("What Is Compound Interest? Understanding Its Formula Now", *GOOD[1:4])

    tg._drop_filler_endings(topics, KEYPHRASE)

    assert topics.topics[0].title == GOOD[0]
    assert logged and "Compound" not in repr(logged)


@pytest.mark.asyncio
async def test_a_set_that_ends_well_is_not_sent_for_repair():
    model = _model(_set(*GOOD, "What Is Compound Interest? How Banks Work It Out Daily"))

    await _titles(model)

    assert model.ainvoke.call_count == 1
