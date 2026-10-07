"""The keyword step's volume_status and the end of a run whose keyword has no SERP.

The keyword overview says why a volume is missing instead of sending a bare 0,
and a keyword the search engine has no results for (or a failed SERP lookup)
ends the run with a message rather than going on to the content steps.
"""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

# The module refuses to import without these; the tests never call DataForSEO.
os.environ.setdefault("DATAFORSEO_BACKLINKS_URL", "https://dataforseo.test/keyword_overview")
os.environ.setdefault("DATAFORSEO_AUTH_HEADER", "test")

import src.flow.engines.rext as rext_module
import src.flow.engines.seo.fetch_dataforseo_backlinks as overview_module
import src.flow.engines.seo.keyword_recomendation as recommendation_module
import src.flow.engines.serp.competitor as competitor_module
import src.flow.engines.serp.fetch_serp as serp_module
import src.services.monitoring_service as monitoring_module
import src.services.notification_helper as notification_module
import src.utils.credit_manager as credit_module
from src.flow.engines.router.keyword_router import keyword_router

USER_ID = "00000000-0000-0000-0000-000000000001"
WORKSPACE_ID = "00000000-0000-0000-0000-000000000002"
_RealAsyncClient = httpx.AsyncClient


def _overview_response(monkeypatch, body=None, status=200):
    """Make the keyword overview call answer with this body (or raise for an HTTP error)."""

    def handler(_request):
        return httpx.Response(status, json=body or {})

    monkeypatch.setattr(
        overview_module.httpx,
        "AsyncClient",
        lambda **_kw: _RealAsyncClient(transport=httpx.MockTransport(handler)),
    )


def _overview_task(status_code=20000, items=None, result=True):
    task = {"status_code": status_code, "status_message": "test"}
    if result:
        task["result"] = [{"items": items}]
    return {"tasks": [task]}


def _overview_item(search_volume):
    return {
        "keyword": "running shoes",
        "keyword_info": {"search_volume": search_volume},
        "keyword_properties": {"keyword_difficulty": 40},
        "search_intent_info": {"main_intent": "commercial"},
        "avg_backlinks_info": {"backlinks": 12, "referring_domains": 5},
        "serp_info": {"serp_item_types": []},
    }


# --- the keyword overview lookup ---------------------------------------------


@pytest.mark.parametrize(
    ("search_volume", "volume_status"),
    [(1300, "ok"), (0, "ok"), (None, "no_data")],
)
async def test_lookup_reports_the_volume_and_why(monkeypatch, search_volume, volume_status):
    _overview_response(monkeypatch, _overview_task(items=[_overview_item(search_volume)]))

    data = await overview_module.get_dataforseo_data("running shoes")

    assert data["search_volume"] == search_volume
    assert data["volume_status"] == volume_status
    assert data["keyword_difficulty"] == 40


@pytest.mark.parametrize(
    ("body", "volume_status"),
    [
        (_overview_task(items=None), "no_data"),
        (_overview_task(result=False), "no_data"),
        (_overview_task(status_code=40102, result=False), "no_data"),
        (_overview_task(status_code=40100, result=False), "lookup_failed"),
        (_overview_task(status_code=50401, result=False), "lookup_failed"),
    ],
)
async def test_lookup_without_an_item_returns_only_the_status(monkeypatch, body, volume_status):
    _overview_response(monkeypatch, body)

    assert await overview_module.get_dataforseo_data("xqzvbnmplk") == {
        "volume_status": volume_status
    }


async def test_lookup_http_error_is_lookup_failed(monkeypatch):
    _overview_response(monkeypatch, status=401)

    assert await overview_module.get_dataforseo_data("running shoes") == {
        "volume_status": "lookup_failed"
    }


# --- the keyword overview node -----------------------------------------------


def _overview_state(**payload):
    return {
        "serp_payload": {
            "query": "running shoes",
            "country": "us",
            "user_id": USER_ID,
            "workspace_id": WORKSPACE_ID,
            **payload,
        }
    }


async def test_node_marks_the_defaults_with_the_lookup_status(monkeypatch):
    monkeypatch.setattr(credit_module, "consume_stage_credits", AsyncMock())
    monkeypatch.setattr(
        overview_module,
        "get_dataforseo_data",
        AsyncMock(return_value={"volume_status": "no_data"}),
    )

    result = await overview_module.fetch_dataforseo_backlinks(_overview_state())

    backlinks = result["seo_result"]["serp_backlinks"]
    assert backlinks["volume_status"] == "no_data"
    assert backlinks["search_volume"] is None


async def test_node_passes_a_found_volume_through(monkeypatch):
    monkeypatch.setattr(credit_module, "consume_stage_credits", AsyncMock())
    found = {
        "keyword": "running shoes",
        "search_volume": 0,
        "volume_status": "ok",
        "keyword_difficulty": 40,
        "main_intent": "commercial",
        "backlinks": 12,
        "referring_domains": 5,
    }
    monkeypatch.setattr(overview_module, "get_dataforseo_data", AsyncMock(return_value=found))

    result = await overview_module.fetch_dataforseo_backlinks(_overview_state())

    assert result["seo_result"]["serp_backlinks"] == found


