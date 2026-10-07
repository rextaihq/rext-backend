import importlib
import pkgutil
import re
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from langchain_core.prompts import BasePromptTemplate

import src.api.tool.prompts as prompts
from src.api.cache.redis_client import cache
from src.api.config import get_settings
from src.api.server import app
from src.api.tool import limits
from src.api.tool.limits import (
    BUDGET_LIMIT,
    BUDGET_MESSAGE,
    FREE_TOOLS,
    MAX_INPUT_BYTES,
    PROMPT_COPIES,
    TAKE_SCRIPT,
    TAKEN,
    TOO_LONG_MESSAGE,
    VISITOR_LIMIT,
    VISITOR_LIMIT_MESSAGE,
    model_tokens,
    worst_case_cost,
)
from src.api.tool.routes import router
from src.api.tool.tools import generate_title_tags

client = TestClient(app)
QUESTIONS = "/api/v1/tools/question-generator"
HOOKS = "/api/v1/tools/hook-generator"
METRICS = "/api/v1/tools/count_metrics"
HOOK_BODY = {"topic_description": "SEO", "goal_of_content": "Rank"}


@pytest.fixture
def settings(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "FREE_TOOLS_CALLS_PER_DAY", 100)
    monkeypatch.setattr(s, "FREE_TOOLS_MODEL_CALLS_PER_DAY", 20)
    monkeypatch.setattr(s, "FREE_TOOLS_DAILY_BUDGET_USD", 5.0)
    return s


@pytest.fixture
def no_model():
    """The model tools answer without a model call."""
    with (
        patch("src.api.tool.routes.generate_questions", AsyncMock(return_value=["Why?"])),
        patch(
            "src.api.tool.routes.generate_hooks",
            AsyncMock(return_value={"topic": "SEO", "hooks": ["Look"]}),
        ),
    ):
        yield


def ask(text="AI technology is rapidly advancing.", **kw):
    return client.post(QUESTIONS, json={"text": text}, **kw)


def tool_routes():
    return [r for r in router.routes if isinstance(r, APIRoute)]


def test_every_tool_route_is_in_the_table_and_bounded():
    tools = {r.path.rsplit("/tools/", 1)[-1] for r in tool_routes() if "POST" in r.methods}
    assert tools == set(FREE_TOOLS)
    assert all(r.methods == {"POST"} for r in tool_routes())
    assert all(getattr(r.endpoint, "free_tool_bounded", False) for r in tool_routes())


def test_a_model_tool_is_built_with_the_cap_it_is_charged_for():
    for tool, spec in FREE_TOOLS.items():
        if spec.model_calls:
            assert model_tokens(tool) == spec.max_tokens > 0
        else:
            with pytest.raises(KeyError):
                model_tokens(tool)


def test_worst_case_cost_counts_a_token_a_byte_three_times_and_the_output_cap():
    # (3 x 20,000 + 1,000) input tokens at $0.15 and 8,192 output tokens at $0.60 a million.
    assert worst_case_cost(FREE_TOOLS["grammar-checker"], MAX_INPUT_BYTES) == 14066
    # Title tags: three calls of (3 x 300 + 1,000) in and 512 out.
    assert worst_case_cost(FREE_TOOLS["title-tags"], 300) == 1777


def _templates():
    for info in pkgutil.iter_modules(prompts.__path__):
        module = importlib.import_module(f"{prompts.__name__}.{info.name}")
        yield from (v for v in vars(module).values() if isinstance(v, BasePromptTemplate))


def test_no_prompt_carries_a_request_field_more_often_than_charged():
    templates = list(_templates())
    assert len(templates) >= 10
    for template in templates:
        text = template.format(**{v: f"<<{v}>>" for v in template.input_variables})
        for v in template.input_variables:
            assert text.count(f"<<{v}>>") <= PROMPT_COPIES, (template, v)


@pytest.mark.asyncio
async def test_title_tags_prompts_carry_a_field_no_more_often_than_charged():
    bad = MagicMock(content="Too short | B")
    model = MagicMock(ainvoke=AsyncMock(return_value=bad))
    with patch("src.api.tool.tools._get_model", return_value=model):
        await generate_title_tags(keyword="<<k>>", topic="<<t>>", brand="<<b>>", tone="<<o>>")
    assert model.ainvoke.await_count == FREE_TOOLS["title-tags"].model_calls
    for call in model.ainvoke.await_args_list:
        prompt = str(call.args[0])
        assert all(prompt.count(m) <= PROMPT_COPIES for m in ("<<k>>", "<<t>>", "<<b>>", "<<o>>"))


