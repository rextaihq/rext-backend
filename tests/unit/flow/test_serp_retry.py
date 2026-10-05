"""A SERP lookup that fails for a passing reason is tried once more.

The search engine's own error (40101), DataForSEO's system errors (50000s), a
network timeout and an HTTP 5xx are retried once; a search with no results, a
credentials problem or any other failure is not.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

import src.flow.engines.serp.fetch_serp as serp_module

ORGANIC = {"type": "organic", "title": "A", "url": "https://a.test"}


def _task(status_code=20000, items=None):
    return {"tasks": [{"status_code": status_code, "result": [{"items": items}]}]}


def _http_error(status):
    request = httpx.Request("POST", "https://dataforseo.test/serp")
    return httpx.HTTPStatusError(
        str(status), request=request, response=httpx.Response(status, request=request)
    )


async def _fetch(monkeypatch, *answers):
    calls = AsyncMock(side_effect=list(answers))
    monkeypatch.setattr(serp_module, "_do_fetch_serp", calls)
    monkeypatch.setattr(serp_module, "DATAFORSEO_SERP_URL", "https://dataforseo.test/serp")
    monkeypatch.setattr(serp_module, "SERP_RETRY_DELAY_SECONDS", 0)
    state = {
        "serp_payload": {
            "query": "running shoes",
            "country": "us",
            "user_id": "u",
            "workspace_id": "w",
        }
    }
    result = await serp_module.fetch_serp_results(state, {}, runtime=SimpleNamespace(store=None))
    return result["serp_result"], calls.await_count


@pytest.mark.parametrize(
    "first",
    [
        _task(status_code=40101),
        _task(status_code=50401),
        {"status_code": 50000, "status_message": "Internal Error.", "tasks": []},
        _http_error(503),
        httpx.ReadTimeout("timed out"),
        httpx.ConnectError("refused"),
    ],
)
async def test_a_passing_failure_is_retried(monkeypatch, first):
    serp, attempts = await _fetch(monkeypatch, first, _task(items=[ORGANIC]))

    assert attempts == 2
    assert serp["serp_status"] == "ok"
    assert len(serp["organic_results"]) == 1


async def test_two_passing_failures_end_as_lookup_failed(monkeypatch):
    serp, attempts = await _fetch(monkeypatch, _task(status_code=40101), _http_error(502))

    assert attempts == 2
    assert serp["serp_status"] == "lookup_failed"
    assert serp["organic_results"] == []


@pytest.mark.parametrize(
    ("answer", "serp_status"),
    [
        (_task(items=None), "no_results"),
        (_task(status_code=40102), "no_results"),
        (_task(status_code=40100), "lookup_failed"),
        (_task(status_code=40501), "lookup_failed"),
        ({"status_code": 40100, "tasks": []}, "lookup_failed"),
        (_http_error(401), "lookup_failed"),
        (_http_error(402), "lookup_failed"),
        (ValueError("bad JSON"), "lookup_failed"),
    ],
)
async def test_other_outcomes_are_not_retried(monkeypatch, answer, serp_status):
    serp, attempts = await _fetch(monkeypatch, answer)

    assert attempts == 1
    assert serp["serp_status"] == serp_status


async def test_a_good_answer_is_not_retried(monkeypatch):
    serp, attempts = await _fetch(monkeypatch, _task(items=[ORGANIC]))

    assert attempts == 1
    assert serp["serp_status"] == "ok"
