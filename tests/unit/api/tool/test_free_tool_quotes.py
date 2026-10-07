"""The free tools return titles and lines without the quote marks a model wraps them in (G73,
revnix/rext-control#597): the Topic Generator sent each title as "\\"10 Ways to…\\"". One surrounding
pair of matching quotes comes off (straight or curly, double or single); quotes inside stay.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.tool.schema.schema import (
    HookGeneratorRequest,
    IdeaGeneratorRequest,
    IdeaGeneratorResponse,
    SEOBlogTitleRequest,
)
from src.api.tool.tools import (
    _list_items,
    _unquote,
    generate_content_ideas,
    generate_hooks,
    generate_questions,
    generate_seo_blog_titles,
)

LEFT_DOUBLE, RIGHT_DOUBLE = "“", "”"
LEFT_SINGLE, RIGHT_SINGLE = "‘", "’"


@pytest.mark.parametrize(
    "wrapped",
    [
        '"10 Ways to Plan Content"',
        "'10 Ways to Plan Content'",
        f"{LEFT_DOUBLE}10 Ways to Plan Content{RIGHT_DOUBLE}",
        f"{LEFT_SINGLE}10 Ways to Plan Content{RIGHT_SINGLE}",
        '  "10 Ways to Plan Content"  ',
    ],
)
def test_one_wrapping_pair_comes_off_each_kind(wrapped):
    assert _unquote(wrapped) == "10 Ways to Plan Content"


def test_quotes_inside_a_title_stay():
    assert _unquote('"Why "Less" Is More"') == 'Why "Less" Is More'
    assert _unquote(f"{LEFT_DOUBLE}The {LEFT_SINGLE}Best{RIGHT_SINGLE} Plan{RIGHT_DOUBLE}") == (
        f"The {LEFT_SINGLE}Best{RIGHT_SINGLE} Plan"
    )
    assert _unquote("A title with no quotes") == "A title with no quotes"


def test_only_a_matching_pair_and_only_one_comes_off():
    # Unmatched marks are part of the text: an opening apostrophe, mixed kinds.
    assert (
        _unquote("'90s Marketing Ideas That Still Work") == "'90s Marketing Ideas That Still Work"
    )
    assert _unquote(f'"Mixed marks{RIGHT_DOUBLE}') == f'"Mixed marks{RIGHT_DOUBLE}'
    # Doubled wrapping loses one pair, not both.
    assert _unquote('""Twice""') == '"Twice"'
    assert _unquote('""') == ""


def test_a_list_loses_its_markers_quotes_and_blank_lines():
    raw = "\n1. \"First title\"\n2) “Second title”\n\n- 'Third title'\n* Fourth title\n• Fifth\n"
    assert _list_items(raw) == [
        "First title",
        "Second title",
        "Third title",
        "Fourth title",
        "Fifth",
    ]
    # A title that starts with a number keeps it.
    assert _list_items("10 Ways to Plan Content") == ["10 Ways to Plan Content"]


def test_a_number_is_numbering_only_when_it_continues_the_count():
    # A title that starts with a year keeps it, alone or inside a numbered list.
    assert _list_items("2026. What Changes for Content Marketing?") == [
        "2026. What Changes for Content Marketing?"
    ]
    assert _list_items('1. "First"\n2. Second\n2026. What Changes') == [
        "First",
        "Second",
        "2026. What Changes",
    ]
    # A bulleted line's number is the title's own.
    assert _list_items("- 3. Steps to a Brief") == ["3. Steps to a Brief"]


def _model(content=None, structured=None):
    model = MagicMock()
    response = MagicMock()
    response.content = content
    model.ainvoke = AsyncMock(return_value=response)
    if structured is not None:
        structured_model = MagicMock()
        structured_model.ainvoke = AsyncMock(return_value=structured)
        model.with_structured_output = MagicMock(return_value=structured_model)
    return model


@pytest.mark.asyncio
async def test_the_topic_generator_returns_titles_without_quotes():
    content = '"10 Ways to Plan Content"\n“A Guide to Content Calendars”\n"Why ‘Less’ Is More"'
    with patch("src.api.tool.tools._get_model", return_value=_model(content)):
        result = await generate_seo_blog_titles(
            SEOBlogTitleRequest(keyword="content planning", number_of_topics=2)
        )
    assert result.blog_titles == ["10 Ways to Plan Content", "A Guide to Content Calendars"]


@pytest.mark.asyncio
async def test_hooks_and_questions_come_back_without_quotes():
    with patch(
        "src.api.tool.tools._get_model", return_value=_model('- "Stop guessing."\n- "Start here."')
    ):
        hooks = await generate_hooks(
            HookGeneratorRequest(
                topic_description="content planning",
                goal_of_content="sign-ups",
                number_of_variations=2,
            )
        )
    assert hooks.hooks == ["Stop guessing.", "Start here."]

    with patch(
        "src.api.tool.tools._get_model",
        return_value=_model('1. "What is a brief?"\n2. "Who writes it?"'),
    ):
        questions = await generate_questions("A text about briefs.")
    assert questions == ["What is a brief?", "Who writes it?"]


@pytest.mark.asyncio
async def test_content_ideas_come_back_without_quotes():
    structured = IdeaGeneratorResponse(
        topic="content planning", ideas=['"A calendar template"', "“A weekly review”", '""']
    )
    with patch("src.api.tool.tools._get_model", return_value=_model(structured=structured)):
        result = await generate_content_ideas(
            IdeaGeneratorRequest(topic="content planning", content_type="blog", ideas_count=2)
        )
    assert result.ideas == ["A calendar template", "A weekly review"]
