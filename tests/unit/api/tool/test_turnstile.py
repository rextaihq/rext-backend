"""The free AI tools' bot check (G87): a model tool verifies the site form's Cloudflare Turnstile
token before the call is counted or run. Cloudflare is a fake here: nothing reaches the network."""

import json
import logging
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient

from src.api.config import get_settings
from src.api.server import app
from src.api.tool import limits, turnstile
from src.api.tool.turnstile import REFUSED_MESSAGE, SITEVERIFY_URL

client = TestClient(app)
QUESTIONS = "/api/v1/tools/question-generator"
METRICS = "/api/v1/tools/count_metrics"
SECRET = "test-turnstile-secret"


@pytest.fixture(autouse=True)
def fresh_logs(monkeypatch):
    monkeypatch.setattr(turnstile, "_logged_at", {})


@pytest.fixture
def settings(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "TURNSTILE_SECRET_KEY", SECRET)
    monkeypatch.setattr(s, "FREE_TOOLS_MODEL_CALLS_PER_DAY", 20)
    monkeypatch.setattr(s, "FREE_TOOLS_DAILY_BUDGET_USD", 5.0)
    return s


@pytest.fixture
def model():
    """The question generator answers without a model call; the mock says whether it ran."""
    with patch("src.api.tool.routes.generate_questions", AsyncMock(return_value=["Why?"])) as mock:
        yield mock


@pytest.fixture
def cloudflare(monkeypatch):
    """A fake siteverify: `answer` is what it does with each request, and `seen` holds the forms."""
    seen = []
    fake = {"answer": lambda request: httpx.Response(200, json={"success": True})}

    def handle(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == SITEVERIFY_URL
        seen.append({k: v[0] for k, v in parse_qs(request.content.decode()).items()})
        return fake["answer"](request)

    monkeypatch.setattr(
        turnstile, "_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(handle))
    )
    fake["seen"] = seen
    return fake


def ask(token=None, **kw):
    body = {"text": "AI technology is rapidly advancing."}
    if token is not None:
        body["turnstile_token"] = token
    return client.post(QUESTIONS, json=body, **kw)


def test_a_good_token_lets_the_tool_run(settings, model, cloudflare):
    response = ask("good-token")

    assert response.status_code == 200
    assert model.await_count == 1
    assert cloudflare["seen"] == [{"secret": SECRET, "response": "good-token"}]


def test_cloudflare_is_given_the_visitors_trusted_address(settings, model, cloudflare, monkeypatch):
    monkeypatch.setattr(limits, "_trusted_address", lambda r: "203.0.113.7")

    assert ask("good-token").status_code == 200
    assert cloudflare["seen"][0]["remoteip"] == "203.0.113.7"


def test_a_refused_token_gets_403_runs_nothing_and_counts_nothing(settings, model, cloudflare):
    cloudflare["answer"] = lambda request: httpx.Response(
        200, json={"success": False, "error-codes": ["invalid-input-response"]}
    )

    for token in ("forged", "used-once"):
        response = ask(token)
        assert response.status_code == 403
        assert response.json()["message"] == REFUSED_MESSAGE
    assert model.await_count == 0
    assert limits.COUNTS.memory == {}


@pytest.mark.parametrize("token", [None, "", "x" * 2049])
def test_no_token_or_an_impossible_one_is_refused_without_asking(
    settings, model, cloudflare, token
):
    response = client.post(
        QUESTIONS, json={"text": "Hi?", **({} if token is None else {"turnstile_token": token})}
    )

    assert response.status_code == 403
    assert cloudflare["seen"] == []
    assert model.await_count == 0


def test_without_a_secret_there_is_no_check(settings, model, cloudflare, monkeypatch):
    monkeypatch.setattr(settings, "TURNSTILE_SECRET_KEY", None)

    assert ask().status_code == 200
    assert cloudflare["seen"] == []


def test_a_tool_without_a_model_needs_no_token(settings, cloudflare):
    assert client.post(METRICS, json={"text": "one two"}).status_code == 200
    assert cloudflare["seen"] == []


def _times_out(request):
    raise httpx.ReadTimeout("slow", request=request)


def _unreachable(request):
    raise httpx.ConnectError("down", request=request)


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param(_times_out, id="timeout"),
        pytest.param(_unreachable, id="unreachable"),
        pytest.param(lambda request: httpx.Response(503, text="busy"), id="5xx"),
        pytest.param(lambda request: httpx.Response(200, text="<html>"), id="not JSON"),
    ],
)
def test_when_cloudflare_doesnt_answer_the_call_goes_ahead_and_is_logged_once(
    settings, model, cloudflare, answer, caplog
):
    cloudflare["answer"] = answer
    caplog.set_level(logging.WARNING)

    assert ask("any-token").status_code == 200
    assert ask("any-token").status_code == 200

    assert model.await_count == 2
    said = [r for r in caplog.records if "didn't answer" in r.getMessage()]
    assert len(said) == 1  # once, not once per call
    assert "any-token" not in caplog.text


def test_a_refused_server_secret_lets_calls_through_and_says_so(
    settings, model, cloudflare, caplog
):
    cloudflare["answer"] = lambda request: httpx.Response(
        200, json={"success": False, "error-codes": ["invalid-input-secret"]}
    )
    caplog.set_level(logging.ERROR)

    assert ask("good-token").status_code == 200

    assert model.await_count == 1
    assert "TURNSTILE_SECRET_KEY" in caplog.text
    assert SECRET not in caplog.text


def test_a_refused_token_stays_out_of_the_error_logs(settings, model, cloudflare, monkeypatch):
    recorded = []

    async def record(request, **kw):
        if not getattr(kw["exception"], "suppress_error_log", False):
            recorded.append(kw["message"])

    monkeypatch.setattr("src.api.middleware.error_handler._record_error", record)

    assert ask().status_code == 403
    assert recorded == []


def test_the_token_counts_toward_neither_the_size_limit_nor_the_cost(settings, model, cloudflare):
    """A body at the input limit still fits with its token, and the day's budget is charged for
    the text alone: the token never reaches a prompt."""
    spec = limits.FREE_TOOLS["question-generator"]
    text = "a" * (limits.MAX_INPUT_BYTES - len(b'{"text":""}'))
    without = json.dumps({"text": text}, separators=(",", ":")).encode()
    assert len(without) == limits.MAX_INPUT_BYTES
    settings.FREE_TOOLS_DAILY_BUDGET_USD = limits.worst_case_cost(spec, len(without)) / 1_000_000
    body = {"text": text, "turnstile_token": "t" * turnstile.MAX_TOKEN_LENGTH}

    response = client.post(
        QUESTIONS,
        content=json.dumps(body, separators=(",", ":")).encode(),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 200
    assert model.await_count == 1
