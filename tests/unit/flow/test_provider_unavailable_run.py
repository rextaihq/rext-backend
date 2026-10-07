"""An outage in the outline or the article ends the run with a notice (G75.1, rext-control#614).

When the AI provider is unavailable, the model steps return the notice instead of raising, and the
graph ends the run at provider_unavailable with a run.failed event and content.error, as
topics_failed and no_serp_data do. The provider's errors are built as the OpenAI client raises them.
"""

import httpx
import openai
import pytest
from langgraph.graph import END

import src.flow.engines.content.generation.content_generation as content_module
import src.flow.engines.content.generation.outline as outline_module
import src.flow.engines.content.generation.provider_unavailable as module
from src.flow.engines.content.content_engine import create_content_engine
from src.flow.engines.content.generation.provider_unavailable import (
    PROVIDER_UNAVAILABLE_CODE,
    PROVIDER_UNAVAILABLE_MESSAGE,
    PROVIDER_UNAVAILABLE_NODE,
    StoppedAfterCharge,
    provider_unavailable,
    stop_on_outage,
    unless_outage,
)
from src.utils import credit_manager

REQUEST = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")


def out_of_credits():
    return openai.RateLimitError(
        "Error code: 429 - You have no credits remaining",
        response=httpx.Response(429, request=REQUEST),
        body={"type": "insufficient_quota", "code": "credit_balance_exhausted"},
    )


NOTICE = {
    "content": {"error": PROVIDER_UNAVAILABLE_MESSAGE, "error_code": PROVIDER_UNAVAILABLE_CODE}
}


async def test_a_model_step_returns_the_notice_when_the_provider_is_out():
    @stop_on_outage
    async def step(state):
        raise out_of_credits()

    assert await step({}) == NOTICE


async def test_any_other_error_still_raises():
    @stop_on_outage
    async def step(state):
        raise ValueError("a parsing error")

    with pytest.raises(ValueError):
        await step({})


async def test_a_plain_step_works_too():
    assert await stop_on_outage(lambda state: {"content": {}})({}) == {"content": {}}


async def test_a_step_that_works_is_untouched():
    @stop_on_outage
    async def step(state):
        return {"content": {"outline": {"status": "draft"}}}

    assert await step({}) == {"content": {"outline": {"status": "draft"}}}


async def test_an_outline_the_provider_fails_costs_nothing(monkeypatch):
    charged = []

    async def balance(uid, workspace_id=None):
        return 100

    async def consume(*args, **kwargs):
        charged.append(args)

    monkeypatch.setattr(credit_manager, "_get_balance", balance)
    monkeypatch.setattr(credit_manager, "consume_stage_credits", consume)

    @stop_on_outage
    @credit_manager.deduct_credits("generate_outline")
    async def generate_outline(state):
        raise out_of_credits()

    assert await generate_outline({"user_id": "6f1c2a52-6c39-4f0e-9a51-6a3c1d0b8e11"}) == NOTICE
    assert charged == []


def test_the_router_ends_the_run_only_after_the_notice():
    route = unless_outage("review_outline")

    assert route(NOTICE) == PROVIDER_UNAVAILABLE_NODE
    assert route({"content": {"error_code": "topic_generation_failed"}}) == "review_outline"
    assert route({"content": {}}) == "review_outline"
    assert route({}) == "review_outline"


async def test_the_end_tells_the_user_through_the_stream_and_the_state(monkeypatch):
    sent = []
    monkeypatch.setattr("langgraph.config.get_stream_writer", lambda: sent.append)

    result = await provider_unavailable(NOTICE)

    assert sent == [
        {
            "type": "run",
            "step": "run.failed",
            "error_code": PROVIDER_UNAVAILABLE_CODE,
            "message": PROVIDER_UNAVAILABLE_MESSAGE,
        }
    ]
    assert result == NOTICE


def test_the_graph_ends_the_outline_and_the_article_at_provider_unavailable():
    edges = {(e.source, e.target) for e in create_content_engine().get_graph().edges}

    for step, onward in [
        ("generate_outline", "review_outline"),
        ("generate_content", "validate_content"),
    ]:
        assert (step, PROVIDER_UNAVAILABLE_NODE) in edges
        assert (step, onward) in edges
    assert (PROVIDER_UNAVAILABLE_NODE, "__end__") in edges
    # Repair and humanizing keep their best effort: the article is written, and the run saves it.
    for step in ("repair_content", "humanize_content"):
        assert (step, PROVIDER_UNAVAILABLE_NODE) not in edges


@pytest.fixture
def outline_state(monkeypatch):
    async def no_sync(workspace_id):
        return None

    monkeypatch.setattr(outline_module, "_bulk_sync_workspace", no_sync)
    return {"content": {"selected_topic": "How to plan a garden", "content_type": "blog"}}


async def test_the_outline_lets_an_outage_through_to_the_notice(monkeypatch, outline_state):
    def outage(content_type):
        raise out_of_credits()

    monkeypatch.setattr(outline_module, "get_outline_model", outage)

    assert await stop_on_outage(outline_module.generate_outline)(outline_state) == NOTICE


