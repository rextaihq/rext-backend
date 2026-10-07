"""The featured image's credit is charged only when an image is delivered (rext-control G66 #562).

The founder's decision, 2026-10-07: images at 1 credit, charged on delivery. The writer is
a stand-in that calls the real generate_image tool, so the tool's own gate decides whether
an image is made; the image model, the research and the credit store are never reached.
"""

import json
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage

import src.flow.engines.agent.tools.tools as tools_module
import src.flow.engines.content.generation.content_generation as node
from src.api.config import settings
from src.utils.credit_manager import STAGE_CREDITS, InsufficientCreditsError

USER_ID = "00000000-0000-0000-0000-000000000001"
WORKSPACE_ID = "00000000-0000-0000-0000-000000000002"
IMAGE_URL = "https://media.rext.test/featured/one.png"
ARTICLE = {
    "title": "How to plan a vegetable garden",
    "meta_description": "A plan for a vegetable garden.",
    "introduction": "Plan a vegetable garden before you dig.",
    "body_markdown": "## Choose the spot\n\nSun matters most.",
    "faqs": [],
    "facts": [],
}
# The article's other stages, charged before this node: SERP, title, outline, E-E-A-T.
EARLIER_STAGES = sum(
    STAGE_CREDITS[s]
    for s in ("serp_seo", "title_generation", "generate_outline", "eeat_optimization")
)


class _Writer:
    """The content agent: calls generate_image once, then returns the article."""

    def __init__(self, counters):
        self.counters = counters

    async def astream_events(self, *_args, **_kwargs):
        generate_image = next(
            t for t in tools_module.get_tools(self.counters) if t.name == "generate_image"
        )
        await generate_image.ainvoke({"title": ARTICLE["title"], "content_type": "blog"})
        yield {
            "event": "on_chain_end",
            "name": "agent",
            "run_id": "root",
            "data": {"output": {"messages": [AIMessage(content=json.dumps(ARTICLE))]}},
        }


@pytest.fixture
def run(monkeypatch):
    """Runs generate_content with the given image outcome; returns the stages charged and the state."""

    charged = []

    async def consume(user_id, cost, stage, workspace_id=None):
        charged.append((stage, cost))

    monkeypatch.setattr(node, "consume_stage_credits", consume)
    monkeypatch.setattr(node, "_fetch_known_entities", AsyncMock(return_value=(None, [])))
    monkeypatch.setattr(node, "research_official_facts", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        node,
        "enforce_subheadings_for_spec",
        AsyncMock(side_effect=lambda content, *a, **k: content),
    )
    monkeypatch.setattr(node, "get_stream_writer", lambda: lambda _event: None)

    async def create_content_agent(*, counters, **_kwargs):
        return _Writer(counters)

    monkeypatch.setattr(node, "create_content_agent", create_content_agent)

    async def go(*, enabled=True, image=IMAGE_URL, affordable=True, state=None):
        monkeypatch.setattr(settings, "AI_IMAGE_GENERATION_ENABLED", enabled)
        monkeypatch.setattr(node, "can_afford_stage", AsyncMock(return_value=affordable))

        async def standalone(*_args, **_kwargs):
            go.images_made += 1
            if isinstance(image, Exception):
                raise image
            return image

        monkeypatch.setattr(tools_module, "generate_image_standalone", standalone)
        content = {
            "selected_topic": ARTICLE["title"],
            "content_type": "blog",
            "outline": {},
            **(state or {}),
        }
        result = await node.generate_content(
            {
                "content": content,
                "serp_payload": {
                    "user_id": USER_ID,
                    "workspace_id": WORKSPACE_ID,
                    "keyword": "garden",
                },
            }
        )
        return charged, result["content"]

    go.images_made = 0
    return go


def _article_total(charged) -> int:
    return EARLIER_STAGES + sum(cost for _stage, cost in charged)


@pytest.mark.asyncio
async def test_with_generation_off_the_image_is_not_charged(run):
    charged, content = await run(enabled=False)

    assert "featured_image" not in [stage for stage, _ in charged]
    assert _article_total(charged) == 14
    assert IMAGE_URL not in content["final_content"]["body_markdown"]


@pytest.mark.asyncio
async def test_a_delivered_image_is_charged_once(run):
    charged, content = await run()

    assert run.images_made == 1
    assert [stage for stage, _ in charged].count("featured_image") == 1
    assert _article_total(charged) == 15
    assert IMAGE_URL in content["final_content"]["body_markdown"]
    assert content["image_credit_deducted"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", [RuntimeError("image model down"), None, "not-a-url"])
async def test_an_image_that_failed_is_not_charged(run, outcome):
    charged, content = await run(image=outcome)

    assert "featured_image" not in [stage for stage, _ in charged]
    assert _article_total(charged) == 14
    assert not content.get("image_credit_deducted")


@pytest.mark.asyncio
async def test_a_resumed_run_charges_nothing_twice(run):
    charged, _ = await run(state={"credits_deducted": True, "image_credit_deducted": True})

    assert charged == []


@pytest.mark.asyncio
async def test_a_run_that_cannot_pay_for_the_image_does_not_generate_one(run):
    charged, content = await run(affordable=False)

    assert "featured_image" not in [stage for stage, _ in charged]
    assert IMAGE_URL not in content["final_content"]["body_markdown"]
    # The writer got the manual-upload placeholder instead.
    assert any(
        image.get("status") == "pending_manual_upload"
        for image in content["final_content"]["images"]
    )
    assert run.images_made == 0


@pytest.mark.asyncio
async def test_a_charge_refused_after_delivery_keeps_the_image(run, monkeypatch):
    """The balance fell short between the check and the delivery: the article keeps its
    image and the run doesn't fail."""

    async def consume(user_id, cost, stage, workspace_id=None):
        if stage == "featured_image":
            raise InsufficientCreditsError(stage, cost, 0)

    monkeypatch.setattr(node, "consume_stage_credits", consume)

    _, content = await run()

    assert IMAGE_URL in content["final_content"]["body_markdown"]
    assert not content.get("image_credit_deducted")
    assert not content.get("error")