def test_a_visitor_is_refused_after_the_day_limit_of_a_tool(settings, no_model):
    settings.FREE_TOOLS_MODEL_CALLS_PER_DAY = 2
    assert ask().status_code == 200
    assert ask().status_code == 200

    refused = ask()
    assert refused.status_code == 429
    assert refused.json()["message"] == VISITOR_LIMIT_MESSAGE
    assert 0 < int(refused.headers["Retry-After"]) <= 86400
    # The limit is per tool: another tool still answers.
    assert client.post(METRICS, json={"text": "one two"}).status_code == 200


def test_each_verified_address_has_its_own_count(settings, no_model, monkeypatch):
    settings.FREE_TOOLS_MODEL_CALLS_PER_DAY = 1
    monkeypatch.setattr(limits, "_trusted_address", lambda r: r.headers.get("x-test-ip"))
    assert ask(headers={"x-test-ip": "203.0.113.1"}).status_code == 200
    assert ask(headers={"x-test-ip": "203.0.113.1"}).status_code == 429
    assert ask(headers={"x-test-ip": "203.0.113.2"}).status_code == 200
    # An address the server can't trust counts as one visitor, whoever sends it.
    assert ask().status_code == 200
    assert ask().status_code == 429


def test_an_untrusted_address_counts_as_one_visitor_and_is_not_logged(
    settings, no_model, monkeypatch, caplog
):
    settings.FREE_TOOLS_MODEL_CALLS_PER_DAY = 1
    visitor = TestClient(app, client=("203.0.113.9", 50000))
    monkeypatch.setattr(settings, "TRUSTED_PROXY_IPS", "127.0.0.1")
    assert limits._trusted_address(MagicMock(client=MagicMock(host="203.0.113.9"))) == "203.0.113.9"
    monkeypatch.setattr(settings, "TRUSTED_PROXY_IPS", "*")
    caplog.set_level("WARNING")
    assert visitor.post(QUESTIONS, json={"text": "Hi?"}).status_code == 200
    assert ask().status_code == 429  # the same single visitor
    # No warning or error names the visitor (the request tracker's own info lines are not ours).
    assert not [r for r in caplog.records if "203.0.113.9" in r.getMessage()]


def test_tools_without_a_model_have_their_own_limit(settings):
    settings.FREE_TOOLS_CALLS_PER_DAY = 1
    assert client.post(METRICS, json={"text": "one two"}).status_code == 200
    assert client.post(METRICS, json={"text": "one two"}).status_code == 429


def test_an_invalid_request_counts_nothing(settings, no_model):
    settings.FREE_TOOLS_MODEL_CALLS_PER_DAY = 1
    for _ in range(3):
        assert client.post(QUESTIONS, json={}).status_code == 422
    assert limits.COUNTS.memory == {}
    assert ask().status_code == 200


def test_the_budget_stops_every_model_tool_for_the_day(settings, no_model):
    one_call = worst_case_cost(FREE_TOOLS["question-generator"], len(b'{"text":"Hi?"}'))
    settings.FREE_TOOLS_DAILY_BUDGET_USD = (one_call + 10) / 1_000_000
    assert client.post(QUESTIONS, json={"text": "Hi?"}).status_code == 200

    refused = client.post(QUESTIONS, json={"text": "Hi?"})
    assert refused.status_code == 429
    assert refused.json()["message"] == BUDGET_MESSAGE
    other = client.post(HOOKS, json=HOOK_BODY)
    assert other.status_code == 429
    assert other.json()["message"] == BUDGET_MESSAGE
    # A refused call takes nothing, so only the first call is spent; tools without a model go on.
    day, _ = limits._today()
    assert limits.COUNTS.memory[f"freetools:{day}:spend"] == one_call
    assert client.post(METRICS, json={"text": "one two"}).status_code == 200


def test_a_refused_call_does_not_count_against_the_visitor(settings, no_model):
    settings.FREE_TOOLS_DAILY_BUDGET_USD = 0
    settings.FREE_TOOLS_MODEL_CALLS_PER_DAY = 1
    assert ask().json()["message"] == BUDGET_MESSAGE
    settings.FREE_TOOLS_DAILY_BUDGET_USD = 5.0
    assert ask().status_code == 200


