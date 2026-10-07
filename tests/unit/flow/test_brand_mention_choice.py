"""The brand-mention choice at the outline gate is followed exactly (rext-control#700).

"None" used only to skip the promotion blocks: nothing told the writer to keep the brand out, every
brand check skipped, and an outline generated before the choice could already name the brand, so a
mention could ship. "Subtle" keeps the brand out of a call to action, which an outline's call to
action naming the brand contradicted.
"""

import json
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage

import src.flow.engines.content.generation.content_generation as node
from src.flow.engines.agent.middleware.persona_middleware import PersonaInjectionMiddleware
from src.flow.engines.content.generation.humanize_content import _build_prompt_data
from src.flow.engines.content.generation.requirements_spec import (
    brand_kept_out_of_cta,
    brand_named_in,
    build_requirements_spec,
    excluded_brand_of,
)
from src.flow.engines.content.generation.validation import check_brand_absent

BRAND = {"brand_name": "Acme Tools", "brand_url": "https://www.acme.test/"}
ARTICLE = {
    "title": "How to plan a vegetable garden",
    "meta_title": "How to plan a vegetable garden",
    "meta_description": "A plan for a vegetable garden.",
    "introduction": "Plan a vegetable garden before you dig.",
    "body_markdown": "## Choose the spot\n\nSun matters most.",
    "cta": {"text": "Start planning your garden today"},
}


def _outline(prominence, **extra):
    return {
        "title": ARTICLE["title"],
        "brand_prominence": prominence,
        "promote_brand": prominence in ("prominent", "subtle"),
        "brand_voice_promotion": dict(BRAND),
        **extra,
    }


# -- Which brand stays out ------------------------------------------------------------


def test_none_keeps_the_brand_out_and_the_others_do_not():
    assert excluded_brand_of(_outline("none")) == {
        "brand_name": "Acme Tools",
        "brand_url": "https://www.acme.test/",
    }
    assert excluded_brand_of(_outline("subtle")) is None
    assert excluded_brand_of(_outline("prominent")) is None
    assert excluded_brand_of({"brand_prominence": "none"}) is None  # no brand known


def test_none_and_subtle_keep_the_brand_out_of_the_call_to_action():
    assert brand_kept_out_of_cta(_outline("none")) == "Acme Tools"
    assert brand_kept_out_of_cta(_outline("subtle")) == "Acme Tools"
    assert brand_kept_out_of_cta(_outline("prominent")) == ""


@pytest.mark.parametrize(
    ("text", "named"),
    [
        ("Try Acme Tools free", True),
        ("try acme tools today", True),
        ("Acme Toolshed is different", False),
        ("Plan your garden", False),
    ],
)
def test_a_brand_is_named_as_a_word_of_its_own(text, named):
    assert brand_named_in(text, "Acme Tools") is named


def test_the_spec_carries_the_excluded_brand_only_for_none():
    assert build_requirements_spec(_outline("none"), "blog")["excluded_brand"]["brand_name"] == (
        "Acme Tools"
    )
    assert build_requirements_spec(_outline("subtle"), "blog")["excluded_brand"] is None


# -- The check -------------------------------------------------------------------------


def _absent(article, prominence="none"):
    return check_brand_absent(article, build_requirements_spec(_outline(prominence), "blog"))


def test_an_article_without_the_brand_passes():
    assert _absent(ARTICLE)["passed"] is True


@pytest.mark.parametrize(
    ("field", "value", "place"),
    [
        ("title", "Acme Tools: how to plan a garden", "title"),
        ("meta_description", "Plan a garden with Acme Tools.", "meta description"),
        ("introduction", "acme tools makes this easy.", "introduction"),
        ("body_markdown", "## Tools\n\nWe use [a planner](https://acme.test/planner).", "body"),
        ("cta", {"text": "Try Acme Tools free"}, "call to action"),
    ],
)
def test_a_mention_anywhere_blocks_under_none(field, value, place):
    result = _absent({**ARTICLE, field: value})

    assert result["passed"] is False and result["severity"] == "blocking"
    assert place in result["detail"] and "Acme Tools" in result["detail"]


def test_with_a_mention_approved_the_check_does_not_apply():
    article = {**ARTICLE, "body_markdown": "Acme Tools helps here."}
    assert _absent(article, "subtle")["passed"] is True
    assert _absent(article, "prominent")["passed"] is True


# -- What the writer, the system prompt and the rewrite are told -----------------------


class _Writer:
    """The content agent: records the messages it was given, then returns the article."""

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


@pytest.fixture
def writer_message(monkeypatch):
    """The human message generate_content gives the writer, for a given outline."""

    async def consume(*_args, **_kwargs):
        return None

    monkeypatch.setattr(node, "consume_stage_credits", consume)
    monkeypatch.setattr(node, "_fetch_known_entities", AsyncMock(return_value=(None, [])))
    monkeypatch.setattr(node, "research_official_facts", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        node,
        "enforce_subheadings_for_spec",
        AsyncMock(side_effect=lambda content, *a, **k: content),
    )
    monkeypatch.setattr(node, "get_stream_writer", lambda: lambda _event: None)
    monkeypatch.setattr(node, "can_afford_stage", AsyncMock(return_value=False))

    async def go(outline):
        seen = []

        async def create_content_agent(**_kwargs):
            return _Writer(seen)

        monkeypatch.setattr(node, "create_content_agent", create_content_agent)
        await node.generate_content(
            {
                "content": {
                    "selected_topic": ARTICLE["title"],
                    "content_type": "blog",
                    "outline": outline,
                },
                "serp_payload": {"user_id": "u", "workspace_id": "w", "keyword": "garden"},
            }
        )
        return "\n".join(str(m.content) for m in seen)

    return go


@pytest.mark.asyncio
async def test_under_none_the_writer_is_told_to_keep_the_brand_out(writer_message):
    message = await writer_message(_outline("none"))

    assert "BRAND EXCLUSION — REQUIRED" in message
    assert "The user chose NO mention of Acme Tools" in message
    assert "FINAL CHECK BEFORE YOU WRITE: Acme Tools appears nowhere" in message
    assert "PRODUCT-LED MENTION" not in message


@pytest.mark.asyncio
@pytest.mark.parametrize("prominence", ["none", "subtle"])
async def test_a_call_to_action_naming_the_brand_is_rewritten_without_it(
    writer_message, prominence
):
    outline = _outline(prominence, final_cta={"primary_cta": "Get started with Acme Tools"})

    message = await writer_message(outline)

    assert "It names Acme Tools, but the user's choice keeps Acme Tools out" in message
    assert "WITHOUT naming Acme Tools" in message
    assert "using this exact CTA text" not in message


@pytest.mark.asyncio
async def test_a_prominent_call_to_action_keeps_its_exact_text(writer_message):
    outline = _outline("prominent", final_cta={"primary_cta": "Get started with Acme Tools"})

    message = await writer_message(outline)

    assert "using this exact CTA text" in message
    assert "BRAND EXCLUSION" not in message


def test_the_system_prompt_states_the_exclusion():
    block = PersonaInjectionMiddleware()._build_brand_placement_block(_outline("none"), "blog")

    assert block.startswith("## BRAND EXCLUSION — MANDATORY")
    assert "NO mention of Acme Tools" in block


def test_the_rewrite_is_told_to_keep_the_brand_out():
    data = _build_prompt_data(
        content_payload=dict(ARTICLE),
        content_type="blog",
        excluded_brand=excluded_brand_of(_outline("none")),
    )

    assert data["brand_instruction"].startswith("BRAND EXCLUSION")
    assert "Acme Tools" in data["brand_instruction"]
