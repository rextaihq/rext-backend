"""An AI provider outage answers 503 "busy", alerts once an hour, and charges nothing (G75, rext-control#611).

On 2026-10-07 staging's OpenAI account ran out of credits (429 insufficient_quota): the free tools
answered 500 and nobody was told. The provider's errors are built here as the OpenAI client raises them.
"""

import logging
from types import SimpleNamespace

import httpx
import openai
import pytest
from fastapi import HTTPException

from src.api.lib.sentry_config import before_send_filter
from src.api.tool import limits
from src.api.tool import routes as tool_routes
from src.api.tool.schema.schema import QuestionRequest, SEOBlogTitleRequest
from src.flow.model import llm_manager
from src.flow.model import provider_outage as outage_module
from src.flow.model.provider_outage import (
    BUSY_MESSAGE,
    INSUFFICIENT_QUOTA,
    KEY_REJECTED,
    RATE_LIMITED,
    RETRY_AFTER_SECONDS,
    SERVER_ERROR,
    UNREACHABLE,
    ProviderOutage,
    ProviderUnavailable,
    provider_outage,
    report_provider_outage,
)
from src.utils import credit_manager

REQUEST = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")


def _status_error(cls, status: int, body=None, message="error"):
    return cls(message, response=httpx.Response(status, request=REQUEST), body=body)


def out_of_credits():
    return _status_error(
        openai.RateLimitError,
        429,
        body={
            "message": "You exceeded your current quota",
            "type": "insufficient_quota",
            "code": "insufficient_quota",
        },
        message="Error code: 429 - You exceeded your current quota",
    )


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (out_of_credits(), INSUFFICIENT_QUOTA),
        (
            # What OpenAI sent on 2026-10-07 when the account was empty.
            _status_error(
                openai.RateLimitError,
                429,
                body={
                    "message": "You have no credits remaining. Add credits to continue using the API.",
                    "type": "insufficient_quota",
                    "param": None,
                    "code": "credit_balance_exhausted",
                },
            ),
            INSUFFICIENT_QUOTA,
        ),
        (
            _status_error(
                openai.RateLimitError, 429, body={"error": {"code": "insufficient_quota"}}
            ),
            INSUFFICIENT_QUOTA,
        ),
        (
            _status_error(openai.RateLimitError, 429, body={"code": "rate_limit_exceeded"}),
            RATE_LIMITED,
        ),
        (_status_error(openai.InternalServerError, 500), SERVER_ERROR),
        (_status_error(openai.APIStatusError, 503), SERVER_ERROR),
        (openai.APIConnectionError(request=REQUEST), UNREACHABLE),
        (openai.APITimeoutError(request=REQUEST), UNREACHABLE),
        (_status_error(openai.AuthenticationError, 401), KEY_REJECTED),
        (_status_error(openai.PermissionDeniedError, 403), KEY_REJECTED),
    ],
)
def test_each_provider_error_is_an_outage(error, kind):
    outage = provider_outage(error)

    assert outage is not None
    assert (outage.provider, outage.kind) == ("OpenAI", kind)


@pytest.mark.parametrize(
    "error",
    [
        _status_error(openai.BadRequestError, 400),
        _status_error(openai.NotFoundError, 404),
        ValueError("a parsing error"),
    ],
)
def test_other_errors_are_not_an_outage(error):
    assert provider_outage(error) is None


def test_an_outage_is_found_inside_another_error():
    try:
        try:
            raise out_of_credits()
        except openai.RateLimitError as inner:
            raise RuntimeError("the chain failed") from inner
    except RuntimeError as outer:
        assert provider_outage(outer).kind == INSUFFICIENT_QUOTA


def test_a_raised_provider_unavailable_is_its_own_outage():
    outage = ProviderOutage("OpenAI", RATE_LIMITED, "slow down")

    assert provider_outage(ProviderUnavailable(outage)) is outage


def test_the_detail_names_no_key_or_organisation():
    error = _status_error(
        openai.AuthenticationError,
        401,
        message="Incorrect API key provided: sk-proj-abc1****wxyz for organization org-Abc123",
    )

    detail = provider_outage(error).detail

    assert "sk-" not in detail and "org-" not in detail
    assert "[redacted]" in detail


