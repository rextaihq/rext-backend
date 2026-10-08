"""Any keyword can become an article, whatever its intent was read as (revnix/rext-control#815).

The content-type step offered only the types of the keyword's intent, and the intent is the
search provider's label. "remote team onboarding" (no brand, no site) was read as navigational
and offered a brand's own pages: help center, brand page, login guide. No blog, no how-to, no
way to reach one, and the run was cancelled there. The step now offers the article types after
the intent's own, and the dashboard folds what it does not lead with under "more".
"""

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

import src.flow.engines.content.generation.content_type as content_type_module
from src.flow.engines.content.generation.content_type import (
    ARTICLE_TYPES_FOR_ANY_INTENT,
    intent_of_choice,
    offered_content_types,
    recommended_among,
)
from src.flow.model.structure.intent_suggestion import INTENT_TO_CONTENT_TYPES
from src.flow.states.rext import REXT

CONFIG = {"configurable": {"thread_id": "any-intent"}}


def _results(*titles):
    """Search results as the run keeps them (`serp_normalized.normalize_results`)."""
    return [
        {"title": title, "url": f"https://site{n}.example/blog/page", "rank": n}
        for n, title in enumerate(titles, 1)
    ]


HOW_TO_RESULTS = _results(
    "How to Onboard a Remote Team: 9 Steps",
    "How to Onboard Remote Employees",
    "How to Build a Remote Onboarding Process",
    "How to Run Remote Team Onboarding in 30 Days",
    "How to Welcome a Remote Hire",
    "Remote onboarding checklist",
)


async def _gate(monkeypatch, intent, query="remote team onboarding", results=None):
    """The content-type gate's payload for a keyword of that intent, the candidates the
    recommendation was made among, and the app to answer it with."""
    asked = []

    def recommend(query, search_intent, candidates):
        asked.append(list(candidates))
        return (candidates[0] if candidates else None), "Fits"

    monkeypatch.setattr(content_type_module, "_recommend_content_type", recommend)
    graph = StateGraph(REXT)
    graph.add_node("recommend_content_type", content_type_module.recommend_content_type)
    graph.add_node("content_type", content_type_module.content_type)
    graph.add_edge(START, "recommend_content_type")
    graph.add_edge("recommend_content_type", "content_type")
    graph.add_edge("content_type", END)
    app = graph.compile(checkpointer=InMemorySaver())
    await app.ainvoke(
        {
            "serp_normalized": {"query": query, "normalize_results": results or []},
            "seo_result": {
                "intent_type": intent,
                "serp_backlinks": {"main_intent": intent, "search_volume": 10},
            },
        },
        CONFIG,
    )
    snapshot = await app.aget_state(CONFIG)
    return snapshot.tasks[0].interrupts[0].value, asked[0], app


@pytest.mark.parametrize("intent", ["navigational", "transactional", "commercial"])
async def test_a_keyword_of_any_intent_is_offered_the_article_types_after_its_own(
    monkeypatch, intent
):
    gate, recommended_among, app = await _gate(monkeypatch, intent)

    own = INTENT_TO_CONTENT_TYPES[intent]
    # The intent's own types lead, in their order; the article types follow.
    assert gate["content_types"] == [*own, "blog", "how-to-guide", "explainer"]
    assert gate["search_intent"] == intent
    # The recommendation is still made among the intent's own types: a brand's own name
    # keeps its site pages first.
    assert recommended_among == own
    assert gate["recommended_content_type"] == own[0]
    # And the article type the customer picks is the one the run goes on with, as an article:
    # the titles and the outline read the intent from the run, and "navigational" asked the
    # titles to name a destination or a brand (review round 1).
    done = await app.ainvoke(Command(resume="blog"), CONFIG)
    assert done["content"]["content_type"] == "blog"
    assert done["seo_result"]["serp_backlinks"] == {
        "main_intent": "informational",
        "search_volume": 10,
    }
    assert done["seo_result"]["intent_type"] == "informational"