async def test_any_other_outline_error_ends_the_run_with_the_notice_too(monkeypatch, outline_state):
    # It kept its own message and the run went on: the review step opened on an empty outline
    # (rext-control#697). No outline is no step to review, whatever the cause.
    def broken(content_type):
        raise ValueError("a schema error")

    monkeypatch.setattr(outline_module, "get_outline_model", broken)

    assert await stop_on_outage(outline_module.generate_outline)(outline_state) == NOTICE


async def test_the_article_lets_an_outage_through_to_the_notice(monkeypatch):
    def outage(outline, content_type):
        raise out_of_credits()

    monkeypatch.setattr(content_module, "_format_outline_for_generation", outage)
    state = {"content": {"selected_topic": "How to plan a garden", "outline": {"title": "x"}}}

    result = await stop_on_outage(content_module.generate_content)(state)

    assert result["content"]["error_code"] == PROVIDER_UNAVAILABLE_CODE
    assert result["content"]["error"] == PROVIDER_UNAVAILABLE_MESSAGE
    assert "credits_deducted" not in result["content"]
    assert unless_outage("validate_content")(result) == PROVIDER_UNAVAILABLE_NODE


async def test_an_article_stopped_after_its_charge_is_not_charged_again_on_a_retry(monkeypatch):
    # From the review of #887: the notice keeps credits_deducted, so a retry on this thread skips the charge.
    charged = []

    async def consume(user_id, credits, stage, workspace_id=None):
        charged.append(stage)

    def outage(*args, **kwargs):
        raise out_of_credits()

    monkeypatch.setattr(content_module, "consume_stage_credits", consume)
    monkeypatch.setattr(content_module, "build_requirements_spec", outage)
    step = stop_on_outage(content_module.generate_content)
    state = {"content": {"selected_topic": "How to plan a garden", "outline": {"title": "x"}}}

    first = await step(state)
    retry = await step({"content": {**state["content"], **first["content"]}})

    assert charged == ["content_drafting", "humanization", "deep_research"]
    assert first["content"]["credits_deducted"] is True
    assert first["content"]["error_code"] == PROVIDER_UNAVAILABLE_CODE
    assert retry["content"]["credits_deducted"] is True
    assert retry["content"]["error_code"] == PROVIDER_UNAVAILABLE_CODE


async def test_a_step_stopped_after_a_charge_keeps_its_marks_in_the_notice():
    @stop_on_outage
    async def step(state):
        try:
            raise out_of_credits()
        except Exception as error:
            raise StoppedAfterCharge(
                {"credits_deducted": True, "image_credit_deducted": True}
            ) from error

    assert await step({}) == {
        "content": {
            "credits_deducted": True,
            "image_credit_deducted": True,
            "error": PROVIDER_UNAVAILABLE_MESSAGE,
            "error_code": PROVIDER_UNAVAILABLE_CODE,
        }
    }


async def test_a_stop_after_a_charge_without_an_outage_still_raises():
    @stop_on_outage
    async def step(state):
        raise StoppedAfterCharge({"credits_deducted": True})

    with pytest.raises(StoppedAfterCharge):
        await step({})


def test_a_refused_charge_and_an_outage_each_end_the_run_their_own_way():
    # With rext-control#524's credit gate on the same edges: a refused charge ends the run, an outage
    # ends it with the notice, anything else goes on.
    branches = create_content_engine().builder.branches
    for node, next_node in (
        ("generate_outline", "review_outline"),
        ("generate_content", "validate_content"),
    ):
        (route,) = (spec.path for spec in branches[node].values())
        assert route.invoke({"content": {"error_code": "insufficient_credits"}}) == END
        stopped = {"content": {"error_code": PROVIDER_UNAVAILABLE_CODE}}
        assert route.invoke(stopped) == PROVIDER_UNAVAILABLE_NODE
        assert route.invoke({"content": {}}) == next_node


STALE = {
    "content": {"error": PROVIDER_UNAVAILABLE_MESSAGE, "error_code": PROVIDER_UNAVAILABLE_CODE}
}


async def test_a_retry_that_works_clears_the_old_notice():
    @stop_on_outage
    async def step(state):
        return {"content": {"outline": {"status": "draft"}}}

    result = await step(STALE)

    assert result["content"] == {"outline": {"status": "draft"}, "error": None, "error_code": None}
    assert unless_outage("review_outline")({"content": result["content"]}) == "review_outline"


async def test_an_old_notice_copied_into_the_answer_is_cleared_too():
    @stop_on_outage
    async def step(state):
        return {"content": {**state["content"], "status": "content_generated"}}

    result = await step(STALE)

    assert result["content"]["error_code"] is None
    assert result["content"]["error"] is None
    assert result["content"]["status"] == "content_generated"


async def test_a_steps_own_error_is_kept_after_an_old_notice():
    @stop_on_outage
    async def step(state):
        return {"content": {"error": "Insufficient credits", "error_code": "insufficient_credits"}}

    assert (await step(STALE))["content"]["error_code"] == "insufficient_credits"


def test_the_message_makes_no_promise_about_credits():
    # The article's stages are charged before it is written; their refund is F18's (rext-control#500).
    assert "charge" not in module.PROVIDER_UNAVAILABLE_MESSAGE.lower()
    assert "credit" not in module.PROVIDER_UNAVAILABLE_MESSAGE.lower()
