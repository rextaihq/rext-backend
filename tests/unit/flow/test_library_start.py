"""A run started from the keyword Library uses the item's research (E17, rext-control#368).

Before, ``is_library`` skipped the SERP and the keyword analysis entirely, so
every Library-started article was written without SERP data, and any text in
``?library=`` became an article with no research at all.
"""

import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import langgraph.config as langgraph_config
import pytest
from langgraph.store.memory import InMemoryStore

import src.flow.engines.seo.keyword_recomendation as keyword_module
import src.flow.engines.serp.normalization as normalization_module
import src.services.notification_helper as notification_module
import src.utils.credit_manager as credit_module
from src.flow.engines.content.generation.topic_generation import (
    KEYWORD_TOO_LONG_MESSAGE,
    TOPICS_FAILED_CODE,
)
from src.flow.engines.rext import _after_serp, create_rext_engine
from src.flow.engines.router.library_router import library_router
from src.flow.engines.seo.library_item import (
    LIBRARY_ITEM_MESSAGE,
    LIBRARY_ITEM_MISSING,
    LIBRARY_RESEARCH_FRESH_FOR,
    charge_library_start,
    library_charge_router,
    library_item_router,
    load_library_item,
)

U1 = "11111111-1111-1111-1111-111111111111"
W1 = "33333333-3333-3333-3333-333333333333"
KEY = "library_content marketing roi_2026-10-05T12:00:00+00:00"
ITEM = {
    "original_query": "content marketing roi",
    "country": "United Kingdom",
    "recommendations": ["content marketing roi for small business"],
    "questions": ["How do you measure content marketing ROI?"],
    "related_topics": [],
    "top_organic_results": [{"title": "A", "url": "https://a.test", "position": 1}],
    "seo_state": {
        "keyword_difficulty": 38,
        "intent": ["informational", "commercial"],
        "volume": 1900,
        "volume_status": "ok",
        "backlinks": 120,
        "referring_domains": 40,
    },
}


class Store:
    def __init__(self, items):
        self.items, self.asked = items, []

    async def aget(self, namespace, key):
        self.asked.append((namespace, key))
        value = self.items.get((namespace, key))
        return SimpleNamespace(value=value) if value else None


@pytest.fixture
def billing(monkeypatch):
    charged = AsyncMock()
    notify = AsyncMock()
    monkeypatch.setattr(credit_module, "consume_stage_credits", charged)
    monkeypatch.setattr(notification_module, "notify_now", notify)
    return charged, notify


def _state(**payload):
    return {
        "serp_payload": {
            "query": "whatever the link carried",
            "is_library": True,
            "user_id": "u-payload",
            "workspace_id": W1,
            "country": "us",
            **payload,
        }
    }


def _config(user=U1):
    return {"configurable": {"langgraph_auth_user_id": user}}


async def test_a_library_start_loads_the_item_from_the_callers_library(billing):
    charged, notify = billing
    store = Store({(("library", U1, W1), KEY): ITEM})

    update = await load_library_item(
        _state(library_key=KEY), _config(U1), runtime=SimpleNamespace(store=store)
    )

    # The signed-in user's Library, not the user id the payload claims; then the
    # analysis's kept search results, which this item has none of.
    assert store.asked == [(("library", U1, W1), KEY), (("library_research", U1, W1), KEY)]
    # The stored keyword and market, not the start's.
    assert update["serp_payload"] == {"query": "content marketing roi", "country": "United Kingdom"}
    assert update["content"] == {"error": None, "error_code": None}
    # Charged only once its fresh SERP has results (charge_library_start).
    charged.assert_not_awaited()
    notify.assert_awaited_once()
    seo = update["seo_result"]
    assert seo["serp_backlinks"]["search_volume"] == 1900
    assert seo["serp_backlinks"]["volume_status"] == "ok"
    assert seo["serp_backlinks"]["keyword_difficulty"] == 38
    assert seo["serp_backlinks"]["main_intent"] == "informational"
    assert seo["intent_type"] == "commercial"
    assert seo["keyword_recommendations"]["selected_keyword"] == "content marketing roi"
    assert seo["keyword_recommendations"]["is_changed"] is False
    assert seo["keyword_recommendations"]["selected_country"] == "United Kingdom"
    assert library_item_router({"content": {}, **update}) == "serp_engine"


