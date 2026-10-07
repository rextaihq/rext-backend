"""The outline sidebar's keywords, tone and audience reach the writer and the rewrite (FB2.18,
revnix/rext-control#699). The keywords couldn't be edited, were weighted like the focus keyphrase
and never checked; the rewrite was told neither the tone nor the audience."""

import json
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage

import src.flow.engines.content.generation.content_generation as node
import src.flow.engines.content.review.outline as review_module
from src.flow.engines.content.generation.humanize_content import _build_prompt_data
from src.flow.engines.content.generation.requirements_spec import build_requirements_spec
from src.flow.engines.content.generation.validation import check_secondary_keywords
from src.flow.engines.content.review.outline import _clean_keywords
from src.flow.prompts.human.humanize import get_humanize_prompt
from src.flow.prompts.system.humanize import HUMANIZE_SYSTEM_PROMPT

FOCUS = "content calendar template"
ARTICLE = {
    "title": "How to use a content calendar template",
    "meta_description": "A content calendar template for small teams.",
    "introduction": "A content calendar template keeps a small team on schedule.",
    "body_markdown": "## Plan the month\n\nPick themes, then dates. An editorial calendar helps.",
}


# -- The gate: the user's keyword list --------------------------------------------------


def test_the_keyword_list_is_cleaned():
    assert _clean_keywords(
        ["  editorial  calendar ", "Editorial Calendar", 42, "", "social media plan", None]
    ) == ["editorial calendar", "social media plan"]
    assert _clean_keywords("not a list") is None
    assert len(_clean_keywords([f"keyword {i}" for i in range(40)])) == 20
    assert len(_clean_keywords(["x" * 200])[0]) == 80


def _approve(monkeypatch, response):
    monkeypatch.setattr(review_module, "interrupt", lambda _payload: response)
    state = {
        "content": {
            "content_type": "blog",
            "outline": {
                "title": ARTICLE["title"],
                "sections": [],
                "focus_keyphrase": FOCUS,
                "keywords_to_include": [FOCUS, "editorial calendar"],
            },
        }
    }
    return review_module.review_outline(state)["content"]["outline"]


@pytest.mark.unit
def test_the_users_keywords_replace_the_outlines_with_the_focus_keyphrase_first(monkeypatch):
    outline = _approve(
        monkeypatch,
        {"action": "approve", "keywords_to_include": ["social media plan", "posting schedule"]},
    )

    assert outline["keywords_to_include"] == [FOCUS, "social media plan", "posting schedule"]


@pytest.mark.unit
def test_without_a_keyword_list_the_outlines_stay(monkeypatch):
    outline = _approve(monkeypatch, {"action": "approve"})

    assert outline["keywords_to_include"] == [FOCUS, "editorial calendar"]


# -- The spec and the check -------------------------------------------------------------


def _spec(keywords):
    return build_requirements_spec(
        {"title": ARTICLE["title"], "keywords_to_include": keywords}, "blog", focus_keyword=FOCUS
    )


def test_the_secondary_keywords_are_the_approved_ones_without_the_focus_keyphrase():
    spec = _spec([FOCUS, "editorial calendar", "Content Calendar Template"])

    assert spec["secondary_keywords"] == ["editorial calendar"]


def test_every_secondary_keyword_present_passes():
    assert check_secondary_keywords(ARTICLE, _spec([FOCUS, "editorial calendar"]))["passed"]


def test_a_missing_secondary_keyword_is_a_warning_not_a_block():
    result = check_secondary_keywords(ARTICLE, _spec([FOCUS, "editorial calendar", "batching"]))

    assert result["passed"] is False and result["severity"] == "warning"
    assert "'batching'" in result["detail"] and "editorial calendar" not in result["detail"]


# -- What the writer is told ------------------------------------------------------------


class _Writer:
    def __init__(self, seen):
        self.seen = seen

    async def astream_events(self, payload, *_args, **_kwargs):
        self.seen.extend(payload["messages"])
        yield {
            "event": "on_chain_end",
            "name": "agent",
            "run_id": "root",
            "data": {"output": {"messages": [AIMessage(content=json.dumps(ARTICLE))]}},
        }


@pytest.mark.asyncio
async def test_the_writer_gets_the_focus_keyphrase_apart_from_the_secondary_keywords(
    monkeypatch,
):
    seen = []

    async def nothing(*_args, **_kwargs):
        return None

    async def create_content_agent(**_kwargs):
        return _Writer(seen)

    monkeypatch.setattr(node, "consume_stage_credits", nothing)
    monkeypatch.setattr(node, "_fetch_known_entities", AsyncMock(return_value=(None, [])))
    monkeypatch.setattr(node, "research_official_facts", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        node,
        "enforce_subheadings_for_spec",
        AsyncMock(side_effect=lambda content, *a, **k: content),
    )
    monkeypatch.setattr(node, "get_stream_writer", lambda: lambda _event: None)
    monkeypatch.setattr(node, "can_afford_stage", AsyncMock(return_value=False))
    monkeypatch.setattr(node, "create_content_agent", create_content_agent)
    await node.generate_content(
        {
            "content": {
                "selected_topic": ARTICLE["title"],
                "content_type": "blog",
                "outline": {
                    "focus_keyphrase": FOCUS,
                    "keywords_to_include": [FOCUS, "editorial calendar", "posting schedule"],
                },
            },
            "serp_payload": {"user_id": "u", "workspace_id": "w", "keyword": FOCUS},
        }
    )
    message = "\n".join(str(m.content) for m in seen)

    assert f'Focus keyphrase: "{FOCUS}"' in message
    assert "Secondary keywords the user approved: editorial calendar, posting schedule" in message
    assert "Use each secondary keyword at least once" in message


# -- What the rewrite is told -----------------------------------------------------------


def test_the_rewrite_gets_the_reader_the_tone_and_the_secondary_keywords():
    data = _build_prompt_data(
        content_payload=dict(ARTICLE),
        content_type="blog",
        focus_keyword=FOCUS,
        secondary_keywords=["editorial calendar"],
        audience=["Marketing leads", "Small agencies"],
        tone="Practical, plain-spoken",
    )

    assert "Written for: Marketing leads, Small agencies" in data["reader_instruction"]
    assert "Tone: Practical, plain-spoken" in data["reader_instruction"]
    assert "secondary keywords; keep each at least once" in data["keyword_instruction"]
    assert "editorial calendar" in data["keyword_instruction"]
    human = get_humanize_prompt().format_messages(**data)[1].content
    assert "READER AND TONE" in human


def test_the_rewrite_template_has_no_unfilled_placeholders():
    for placeholder in (
        "[exact persona + skill level]",
        "[casual/direct/spicy/calm]",
        "(fill these)",
    ):
        assert placeholder not in HUMANIZE_SYSTEM_PROMPT


def test_without_a_reader_or_tone_nothing_is_added():
    data = _build_prompt_data(content_payload=dict(ARTICLE), content_type="blog")

    assert data["reader_instruction"] == ""