@pytest.fixture
def fresh_alerts(monkeypatch):
    monkeypatch.setattr(outage_module, "_last_alert", {})
    clock = SimpleNamespace(now=1000.0)
    monkeypatch.setattr(outage_module.time, "monotonic", lambda: clock.now)
    return clock


def test_the_team_is_alerted_once_an_hour_per_kind(fresh_alerts, caplog):
    quota = ProviderOutage("OpenAI", INSUFFICIENT_QUOTA, "quota")

    with caplog.at_level(logging.WARNING, logger=outage_module.logger.name):
        assert report_provider_outage(quota) is True
        assert report_provider_outage(quota) is False
        assert report_provider_outage(ProviderOutage("OpenAI", SERVER_ERROR, "500")) is True
        fresh_alerts.now += 3600
        assert report_provider_outage(quota) is True

    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 3
    assert "OpenAI (insufficient_quota)" in errors[0].getMessage()


def test_the_model_error_hook_alerts_on_an_outage_only(monkeypatch):
    alerted = []
    monkeypatch.setattr(llm_manager, "report_provider_outage", alerted.append)

    llm_manager._alert_if_outage("OpenAI", out_of_credits())
    llm_manager._alert_if_outage("OpenAI", ValueError("not an outage"))

    assert [o.kind for o in alerted] == [INSUFFICIENT_QUOTA]


@pytest.fixture
def uncounted(monkeypatch):
    async def count_call(request):
        return None

    monkeypatch.setattr(limits, "count_call", count_call)
    return SimpleNamespace()


async def test_a_tool_answers_503_with_retry_after_when_the_account_is_empty(
    monkeypatch, uncounted
):
    async def generate(_):
        raise out_of_credits()

    monkeypatch.setattr(tool_routes, "generate_seo_blog_titles", generate)

    with pytest.raises(HTTPException) as exc_info:
        await tool_routes.seo_blog_titles_route(
            request_seo=SEOBlogTitleRequest(keyword="email marketing"), request=SimpleNamespace()
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == BUSY_MESSAGE
    assert exc_info.value.headers == {"Retry-After": str(RETRY_AFTER_SECONDS)}
    # Alerted once an hour by the model's hook: no Error Logs row or Sentry event per request.
    assert exc_info.value.suppress_error_log is True


async def test_any_other_tool_failure_is_still_a_500(monkeypatch, uncounted):
    async def generate(_):
        raise ValueError("the model's answer didn't parse")

    monkeypatch.setattr(tool_routes, "generate_seo_blog_titles", generate)

    with pytest.raises(HTTPException) as exc_info:
        await tool_routes.seo_blog_titles_route(
            request_seo=SEOBlogTitleRequest(keyword="email marketing"), request=SimpleNamespace()
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.headers is None


async def test_a_routes_own_400_goes_out_as_it_is(uncounted):
    with pytest.raises(HTTPException) as exc_info:
        await tool_routes.generate_questions_route(
            request_q=QuestionRequest.model_construct(text="   "), request=SimpleNamespace()
        )

    assert exc_info.value.status_code == 400


async def test_a_stage_the_provider_fails_charges_nothing(monkeypatch):
    charged = []

    async def balance(uid, workspace_id=None):
        return 100

    async def consume(*args, **kwargs):
        charged.append(args)

    monkeypatch.setattr(credit_manager, "_get_balance", balance)
    monkeypatch.setattr(credit_manager, "consume_stage_credits", consume)

    @credit_manager.deduct_credits("generate_outline")
    async def node(state):
        raise out_of_credits()

    with pytest.raises(openai.RateLimitError):
        await node({"user_id": "6f1c2a52-6c39-4f0e-9a51-6a3c1d0b8e11"})

    assert charged == []


def test_sentry_drops_an_error_its_code_reports_itself():
    busy = HTTPException(status_code=503, detail=BUSY_MESSAGE)
    busy.suppress_error_log = True
    other = HTTPException(status_code=503, detail="down")
    event = {"exception": {"values": [{"type": "HTTPException", "value": "503"}]}}

    assert before_send_filter(dict(event), {"exc_info": (HTTPException, busy, None)}) is None
    assert before_send_filter(dict(event), {"exc_info": (HTTPException, other, None)}) is not None
