"""A run started from the keyword Library uses the item's research (E17, rext-control#368).

Before, ``is_library`` skipped the SERP and the keyword analysis entirely, so
every Library-started article was written without SERP data, and any text in
``?library=`` became an article with no research at all.
"""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

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
    charge_library_start,
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

    # The signed-in user's Library, not the user id the payload claims.
    assert store.asked == [(("library", U1, W1), KEY)]
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


def test_the_charges_lead_to_the_content_steps():
    edges = {(e.source, e.target) for e in create_rext_engine().get_graph().edges}

    assert ("serp_engine", "charge_library_start") in edges
    assert ("charge_library_start", "content_engine") in edges
    assert ("serp_engine", "content_engine") not in edges