async def test_a_type_of_the_keywords_own_intent_leaves_the_intent_as_it_was(monkeypatch):
    gate, _, app = await _gate(monkeypatch, "navigational", query="acme tools")

    done = await app.ainvoke(Command(resume={"Selected Content Type": "brand-page"}), CONFIG)

    assert done["content"]["content_type"] == "brand-page"
    assert done["seo_result"]["serp_backlinks"]["main_intent"] == "navigational"
    assert done["seo_result"]["intent_type"] == "navigational"


def test_the_intent_follows_the_type_only_across_intents():
    assert intent_of_choice("blog", "navigational") == "informational"
    assert intent_of_choice("how-to-guide", "Transactional") == "informational"
    assert intent_of_choice("comparison", "navigational") == "commercial"
    assert intent_of_choice("help-center", "navigational") == "navigational"
    assert intent_of_choice("blog", "informational") == "informational"
    # Free text, or nothing: the intent stays.
    assert intent_of_choice("article", "navigational") == "navigational"
    assert intent_of_choice("", "commercial") == "commercial"


async def test_an_informational_keyword_is_offered_what_it_was(monkeypatch):
    gate, recommended_among, _ = await _gate(monkeypatch, "informational")

    assert gate["content_types"] == INTENT_TO_CONTENT_TYPES["informational"]
    assert recommended_among == INTENT_TO_CONTENT_TYPES["informational"]


async def test_an_intent_with_no_types_of_its_own_is_offered_the_article_types(monkeypatch):
    """A label the table does not know ("local") offered an empty step."""
    gate, recommended_among, _ = await _gate(monkeypatch, "local")

    assert gate["content_types"] == list(ARTICLE_TYPES_FOR_ANY_INTENT)
    assert recommended_among == [] and gate["recommended_content_type"] is None


def test_the_article_types_are_ones_the_product_writes_and_none_is_offered_twice():
    from src.flow.model.structure.outlines import CONTENT_TYPE_TO_MODEL

    assert set(ARTICLE_TYPES_FOR_ANY_INTENT) <= set(CONTENT_TYPE_TO_MODEL)
    assert set(ARTICLE_TYPES_FOR_ANY_INTENT) <= set(INTENT_TO_CONTENT_TYPES["informational"])
    for own in INTENT_TO_CONTENT_TYPES.values():
        offered = offered_content_types(own)
        assert len(offered) == len(set(offered)) and offered[: len(own)] == own


def test_the_pick_may_be_an_article_type_only_where_the_results_lead_with_one():
    """The intent is the provider's label; the results are what a searcher is shown. When they
    are mostly how-to guides or explainers, that type joins the ones the pick is made among.
    Home pages, list posts or no leading format leave the intent's own, as before."""
    own = INTENT_TO_CONTENT_TYPES["navigational"]

    def leading(*types):
        return {"dominant_format": {"content_types": list(types)}}

    assert recommended_among(own, leading("how-to-guide", "tutorial")) == [*own, "how-to-guide"]
    assert recommended_among(own, leading("explainer", "glossary", "faq")) == [*own, "explainer"]
    assert recommended_among(own, leading("product-homepage", "landing-page", "brand-page")) == own
    assert recommended_among(own, leading("best-tools", "product-roundup")) == own
    assert recommended_among(own, {"dominant_format": None}) == own
    assert recommended_among(own, None) == own
    informational = INTENT_TO_CONTENT_TYPES["informational"]
    assert recommended_among(informational, leading("how-to-guide")) == informational


async def test_a_keyword_read_as_navigational_whose_results_are_how_to_guides(monkeypatch):
    """The reported keyword, as the step now reads it from its results."""
    from src.flow.engines.serp.serp_evidence import build_serp_evidence

    evidence = build_serp_evidence({"normalize_results": HOW_TO_RESULTS})
    assert evidence["dominant_format"]["format"] == "how-to"

    gate, among, _ = await _gate(monkeypatch, "navigational", results=HOW_TO_RESULTS)

    assert (
        "how-to-guide" in among
        and among[: len(INTENT_TO_CONTENT_TYPES["navigational"])]
        == (INTENT_TO_CONTENT_TYPES["navigational"])
    )
    assert "blog" in gate["content_types"]