async def test_free_text_or_an_unknown_item_is_refused_with_a_message(billing, caplog):
    charged, notify = billing
    store = Store({(("library", U1, W1), KEY): ITEM})
    caplog.set_level(logging.INFO)

    for state in (_state(), _state(library_key="library_typed text_2026"), _state(library_key=KEY)):
        config = (
            _config("someone-else")
            if state["serp_payload"].get("library_key") == KEY
            else _config()
        )
        update = await load_library_item(state, config, runtime=SimpleNamespace(store=store))

        assert update == {
            "content": {"error": LIBRARY_ITEM_MESSAGE, "error_code": LIBRARY_ITEM_MISSING}
        }
        assert library_item_router(update) == "end"

    # Nothing charged or announced, and no key (it holds the typed text) in the logs.
    charged.assert_not_awaited()
    notify.assert_not_awaited()
    assert "typed text" not in caplog.text and KEY not in caplog.text


async def test_an_item_whose_keyword_can_fit_no_title_is_refused_before_any_charge(billing):
    charged, notify = billing
    long_query = "how to measure content marketing return on investment for small local businesses"
    store = Store({(("library", U1, W1), KEY): {**ITEM, "original_query": long_query}})

    update = await load_library_item(
        _state(library_key=KEY), _config(U1), runtime=SimpleNamespace(store=store)
    )

    assert update == {
        "content": {"error": KEYWORD_TOO_LONG_MESSAGE, "error_code": TOPICS_FAILED_CODE}
    }
    assert library_item_router(update) == "end"
    charged.assert_not_awaited()
    notify.assert_not_awaited()


async def test_an_older_item_without_a_country_takes_the_starts(billing):
    store = Store({(("library", U1, W1), KEY): {**ITEM, "country": None}})

    update = await load_library_item(
        _state(library_key=KEY), _config(U1), runtime=SimpleNamespace(store=store)
    )

    assert update["serp_payload"]["country"] == "us"


async def test_the_router_sends_a_library_start_to_load_its_item(monkeypatch, billing):
    _, notify = billing
    monkeypatch.setattr(credit_module, "_get_balance", AsyncMock(return_value=100))
    state = {
        "serp_payload": {
            "is_library": True,
            "query": "q",
            "user_id": "11111111-1111-1111-1111-111111111111",
            "workspace_id": "33333333-3333-3333-3333-333333333333",
        }
    }

    assert await library_router(state) == "load_library_item"
    # Announced only once its item has loaded.
    notify.assert_not_awaited()
    assert await library_router({"serp_payload": {"query": "q"}}) == "serp_engine"


def test_after_the_serp_a_library_start_skips_the_keyword_gate(monkeypatch):
    monkeypatch.setattr(normalization_module, "has_organic_results", lambda state: True)
    assert _after_serp({"serp_payload": {"is_library": True}}) == "charge_library_start"
    assert _after_serp({"serp_payload": {}}) == "seo_engine"

    # A search that finds nothing ends before the charges, as the keyword analysis does.
    monkeypatch.setattr(normalization_module, "has_organic_results", lambda state: False)
    assert _after_serp({"serp_payload": {"is_library": True}}) == "no_serp_data"


async def test_a_library_start_costs_what_any_article_costs_once_its_serp_has_results(billing):
    charged, _ = billing
    state = {"serp_payload": {**_state()["serp_payload"], "query": "content marketing roi"}}

    assert await charge_library_start(state) == {}

    # The SERP stage and the title step, for the start's user and workspace.
    assert [c.args[2] for c in charged.await_args_list] == ["serp_seo", "title_generation"]
    assert {c.kwargs["workspace_id"] for c in charged.await_args_list} == {W1}


@pytest.mark.parametrize("refused", ["serp_seo", "title_generation"])
async def test_a_refused_charge_ends_the_start_before_the_content_steps(monkeypatch, refused):
    charged = []

    async def consume(user_id, amount, stage, workspace_id=None):
        charged.append(stage)
        if stage == refused:
            raise credit_module.InsufficientCreditsError(stage, amount, 0)

    monkeypatch.setattr(credit_module, "consume_stage_credits", consume)
    monkeypatch.setattr(credit_module, "_emit_credit_event", lambda *a, **k: None)
    state = {"serp_payload": _state()["serp_payload"]}

    update = await charge_library_start(state)

    # Beside the code, which of the two charges it was, for the failed event's stage.
    stage = "analysis" if refused == "serp_seo" else "titles"
    assert update == {
        "content": {
            "error_code": "insufficient_credits",
            "failure": {"stage": stage, "reason": None},
        }
    }
    assert library_charge_router(update) == "insufficient_credits"
    # Nothing is charged after the refused stage.
    assert charged == ["serp_seo"] if refused == "serp_seo" else ["serp_seo", "title_generation"]
    assert (
        library_charge_router({"content": {"error": None, "error_code": None}}) == "content_engine"
    )