async def test_node_without_credits_says_so(monkeypatch):
    error = credit_module.InsufficientCreditsError("serp_seo", required=1, available=0)
    monkeypatch.setattr(credit_module, "consume_stage_credits", AsyncMock(side_effect=error))
    monkeypatch.setattr(credit_module, "_emit_credit_event", lambda *_a, **_kw: None)
    lookup = AsyncMock()
    monkeypatch.setattr(overview_module, "get_dataforseo_data", lookup)

    result = await overview_module.fetch_dataforseo_backlinks(_overview_state())

    lookup.assert_not_called()
    backlinks = result["seo_result"]["serp_backlinks"]
    assert backlinks["volume_status"] == "insufficient_credits"
    assert backlinks["search_volume"] is None


async def test_node_without_the_run_ids_is_lookup_failed():
    result = await overview_module.fetch_dataforseo_backlinks(_overview_state(user_id=None))

    assert result["seo_result"]["serp_backlinks"]["volume_status"] == "lookup_failed"


# --- the SERP status ---------------------------------------------------------


def _serp_task(status_code=20000, items=None):
    return {"tasks": [{"status_code": status_code, "result": [{"items": items}]}]}


@pytest.mark.parametrize(
    ("raw", "serp_status"),
    [
        (_serp_task(items=[{"type": "organic", "title": "A", "url": "https://a.test"}]), "ok"),
        (_serp_task(items=None), "no_results"),
        (_serp_task(items=[{"type": "related_searches", "items": ["x"]}]), "no_results"),
        (_serp_task(status_code=40102, items=None), "no_results"),
        (_serp_task(status_code=40100, items=None), "lookup_failed"),
        ({"tasks": []}, "lookup_failed"),
    ],
)
def test_serp_records_whether_it_found_results(raw, serp_status):
    assert serp_module._parse_serp_response(raw)["serp_status"] == serp_status


def test_failed_serp_fetch_is_lookup_failed():
    assert serp_module._empty_serp_state()["serp_status"] == "lookup_failed"


# --- the keyword gate --------------------------------------------------------


def _gate_state(serp_backlinks, organic=True, serp_status="ok"):
    return {
        "serp_payload": {
            "query": "running shoes",
            "country": "us",
            "user_id": USER_ID,
            "workspace_id": WORKSPACE_ID,
        },
        "serp_result": {"serp_status": serp_status},
        "serp_normalized": {
            "normalize_results": [{"title": "A", "url": "https://a.test"}] if organic else [],
            "related_topics": ["trail running shoes"],
            "questions": [],
        },
        "seo_result": {"serp_backlinks": serp_backlinks},
    }


def _runtime():
    return SimpleNamespace(store=SimpleNamespace(aput=AsyncMock()))


async def _payload_at_the_gate(monkeypatch, state):
    payloads = []

    def _interrupt(payload):
        payloads.append(payload)
        return "running shoes"

    monkeypatch.setattr(recommendation_module, "interrupt", _interrupt)
    monkeypatch.setattr(credit_module, "consume_stage_credits", AsyncMock())
    runtime = _runtime()
    # The Library save, then the gate (two nodes, rext-control#330).
    saved = await recommendation_module.save_keyword_research(state, {}, runtime=runtime)
    state = {**state, "seo_result": {**state["seo_result"], **saved["seo_result"]}}
    await recommendation_module.keyword_recommendation(state)
    stored = runtime.store.aput.await_args.kwargs["value"]
    return payloads[0]["seo_state"], stored["seo_state"]


@pytest.mark.parametrize(
    ("serp_backlinks", "volume", "volume_status"),
    [
        ({"search_volume": 1300, "volume_status": "ok"}, 1300, "ok"),
        ({"search_volume": 0, "volume_status": "ok"}, 0, "ok"),
        ({"search_volume": None, "volume_status": "no_data"}, None, "no_data"),
        ({"search_volume": None, "volume_status": "lookup_failed"}, None, "lookup_failed"),
        (
            {"search_volume": None, "volume_status": "insufficient_credits"},
            None,
            "insufficient_credits",
        ),
        # a run started before the status existed
        ({"search_volume": 0}, 0, "ok"),
    ],
)
async def test_gate_payload_carries_the_volume_status(
    monkeypatch, serp_backlinks, volume, volume_status
):
    at_gate, in_library = await _payload_at_the_gate(monkeypatch, _gate_state(serp_backlinks))

    assert at_gate["volume"] == volume
    assert at_gate["volume_status"] == volume_status
    assert in_library["volume"] == volume
    assert in_library["volume_status"] == volume_status


