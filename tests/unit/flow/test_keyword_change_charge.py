"""What the keyword gate charges for a kept keyword and for a changed one.

Topics are generated once, after the answer that keeps the keyword, so title
generation is charged once. A changed keyword or country goes back to the
analysis, which bills its own SERP pass; the change itself costs nothing more.
"""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

# The module refuses to import without these; the tests never call DataForSEO.
os.environ.setdefault("DATAFORSEO_BACKLINKS_URL", "https://dataforseo.test/keyword_overview")
os.environ.setdefault("DATAFORSEO_AUTH_HEADER", "test")

import src.flow.engines.seo.fetch_dataforseo_backlinks as overview_module
import src.flow.engines.seo.keyword_recomendation as recommendation_module
import src.utils.credit_manager as credit_module
from src.flow.engines.router.keyword_router import keyword_router
from src.services.plan_catalog import credit_rules

USER_ID = "00000000-0000-0000-0000-000000000001"
WORKSPACE_ID = "00000000-0000-0000-0000-000000000002"


@pytest.fixture
def charges(monkeypatch):
    """Every stage charged, in order."""
    consume = AsyncMock()
    monkeypatch.setattr(credit_module, "consume_stage_credits", consume)
    monkeypatch.setattr(
        overview_module,
        "get_dataforseo_data",
        AsyncMock(return_value={"search_volume": 1300, "volume_status": "ok"}),
    )

    def stages():
        return [call.args[2] for call in consume.await_args_list]

    return stages


def _payload(query="running shoes", country="us"):
    return {"query": query, "country": country, "user_id": USER_ID, "workspace_id": WORKSPACE_ID}


async def _analysis(payload):
    """The SERP pass the gate follows: the keyword overview bills serp_seo."""
    result = await overview_module.fetch_dataforseo_backlinks({"serp_payload": payload})
    return {
        "serp_payload": payload,
        "serp_result": {"serp_status": "ok"},
        "serp_normalized": {
            "normalize_results": [{"title": "A", "url": "https://a.test"}],
            "related_topics": ["trail running shoes"],
            "questions": [],
        },
        "seo_result": result["seo_result"],
    }


async def _gate(monkeypatch, state, answer):
    """The Library save, then the gate answered (two nodes, rext-control#330)."""
    monkeypatch.setattr(recommendation_module, "interrupt", lambda _payload: answer)
    runtime = SimpleNamespace(store=SimpleNamespace(aput=AsyncMock()))
    saved = await recommendation_module.save_keyword_research(state, {}, runtime=runtime)
    state = {**state, "seo_result": {**state["seo_result"], **saved["seo_result"]}}
    return await recommendation_module.keyword_recommendation(state)


async def test_keeping_the_keyword_charges_the_topics_once(monkeypatch, charges):
    state = await _analysis(_payload())

    result = await _gate(monkeypatch, state, "running shoes")

    assert keyword_router(result) == "END"
    assert charges() == ["serp_seo", "title_generation"]


async def test_a_keyword_too_long_for_any_title_is_not_charged_for_titles(monkeypatch, charges):
    # No title can contain it, so the topic step ends the run without one.
    keyword = "how to measure content marketing return on investment for small local businesses"
    state = await _analysis(_payload(query=keyword))

    result = await _gate(monkeypatch, state, keyword)

    assert keyword_router(result) == "END"
    assert charges() == ["serp_seo"]


@pytest.mark.parametrize(
    "answer",
    [
        {"Primary Keyword": "trail running shoes", "country": "us"},
        {"Primary Keyword": "running shoes", "country": "gb"},
    ],
    ids=["keyword", "country"],
)
async def test_a_change_charges_only_its_new_analysis(monkeypatch, charges, answer):
    first = await _gate(monkeypatch, await _analysis(_payload()), answer)
    assert keyword_router(first) == "SERP_ENGINE"
    assert charges() == ["serp_seo"]

    # The run goes back to the analysis with the new pair, and the gate asks again.
    second = await _gate(monkeypatch, await _analysis(first["serp_payload"]), answer)

    assert keyword_router(second) == "END"
    assert charges() == ["serp_seo", "serp_seo", "title_generation"]


async def test_the_catalogue_states_what_a_change_costs(monkeypatch, charges):
    first = await _gate(
        monkeypatch, await _analysis(_payload()), {"Primary Keyword": "trail running shoes"}
    )
    await _gate(monkeypatch, await _analysis(first["serp_payload"]), "trail running shoes")

    costs = credit_module.STAGE_CREDITS
    with_change = sum(costs[stage] for stage in charges())
    without_change = costs["serp_seo"] + costs["title_generation"]
    assert with_change - without_change == credit_rules()["keyword_change"] == 1
