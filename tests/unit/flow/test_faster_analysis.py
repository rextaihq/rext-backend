"""The analysis step, faster (rext-control#697): the day's SERP and intent cache, the Library
save without an embedding, and one timing line per stage."""

import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import src.flow.engines.seo.keyword_recomendation as keyword_module
import src.flow.engines.serp.competitor as competitor
import src.flow.engines.serp.fetch_serp as serp_module
from src.flow.engines.serp import serp_cache
from src.flow.model.structure.intent import SEOIntentResult
from src.utils.stage_timing import timed_stage

ORGANIC = {"type": "organic", "title": "A", "url": "https://a.test"}


def _task(status_code=20000, items=None):
    return {"tasks": [{"status_code": status_code, "result": [{"items": items}]}]}


@pytest.fixture
def day_cache(monkeypatch):
    """The cache as Redis keeps it: what's written comes back as JSON."""
    kept = {}

    async def read(key):
        return kept.get(key)

    async def write(key, value):
        kept[key] = json.loads(json.dumps(value, default=str))

    monkeypatch.setattr(serp_cache, "read", read)
    monkeypatch.setattr(serp_cache, "write", write)
    return kept


async def _fetch(monkeypatch, calls, query="running shoes", country="us"):
    monkeypatch.setattr(serp_module, "_do_fetch_serp", calls)
    monkeypatch.setattr(serp_module, "DATAFORSEO_SERP_URL", "https://dataforseo.test/serp")
    state = {
        "serp_payload": {"query": query, "country": country, "user_id": "u", "workspace_id": "w"}
    }
    result = await serp_module.fetch_serp_results(state, {}, runtime=SimpleNamespace(store=None))
    return result["serp_result"]


# --- the SERP ---------------------------------------------------------------------------


async def test_a_keyword_analysed_today_reuses_its_serp(monkeypatch, day_cache):
    calls = AsyncMock(return_value=_task(items=[ORGANIC]))

    first = await _fetch(monkeypatch, calls, query="Running Shoes")
    again = await _fetch(monkeypatch, calls, query="  running   shoes ")

    assert calls.await_count == 1  # the second analysis made no SERP call
    assert first["serp_status"] == "ok" and again == json.loads(json.dumps(first, default=str))


async def test_another_country_is_another_serp(monkeypatch, day_cache):
    calls = AsyncMock(return_value=_task(items=[ORGANIC]))

    await _fetch(monkeypatch, calls, country="us")
    await _fetch(monkeypatch, calls, country="gb")

    assert calls.await_count == 2


async def test_a_lookup_that_found_nothing_is_never_kept(monkeypatch, day_cache):
    calls = AsyncMock(side_effect=[_task(items=[]), _task(items=[ORGANIC])])

    assert (await _fetch(monkeypatch, calls))["serp_status"] == "no_results"
    assert (await _fetch(monkeypatch, calls))["serp_status"] == "ok"  # asked again, live
    assert calls.await_count == 2


async def test_a_failed_task_with_some_rows_is_never_kept(monkeypatch, day_cache):
    # A task DataForSEO reports as failed can still carry rows: it reads as "ok", but what
    # depends on completion (the AI Overview) is unknown, so it isn't served to others.
    calls = AsyncMock(return_value=_task(status_code=40501, items=[ORGANIC]))

    first = await _fetch(monkeypatch, calls)
    await _fetch(monkeypatch, calls)

    assert first["serp_status"] == "ok" and calls.await_count == 2 and day_cache == {}


async def test_a_cache_hit_logs_no_keyword(monkeypatch, day_cache, caplog):
    caplog.set_level(logging.INFO)
    calls = AsyncMock(return_value=_task(items=[ORGANIC]))

    await _fetch(monkeypatch, calls, query="acme confidential launch")
    caplog.clear()
    await _fetch(monkeypatch, calls, query="acme confidential launch")

    assert calls.await_count == 1
    assert not any("confidential" in r.getMessage() for r in caplog.records)


# --- the intent call --------------------------------------------------------------------

GROUPS = {"a.test": {"top_result": {"title": "A", "snippet": "about a"}, "top_positions": [1]}}


