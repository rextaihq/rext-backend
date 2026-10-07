"""A long keyword gets title choices and never stops the run at the title step (G69, #585).

Every title must hold the whole keyphrase, so 59 characters left a 48-character keyphrase about
11 for anything else: four of five titles were dropped as too long, and the one left was below
the minimum. The limit now grows with the keyphrase (59, or the keyphrase plus 20, never over
75), one title is enough to go on, and when none survives the keyphrase itself is offered.
"""

from unittest.mock import AsyncMock

import pytest

from src.flow.engines.content.generation import topic_generation as tg
from src.flow.engines.content.generation.seo_title_rules import (
    contains_keyphrase,
    keyphrase_fits_a_title,
    keyphrase_title,
    repair_title,
    title_is_valid,
    title_max_chars,
    title_violations,
)
from src.flow.model.structure.topics import SEOTopic, SEOTopics

LONG = "best project management software for small teams"  # 48 characters
SHORT = "seo agencies"


def _topics(*titles: str) -> SEOTopics:
    return SEOTopics(topics=[SEOTopic(title=t, recommended=(i == 0)) for i, t in enumerate(titles)])


def test_the_limit_grows_with_the_keyphrase_up_to_75():
    assert len(LONG) == 48
    assert title_max_chars(SHORT) == 59  # a short keyword keeps today's limit
    assert title_max_chars("") == 59
    assert title_max_chars(LONG) == 68  # 48 + 20
    assert title_max_chars("x" * 60) == 75  # 80, capped
    assert title_max_chars("x" * 75) == 75


def test_a_short_keyword_behaves_as_today():
    title = "SEO Agencies for Small Businesses: How to Choose One Wisely"
    assert len(title) == 59 and title_is_valid(title, SHORT)
    assert title_violations(title + "!", SHORT) == ["too_long:60"]


def test_titles_for_a_long_keyword_fit_within_its_limit():
    fits = "Best Project Management Software for Small Teams: How to Choose"  # 63
    too_long = "Best Project Management Software for Small Teams: A Buyer's Guide for 2026"
    assert len(fits) == 63 and title_is_valid(fits, LONG)
    assert len(too_long) == 74 and title_violations(too_long, LONG) == ["too_long:74"]

    repaired = repair_title(too_long, LONG)
    assert repaired is not None
    assert len(repaired) <= 68 and contains_keyphrase(repaired, LONG)


def test_a_keyphrase_over_59_characters_still_gets_a_title():
    keyphrase = "affordable project management software for remote nonprofit teams"  # 65
    assert len(keyphrase) == 65
    assert keyphrase_fits_a_title(keyphrase)

    title = keyphrase_title(keyphrase)

    assert title_is_valid(title, keyphrase), title
    assert len(title) <= 75


@pytest.mark.asyncio
async def test_the_long_keyword_from_the_report_gets_titles():
    """The titles the model wrote for it (62-74 characters): those within 68 stay, the longer
    ones are trimmed or dropped, and the step goes on with what is left."""
    written = _topics(
        "Best Project Management Software for Small Teams: Top Picks Now",  # 63
        "Best Project Management Software for Small Teams: Features Compared",  # 67
        "Best Project Management Software for Small Teams: A Practical Guide",  # 67
        "Best Project Management Software for Small Teams: Pricing and Features",  # 70
        "Best Project Management Software for Small Teams in 2026: Ranked and Reviewed",  # 77
    )
    model = AsyncMock()
    model.ainvoke.side_effect = [written, RuntimeError("repair model down")]

    result = await tg._generate_and_validate_topics(
        model=model, messages=[], query=LONG, keyphrase=LONG
    )

    assert result is not None
    assert len(result.topics) >= 3
    for topic in result.topics:
        assert title_is_valid(topic.title, LONG), topic.title
    assert sum(1 for topic in result.topics if topic.recommended) == 1


@pytest.mark.asyncio
async def test_one_valid_title_is_enough_to_go_on():
    model = AsyncMock()
    model.ainvoke.side_effect = [
        _topics("Best Project Management Software for Small Teams: How to Choose"),
    ]

    result = await tg._generate_and_validate_topics(
        model=model, messages=[], query=LONG, keyphrase=LONG
    )

    assert result is not None and len(result.topics) == 1


@pytest.mark.asyncio
async def test_when_no_title_survives_the_keyphrase_is_offered(monkeypatch):
    """Nothing the model wrote can be used and nothing can be repaired: the keyphrase itself,
    in title case and lifted to the minimum, is the one title, rather than ending the run."""
    monkeypatch.setattr(tg, "repair_title", lambda title, keyphrase: None)
    model = AsyncMock()
    model.ainvoke.side_effect = [
        _topics("Team Tools", "Pick a Planner"),  # no keyphrase, and nothing to repair from
        RuntimeError("repair model down"),
    ]

    result = await tg._generate_and_validate_topics(
        model=model, messages=[], query=LONG, keyphrase=LONG
    )

    assert result is not None
    [topic] = result.topics
    # Each word capitalized, as the repair's keyphrase lead is; matching ignores case.
    assert topic.title.startswith("Best Project Management Software For Small Teams")
    assert title_is_valid(topic.title, LONG), topic.title
    assert topic.recommended


def test_the_prompt_states_the_keyphrases_limit():
    prompt = tg._build_system_prompt(
        keyphrase=LONG,
        current_year=2026,
        selected_intent="commercial",
        selected_content_type="comparison",
    )

    assert "BETWEEN 50 AND 68" in prompt
    assert "BETWEEN 50 AND 59" not in prompt
