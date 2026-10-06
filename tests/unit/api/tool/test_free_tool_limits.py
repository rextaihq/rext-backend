from unittest.mock import AsyncMock, patch

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from src.api.cache.redis_client import cache
from src.api.config import get_settings
from src.api.server import app
from src.api.tool import limits
from src.api.tool.limits import (
    BUDGET_MESSAGE,
    FREE_TOOLS,
    MAX_INPUT_BYTES,
    TOO_LONG_MESSAGE,
    VISITOR_LIMIT_MESSAGE,
    model_tokens,
    worst_case_cost,
)
from src.api.tool.routes import router

client = TestClient(app)
QUESTIONS = "/api/v1/tools/question-generator"
HOOKS = "/api/v1/tools/hook-generator"
METRICS = "/api/v1/tools/count_metrics"


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


def ask(text="AI technology is rapidly advancing."):
    return client.post(QUESTIONS, json={"text": text})


def test_every_tool_route_is_in_the_table():
    tools = {
        route.path.rsplit("/tools/", 1)[-1]
        for route in router.routes
        if isinstance(route, APIRoute) and "POST" in route.methods
    }
    assert tools == set(FREE_TOOLS)
    assert not [r for r in router.routes if isinstance(r, APIRoute) and "GET" in r.methods]


def test_a_model_tool_is_built_with_the_cap_it_is_charged_for():
    for tool, spec in FREE_TOOLS.items():
        if spec.model_calls:
            assert model_tokens(tool) == spec.max_tokens > 0
        else:
            with pytest.raises(KeyError):
                model_tokens(tool)


def test_worst_case_cost_counts_the_whole_input_and_output_cap():
    # (20,000 / 3 + 1,000) input tokens at $0.15 and 8,192 output tokens at $0.60 a million.
    assert worst_case_cost(FREE_TOOLS["grammar-checker"], MAX_INPUT_BYTES) == 6066
    # Title tags: three calls of (300 / 3 + 1,000) in and 512 out.
    assert worst_case_cost(FREE_TOOLS["title-tags"], 300) == 1417


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


def test_tools_without_a_model_have_their_own_limit(settings):
    settings.FREE_TOOLS_CALLS_PER_DAY = 1
    assert client.post(METRICS, json={"text": "one two"}).status_code == 200
    assert client.post(METRICS, json={"text": "one two"}).status_code == 429


def test_the_budget_stops_every_model_tool_for_the_day(settings, no_model):
    one_call = worst_case_cost(FREE_TOOLS["question-generator"], len(b'{"text":"Hi?"}'))
    settings.FREE_TOOLS_DAILY_BUDGET_USD = (one_call + 10) / 1_000_000
    assert client.post(QUESTIONS, json={"text": "Hi?"}).status_code == 200

    refused = client.post(QUESTIONS, json={"text": "Hi?"})
    assert refused.status_code == 429
    assert refused.json()["message"] == BUDGET_MESSAGE
    other = client.post(HOOKS, json={"topic_description": "SEO", "goal_of_content": "Rank"})
    assert other.status_code == 429
    assert other.json()["message"] == BUDGET_MESSAGE
    # A refused call is given back, so only the first call is spent; tools without a model go on.
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
    # A tool without a model takes it.
    assert client.post(METRICS, json={"text": "word " * 10_000}).status_code == 200


def test_the_counts_start_again_the_next_utc_day(settings, no_model, monkeypatch):
    settings.FREE_TOOLS_MODEL_CALLS_PER_DAY = 1
    monkeypatch.setattr(limits, "_today", lambda: ("20261006", 100))
    assert ask().status_code == 200
    assert ask().status_code == 429
    monkeypatch.setattr(limits, "_today", lambda: ("20261007", 86400))
    assert ask().status_code == 200


class FakePipeline:
    def __init__(self, redis):
        self.redis, self.key, self.amount = redis, None, 0

    def incrby(self, key, amount):
        self.key, self.amount = key, amount

    def expire(self, key, ttl):
        self.redis.ttls[key] = ttl

    async def execute(self):
        if self.redis.broken:
            raise ConnectionError("down")
        self.redis.store[self.key] = self.redis.store.get(self.key, 0) + self.amount
        return [self.redis.store[self.key], True]


class FakeRedis:
    def __init__(self, broken=False):
        self.store, self.ttls, self.broken = {}, {}, broken

    def pipeline(self):
        return FakePipeline(self)


def test_the_counts_live_in_redis_until_the_day_ends(settings, no_model, monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(cache, "redis", redis)
    monkeypatch.setattr(limits, "_today", lambda: ("20261006", 3600))
    assert ask().status_code == 200
    keys = sorted(redis.store)
    assert keys == ["freetools:20261006:spend", keys[1]]
    assert keys[1].startswith("freetools:20261006:visitor:") and keys[1].endswith(
        ":question-generator"
    )
    # The address is stored hashed, never as it is.
    assert "testclient" not in keys[1]
    assert set(redis.ttls.values()) == {3660}
    assert limits.COUNTS.memory == {}


def test_without_redis_each_process_counts_in_memory(settings, no_model, monkeypatch):
    settings.FREE_TOOLS_MODEL_CALLS_PER_DAY = 1
    monkeypatch.setattr(cache, "redis", FakeRedis(broken=True))
    assert ask().status_code == 200
    assert ask().status_code == 429


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
    assert (
        client.post(HOOKS, json={"topic_description": "SEO", "goal_of_content": "Rank"}).status_code
        == 429
    )
    assert (
        client.post(HOOKS, json={"topic_description": "SEO", "goal_of_content": "Rank"}).status_code
        == 429
    )
    assert recorded == [BUDGET_MESSAGE]