async def test_the_same_rows_reuse_the_intent_answer(monkeypatch, day_cache):
    answer = (
        "COMMERCIAL",
        {"a.test": SEOIntentResult(domain="a.test", intent="COMMERCIAL", is_brand=True)},
        ["running shoes for women"],
    )
    classify = AsyncMock(return_value=answer)
    monkeypatch.setattr(competitor, "_classify_competitor_intents", classify)

    await competitor._classify_cached("running shoes", GROUPS)
    intent, results, suggested = await competitor._classify_cached("Running Shoes", GROUPS)

    assert classify.await_count == 1
    assert intent == "COMMERCIAL" and suggested == ["running shoes for women"]
    assert results["a.test"].intent == "COMMERCIAL" and results["a.test"].is_brand is True


async def test_other_rows_ask_again(monkeypatch, day_cache):
    classify = AsyncMock(return_value=("INFORMATIONAL", {}, []))
    monkeypatch.setattr(competitor, "_classify_competitor_intents", classify)

    await competitor._classify_cached("running shoes", GROUPS)
    await competitor._classify_cached("running shoes", {**GROUPS, "b.test": GROUPS["a.test"]})

    assert classify.await_count == 2


async def test_an_unknown_intent_is_never_kept(monkeypatch, day_cache):
    classify = AsyncMock(return_value=("UNKNOWN", {}, []))
    monkeypatch.setattr(competitor, "_classify_competitor_intents", classify)

    await competitor._classify_cached("running shoes", GROUPS)
    await competitor._classify_cached("running shoes", GROUPS)

    assert classify.await_count == 2 and day_cache == {}


# --- a cache that fails ------------------------------------------------------------------


async def test_a_redis_that_fails_is_a_miss_and_never_stops_the_run(monkeypatch):
    from src.api.cache.redis_client import cache

    monkeypatch.setattr(cache, "_enabled", True)
    monkeypatch.setattr(cache, "get", AsyncMock(side_effect=ConnectionError("down")))
    monkeypatch.setattr(cache, "set", AsyncMock(side_effect=ConnectionError("down")))

    assert await serp_cache.read("serp:v1:x") is None
    await serp_cache.write("serp:v1:x", {"serp_status": "ok"})  # no exception


async def test_with_redis_off_nothing_is_read_or_written(monkeypatch):
    from src.api.cache.redis_client import cache

    monkeypatch.setattr(cache, "_enabled", False)
    get = AsyncMock()
    monkeypatch.setattr(cache, "get", get)

    assert await serp_cache.read("serp:v1:x") is None
    get.assert_not_awaited()


# --- the Library save -------------------------------------------------------------------


async def test_the_library_save_makes_no_embedding(monkeypatch):
    # The Library is listed and read by key; the store's index embedded the whole value
    # with an OpenAI call on every analysis.
    saved = []

    class _Store:
        async def aput(self, namespace, key, value, **kwargs):
            saved.append(kwargs)

    monkeypatch.setattr(keyword_module, "has_organic_results", lambda state: True)
    state = {
        "serp_payload": {
            "query": "running shoes",
            "country": "us",
            "user_id": "u1",
            "workspace_id": "w1",
        },
        "serp_normalized": {
            "query": "running shoes",
            "related_topics": ["trail running shoes"],
            "normalize_results": [{"title": "A", "url": "https://a.test", "position": 1}],
        },
        "seo_result": {"serp_backlinks": {"main_intent": "commercial", "search_volume": 320}},
    }

    await keyword_module.save_keyword_research(state, {}, runtime=SimpleNamespace(store=_Store()))

    # Two writes: the item, and the search results kept beside it for a later start (E24).
    assert saved == [{"index": False}, {"index": False}]


# --- the timing lines -------------------------------------------------------------------


def test_each_stage_logs_its_time_with_no_keyword(caplog):
    caplog.set_level(logging.INFO, logger="rext.stage_timing")

    with timed_stage("serp") as timing:
        timing["cache"] = "miss"
    with pytest.raises(RuntimeError), timed_stage("outline_model", regenerating=False):
        raise RuntimeError("model down")

    lines = [r.getMessage() for r in caplog.records if r.name == "rext.stage_timing"]
    assert lines[0].startswith("stage_timing stage=serp ms=")
    assert lines[0].endswith(" outcome=ok cache=miss")
    assert lines[1].endswith(" outcome=error regenerating=False")