def test_the_charges_lead_to_the_content_steps_or_the_credits_end():
    edges = {(e.source, e.target) for e in create_rext_engine().get_graph().edges}

    assert ("serp_engine", "charge_library_start") in edges
    assert ("charge_library_start", "content_engine") in edges
    assert ("charge_library_start", "insufficient_credits") in edges
    assert ("serp_engine", "content_engine") not in edges


# E24 (rext-control#496): a start within a week of its analysis reuses the analysis's
# search results instead of reading them, and paying for them, again.

RESEARCH_NS = ("library_research", U1, W1)


def _research(age: timedelta) -> dict:
    return {
        "analysed_at": (datetime.now(timezone.utc) - age).isoformat(),
        "serp_normalized": {
            "query": "content marketing roi",
            "normalize_results": [{"title": "A", "url": "https://a.test", "position": 1}],
            "related_topics": ["content marketing metrics"],
            "questions": ["How do you measure content marketing ROI?"],
            "features": {"people_also_ask": True, "ai_overview": False},
            "intent_matched_signals": {"primary_intent": "commercial", "titles": ["A"]},
        },
        "competitors": [{"domain": "a.test", "top_positions": [1], "total_occurrences": 1}],
        "final_intent_type": "commercial",
        "related_searches": ["content roi calculator"],
    }


@pytest.fixture
def said(monkeypatch):
    events = []
    monkeypatch.setattr(langgraph_config, "get_stream_writer", lambda: events.append)
    return events


async def test_a_start_within_a_week_reuses_the_analysis_search_results(billing, said):
    charged, _ = billing
    research = _research(timedelta(days=2))
    store = Store({(("library", U1, W1), KEY): ITEM, (RESEARCH_NS, KEY): research})

    update = await load_library_item(
        _state(library_key=KEY), _config(U1), runtime=SimpleNamespace(store=store)
    )

    # What the SERP step would have left, from the analysis.
    assert update["serp_normalized"] == research["serp_normalized"]
    assert update["competitors"] == research["competitors"]
    assert update["final_intent_type"] == "commercial"
    assert update["serp_result"] == {
        "related_searches": ["content roi calculator"],
        "serp_status": "ok",
    }
    assert update["seo_result"]["intent_type"] == "commercial"
    assert (
        update["seo_result"]["keyword_recommendations"]["research_reused_at"]
        == (research["analysed_at"])
    )
    # Straight to the charges, without a SERP; the start screen is told.
    assert library_item_router({"content": {}, **update}) == "charge_library_start"
    assert said == [
        {
            "type": "library",
            "step": "library.research_reused",
            "analysed_at": research["analysed_at"],
        }
    ]
    charged.assert_not_awaited()


@pytest.mark.parametrize(
    "research",
    [
        _research(LIBRARY_RESEARCH_FRESH_FOR + timedelta(hours=1)),
        None,
        {**_research(timedelta(days=1)), "serp_normalized": {"normalize_results": []}},
        {**_research(timedelta(days=1)), "analysed_at": "not a time"},
    ],
    ids=["older than a week", "never kept", "no results kept", "unreadable time"],
)
async def test_any_other_start_reads_the_search_results_again(billing, said, research):
    items = {(("library", U1, W1), KEY): {**ITEM, "timestamp": "2026-09-20T10:00:00+00:00"}}
    if research is not None:
        items[(RESEARCH_NS, KEY)] = research
    store = Store(items)

    update = await load_library_item(
        _state(library_key=KEY), _config(U1), runtime=SimpleNamespace(store=store)
    )

    assert "serp_normalized" not in update and "competitors" not in update
    assert update["seo_result"]["keyword_recommendations"]["research_reused_at"] is None
    assert library_item_router({"content": {}, **update}) == "serp_engine"
    assert said == [
        {
            "type": "library",
            "step": "library.research_refreshed",
            "analysed_at": "2026-09-20T10:00:00+00:00",
        }
    ]