@pytest.mark.parametrize(
    ("serp_status", "expected"),
    [("no_results", "no_results"), ("lookup_failed", "lookup_failed"), (None, "lookup_failed")],
)
async def test_no_serp_results_skips_the_gate_and_records_why(monkeypatch, serp_status, expected):
    monkeypatch.setattr(
        recommendation_module, "interrupt", lambda _p: pytest.fail("the gate must not open")
    )
    runtime = _runtime()
    state = _gate_state({"volume_status": "no_data"}, organic=False, serp_status=serp_status)

    result = await recommendation_module.save_keyword_research(state, {}, runtime=runtime)

    recs = result["seo_result"]["keyword_recommendations"]
    assert recs["error"]
    assert recs["serp_status"] == expected
    runtime.store.aput.assert_not_called()
    assert recommendation_module.keyword_research_router(result) == "end"
    assert keyword_router(result) == "NO_SERP"


def test_router_still_continues_or_reanalyses():
    def routed(**recs):
        return keyword_router({"seo_result": {"keyword_recommendations": recs}})

    assert routed(is_changed=False, error=None) == "END"
    assert routed(is_changed=True, error=None) == "SERP_ENGINE"


# --- the end of the run ------------------------------------------------------


@pytest.mark.parametrize("serp_status", ["no_results", "lookup_failed", None])
async def test_end_step_sets_the_error_and_streams_it(monkeypatch, serp_status):
    events = []
    monkeypatch.setattr("langgraph.config.get_stream_writer", lambda: events.append)
    log = AsyncMock()
    monkeypatch.setattr(monitoring_module.MonitoringService, "persist_error_log", log)
    state = {
        "serp_result": {"serp_status": serp_status},
        "serp_payload": {"workspace_id": WORKSPACE_ID},
    }

    result = await rext_module._no_serp_data(state)

    shown = "no_results" if serp_status == "no_results" else "lookup_failed"
    message = rext_module.NO_SERP_MESSAGES[shown]
    assert result == {"content": {"error": message, "error_code": "no_serp_data"}}
    assert events == [
        {
            "type": "run",
            "step": "run.failed",
            "error_code": "no_serp_data",
            "serp_status": shown,
            "message": message,
        }
    ]
    # only a failed lookup is an operator's concern
    assert log.await_count == (0 if shown == "no_results" else 1)


# --- the whole graph ---------------------------------------------------------


async def _run_graph(monkeypatch, *, serp):
    monkeypatch.setattr(credit_module, "_get_balance", AsyncMock(return_value=1000))
    monkeypatch.setattr(notification_module, "notify_now", AsyncMock())
    monkeypatch.setattr(serp_module, "DATAFORSEO_SERP_URL", "https://dataforseo.test/serp")
    monkeypatch.setattr(serp_module, "SERP_RETRY_DELAY_SECONDS", 0)
    monkeypatch.setattr(serp_module, "_do_fetch_serp", serp)
    # None of these may run for a search with no results: no model call, no
    # charge (founder, 2026-10-05) and no keyword overview call.
    unused = {}
    for module, name in (
        (competitor_module, "_classify_competitor_intents"),
        (credit_module, "consume_stage_credits"),
        (overview_module, "get_dataforseo_data"),
    ):
        unused[name] = AsyncMock()
        monkeypatch.setattr(module, name, unused[name])
    log = AsyncMock()
    monkeypatch.setattr(monitoring_module.MonitoringService, "persist_error_log", log)

    graph = rext_module.create_rext_engine()
    custom, last = [], None
    payload = {
        "query": "xqzvbnmplk",
        "country": "us",
        "user_id": USER_ID,
        "workspace_id": WORKSPACE_ID,
    }
    async for mode, chunk in graph.astream(
        {"serp_payload": payload}, stream_mode=["custom", "values"]
    ):
        if mode == "custom":
            custom.append(chunk)
        else:
            last = chunk
    for name, mock in unused.items():
        assert not mock.called, f"{name} ran for a search with no results"
    return custom, last, log


async def test_a_nonsense_keyword_ends_the_run_with_a_message(monkeypatch):
    serp = AsyncMock(return_value=_serp_task(items=None))

    custom, final, log = await _run_graph(monkeypatch, serp=serp)

    message = rext_module.NO_SERP_MESSAGES["no_results"]
    assert final["content"] == {"error": message, "error_code": "no_serp_data"}
    assert "__interrupt__" not in final
    assert [e for e in custom if e.get("type") == "run"] == [
        {
            "type": "run",
            "step": "run.failed",
            "error_code": "no_serp_data",
            "serp_status": "no_results",
            "message": message,
        }
    ]
    log.assert_not_called()


async def test_a_failed_serp_lookup_ends_the_run_and_is_logged(monkeypatch):
    request = httpx.Request("POST", "https://dataforseo.test/serp")
    error = httpx.HTTPStatusError(
        "401", request=request, response=httpx.Response(401, request=request)
    )

    custom, final, log = await _run_graph(monkeypatch, serp=AsyncMock(side_effect=error))

    message = rext_module.NO_SERP_MESSAGES["lookup_failed"]
    assert final["content"] == {"error": message, "error_code": "no_serp_data"}
    assert [e["serp_status"] for e in custom if e.get("type") == "run"] == ["lookup_failed"]
    log.assert_awaited_once()
