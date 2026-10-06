"""A run started from the keyword Library uses the item's research (E17, rext-control#368).

Before, ``is_library`` skipped the SERP and the keyword analysis entirely, so
every Library-started article was written without SERP data, and any text in
``?library=`` became an article with no research at all.
"""

from types import SimpleNamespace

import src.flow.engines.serp.normalization as normalization_module
from src.flow.engines.rext import _after_serp
from src.flow.engines.router.library_router import library_router
from src.flow.engines.seo.library_item import (
    LIBRARY_ITEM_MESSAGE,
    LIBRARY_ITEM_MISSING,
    library_item_router,
    load_library_item,
)

KEY = "library_content marketing roi_2026-10-05T12:00:00+00:00"
ITEM = {
    "original_query": "content marketing roi",
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


def _state(**payload):
    return {
        "serp_payload": {
            "query": "whatever the link carried",
            "is_library": True,
            "user_id": "u-payload",
            "workspace_id": "w1",
            "country": "us",
            **payload,
        }
    }


def _config(user="u1"):
    return {"configurable": {"langgraph_auth_user_id": user}}


async def test_a_library_start_loads_the_item_from_the_callers_library():
    store = Store({(("library", "u1", "w1"), KEY): ITEM})

    update = await load_library_item(
        _state(library_key=KEY), _config("u1"), runtime=SimpleNamespace(store=store)
    )

    # The signed-in user's Library, not the user id the payload claims.
    assert store.asked == [(("library", "u1", "w1"), KEY)]
    assert update["serp_payload"] == {"query": "content marketing roi"}
    seo = update["seo_result"]
    assert seo["serp_backlinks"]["search_volume"] == 1900
    assert seo["serp_backlinks"]["volume_status"] == "ok"
    assert seo["serp_backlinks"]["keyword_difficulty"] == 38
    assert seo["serp_backlinks"]["main_intent"] == "informational"
    assert seo["intent_type"] == "commercial"
    assert seo["keyword_recommendations"]["selected_keyword"] == "content marketing roi"
    assert seo["keyword_recommendations"]["is_changed"] is False
    assert library_item_router({"content": {}, **update}) == "serp_engine"


async def test_free_text_or_an_unknown_item_is_refused_with_a_message():
    store = Store({(("library", "u1", "w1"), KEY): ITEM})

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


async def test_the_router_sends_a_library_start_to_load_its_item(monkeypatch):
    state = {"serp_payload": {"is_library": True, "query": "q"}}

    assert await library_router(state) == "load_library_item"
    assert await library_router({"serp_payload": {"query": "q"}}) == "serp_engine"


def test_after_the_serp_a_library_start_skips_the_keyword_gate(monkeypatch):
    monkeypatch.setattr(normalization_module, "has_organic_results", lambda state: True)
    assert _after_serp({"serp_payload": {"is_library": True}}) == "content_engine"
    assert _after_serp({"serp_payload": {}}) == "seo_engine"

    monkeypatch.setattr(normalization_module, "has_organic_results", lambda state: False)
    assert _after_serp({"serp_payload": {"is_library": True}}) == "no_serp_data"