async def test_a_start_that_reuses_its_research_pays_only_for_its_titles(billing):
    charged, _ = billing
    state = {
        "serp_payload": {**_state()["serp_payload"], "query": "content marketing roi"},
        "seo_result": {
            "keyword_recommendations": {"research_reused_at": "2026-10-06T09:00:00+00:00"}
        },
    }

    assert await charge_library_start(state) == {}

    assert [c.args[2] for c in charged.await_args_list] == ["title_generation"]


async def test_the_analysis_keeps_its_search_results_beside_the_item(monkeypatch):
    monkeypatch.setattr(keyword_module, "has_organic_results", lambda state: True)
    store = InMemoryStore()
    research = _research(timedelta(0))
    state = {
        "serp_payload": {
            "query": "content marketing roi",
            "country": "us",
            "user_id": U1,
            "workspace_id": W1,
        },
        "serp_normalized": {
            **research["serp_normalized"],
            # Not read after the SERP step: not kept.
            "stats": {"organic_count": 1},
            "domain_stats": {"unique_domains": 1},
        },
        "competitors": research["competitors"],
        "final_intent_type": "commercial",
        "serp_result": {"related_searches": ["content roi calculator"], "organic_results": [{}]},
        "seo_result": {"serp_backlinks": {"main_intent": "informational", "search_volume": 320}},
    }

    update = await keyword_module.save_keyword_research(
        state, {}, runtime=SimpleNamespace(store=store)
    )

    key = update["seo_result"][keyword_module.KEYWORD_RESEARCH_KEY]
    item = await store.aget(("library", U1, W1), key)
    kept = await store.aget(RESEARCH_NS, key)
    # Beside the item, not in it: the dashboard downloads every item's value.
    assert "serp_normalized" not in item.value and "competitors" not in item.value
    assert kept.value == {**research, "analysed_at": item.value["timestamp"]}


def test_a_fresh_analysis_leads_from_the_item_straight_to_the_charges():
    edges = {(e.source, e.target) for e in create_rext_engine().get_graph().edges}

    assert ("load_library_item", "charge_library_start") in edges
    assert ("load_library_item", "serp_engine") in edges


# -- The analytics events of a Library start (revnix/rext-control#712) ------------------------


async def test_a_library_start_is_counted_with_its_items_country_and_a_refused_one_as_failed(
    billing, monkeypatch
):
    import src.services.generation_events as events

    seen = []
    monkeypatch.setattr(
        events, "_announce", lambda name, properties, state, **how: seen.append((name, properties))
    )
    store = Store({(("library", U1, W1), KEY): ITEM})

    await load_library_item(
        _state(library_key=KEY), _config(U1), runtime=SimpleNamespace(store=store)
    )
    # The item's own market (United Kingdom), not the start's ("us").
    assert seen == [("content_generation_started", {"from_library": True, "country": "GB"})]

    await load_library_item(_state(), _config(U1), runtime=SimpleNamespace(store=store))
    name, properties = seen[1]
    assert name == "content_generation_failed"
    assert (properties["stage"], properties["reason"]) == ("analysis", "refused")
    assert len(seen) == 2


async def test_a_refused_library_start_is_counted_for_what_stopped_it(billing, monkeypatch):
    """Review round 3 of the events: the same message for the person, the right cause in the
    counts. A keyword no title can hold is refused at the titles, as a typed one is; a store
    that could not be read is ours, not a refusal."""
    import src.services.generation_events as events

    seen = []
    monkeypatch.setattr(
        events, "_announce", lambda name, properties, state, **how: seen.append((name, properties))
    )

    too_long = {**ITEM, "original_query": "the " + "longest keyword anyone ever typed " * 6}
    store = Store({(("library", U1, W1), KEY): too_long})
    refused = await load_library_item(
        _state(library_key=KEY), _config(U1), runtime=SimpleNamespace(store=store)
    )

    class Unreadable:
        async def aget(self, namespace, key):
            raise RuntimeError("the store is down")

    unreadable = await load_library_item(
        _state(library_key=KEY), _config(U1), runtime=SimpleNamespace(store=Unreadable())
    )

    assert refused["content"]["error"] == KEYWORD_TOO_LONG_MESSAGE
    assert unreadable["content"]["error_code"] == LIBRARY_ITEM_MISSING
    assert [(name, p["stage"], p["reason"]) for name, p in seen] == [
        ("content_generation_failed", "titles", "refused"),
        ("content_generation_failed", "analysis", "internal"),
    ]