def test_a_model_tool_refuses_too_much_text(settings, no_model):
    refused = ask("a" * MAX_INPUT_BYTES)
    assert refused.status_code == 413
    assert refused.json()["message"] == TOO_LONG_MESSAGE
    assert limits.COUNTS.memory == {}
    # A tool without a model takes it.
    assert client.post(METRICS, json={"text": "word " * 10_000}).status_code == 200


def test_the_counts_start_again_the_next_utc_day(settings, no_model, monkeypatch):
    settings.FREE_TOOLS_MODEL_CALLS_PER_DAY = 1
    monkeypatch.setattr(limits, "_today", lambda: ("20261006", 100))
    assert ask().status_code == 200
    assert ask().status_code == 429
    monkeypatch.setattr(limits, "_today", lambda: ("20261007", 86400))
    assert ask().status_code == 200


def test_only_the_days_first_budget_refusal_reaches_the_error_logs(settings, no_model, monkeypatch):
    recorded = []

    async def record(request, **kw):
        if not getattr(kw["exception"], "suppress_error_log", False):
            recorded.append(kw["message"])

    monkeypatch.setattr("src.api.middleware.error_handler._record_error", record)
    monkeypatch.setattr(limits, "_budget_logged", None)
    settings.FREE_TOOLS_MODEL_CALLS_PER_DAY = 1
    assert ask().status_code == 200
    assert ask().status_code == 429  # the visitor's limit: not recorded
    settings.FREE_TOOLS_DAILY_BUDGET_USD = 0
    assert client.post(HOOKS, json=HOOK_BODY).status_code == 429
    assert client.post(HOOKS, json=HOOK_BODY).status_code == 429
    assert recorded == [BUDGET_MESSAGE]


class FakeRedis:
    """Runs TAKE_SCRIPT's rule as Python; the script itself runs against a real Redis below."""

    def __init__(self, broken=False):
        self.store, self.ttls, self.broken = {}, {}, broken

    async def eval(self, script, numkeys, visitor, spend, limit, cost, budget, ttl):
        assert script == TAKE_SCRIPT and numkeys == 2
        if self.broken:
            raise ConnectionError("down")
        if self.store.get(visitor, 0) >= limit:
            return VISITOR_LIMIT
        if cost and self.store.get(spend, 0) + cost > budget:
            return BUDGET_LIMIT
        if cost:
            self.store[spend] = self.store.get(spend, 0) + cost
            self.ttls[spend] = ttl
        self.store[visitor] = self.store.get(visitor, 0) + 1
        self.ttls[visitor] = ttl
        return TAKEN


def test_the_counts_live_in_redis_until_the_day_ends(settings, no_model, monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(cache, "redis", redis)
    monkeypatch.setattr(limits, "_today", lambda: ("20261006", 3600))
    assert ask().status_code == 200
    spend, visitor = sorted(redis.store)
    assert spend == "freetools:20261006:spend"
    assert re.fullmatch(r"freetools:20261006:visitor:[0-9a-f]{16}:question-generator", visitor)
    assert set(redis.ttls.values()) == {3660}
    assert limits.COUNTS.memory == {}


def test_without_redis_each_process_counts_in_memory(settings, no_model, monkeypatch):
    settings.FREE_TOOLS_MODEL_CALLS_PER_DAY = 1
    monkeypatch.setattr(cache, "redis", FakeRedis(broken=True))
    assert ask().status_code == 200
    assert ask().status_code == 429


@pytest.mark.asyncio
async def test_the_redis_script_checks_and_counts_in_one_step():
    from redis import asyncio as aioredis

    redis = aioredis.from_url(get_settings().REDIS_URL, socket_connect_timeout=2)
    try:
        await redis.ping()
    except Exception:
        await redis.aclose()
        pytest.skip("no Redis to run the script against")
    visitor, spend = f"freetools-test:{uuid4()}:visitor", f"freetools-test:{uuid4()}:spend"
    try:

        async def take(limit, cost, budget):
            return int(await redis.eval(TAKE_SCRIPT, 2, visitor, spend, limit, cost, budget, 60))

        assert await take(2, 300, 1000) == TAKEN
        assert await take(2, 800, 1000) == BUDGET_LIMIT  # 300 + 800 is over: nothing taken
        assert await take(2, 700, 1000) == TAKEN
        assert await take(2, 0, 1000) == VISITOR_LIMIT
        assert int(await redis.get(visitor)) == 2
        assert int(await redis.get(spend)) == 1000
        assert 0 < await redis.ttl(visitor) <= 60
    finally:
        await redis.delete(visitor, spend)
        await redis.aclose()
