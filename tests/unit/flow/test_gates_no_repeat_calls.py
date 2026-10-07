"""Answering a gate repeats no model call and no write (rext-control#330).

LangGraph runs a node again from its start when the user's answer resumes it, so
a model call or a Library write in the gate's own node ran again on every
answer: the content-type pick twice, every title set once more per answer (and
the set kept was not the one shown), and every kept keyword saved to the
Library twice. Each gate's work now runs in a node before the gate. These tests
pause each gate on a checkpointer, answer it, and count the calls.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command

import src.flow.engines.content.generation.content_type as content_type_module
import src.flow.engines.content.generation.topic_generation as topic_module
import src.flow.engines.seo.keyword_recomendation as keyword_module
from src.flow.engines.content.generation.focus_keyword import FOCUS_KEYWORD_STATE_KEY
from src.flow.states.rext import REXT

QUERY = "content marketing roi for small business"
CONFIG = {"configurable": {"thread_id": "gate-test"}}
FIRST_SET = [
    "Content Marketing ROI for Small Business: A Practical Guide",
    "How to Measure Content Marketing ROI for Small Business",
]
SECOND_SET = [
    "Content Marketing ROI for Small Business: What to Track",
    "Content Marketing ROI for Small Business in Five Steps",
]


async def _pending_gate(app) -> dict:
    """The payload of the gate the thread is paused on."""
    snapshot = await app.aget_state(CONFIG)
    return snapshot.tasks[0].interrupts[0].value


def _title_set(titles):
    return SimpleNamespace(
        topics=[
            SimpleNamespace(title=title, recommended=index == 0, recommendation_reason="Fits")
            for index, title in enumerate(titles)
        ]
    )


async def test_answering_the_content_type_gate_asks_the_model_once(monkeypatch):
    calls = []

    def recommend(query, search_intent, candidates):
        calls.append(query)
        return candidates[0], "The format most people searching this want"

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
            "serp_normalized": {"query": QUERY},
            "seo_result": {"serp_backlinks": {"main_intent": "informational"}},
        },
        CONFIG,
    )
    gate = await _pending_gate(app)
    assert gate["type"] == "content_type"
    assert gate["recommended_content_type"] == gate["content_types"][0]
    assert gate["recommendation_reason"] == "The format most people searching this want"

    chosen = gate["content_types"][1]
    done = await app.ainvoke(Command(resume=chosen), CONFIG)

    assert done["content"]["content_type"] == chosen
    assert calls == [QUERY]


def _topic_graph(*, with_generation=True):
    graph = StateGraph(REXT)
    graph.add_node("topic_generation", topic_module.topic_generation)
    if with_generation:
        graph.add_node("generate_topics", topic_module.generate_topics)
        graph.add_edge(START, "generate_topics")
        graph.add_conditional_edges(
            "generate_topics",
            topic_module.topics_router,
            {"topic_generation": "topic_generation", "topics_failed": END},
        )
        graph.add_conditional_edges(
            "topic_generation",
            topic_module.topic_gate_router,
            {"generate_topics": "generate_topics", "keyword_clustering": END},
        )
    else:
        graph.add_edge(START, "topic_generation")
        graph.add_edge("topic_generation", END)
    return graph.compile(checkpointer=InMemorySaver())


async def test_the_title_gate_calls_the_model_once_per_set_and_keeps_the_set_shown(monkeypatch):
    sets = iter([_title_set(FIRST_SET), _title_set(SECOND_SET)])
    generate = AsyncMock(side_effect=lambda **kwargs: next(sets))
    monkeypatch.setattr(topic_module, "_generate_and_validate_topics", generate)
    monkeypatch.setattr(
        topic_module,
        "topic_generation_model",
        lambda: SimpleNamespace(with_structured_output=lambda schema: object()),
    )
    app = _topic_graph()

    await app.ainvoke(
        {
            "serp_normalized": {"query": QUERY},
            "serp_payload": {"query": QUERY},
            "content": {"content_type": "blog"},
        },
        CONFIG,
    )
    first = await _pending_gate(app)
    assert first["topics"] == FIRST_SET
    assert first["recommended_topic"] == FIRST_SET[0]
    assert first["focus_keyphrase"] == QUERY

    await app.ainvoke(
        Command(resume={"action": "regenerate", "feedback": "more practical"}), CONFIG
    )
    second = await _pending_gate(app)
    assert second["topics"] == SECOND_SET
    # The feedback went to the model with the new set's call, and only there.
    assert "more practical" in generate.await_args_list[1].kwargs["messages"][-1].content
    assert "more practical" not in str(generate.await_args_list[0].kwargs["messages"])

    done = await app.ainvoke(Command(resume={"selected_topic": SECOND_SET[1]}), CONFIG)

    assert generate.await_count == 2
    assert done["content"]["selected_topic"] == SECOND_SET[1]
    assert done["content"]["topics"] == SECOND_SET
    assert done["content"][FOCUS_KEYWORD_STATE_KEY] == QUERY
    assert done["content"][topic_module.TOPIC_REGENERATE_KEY] is None


async def test_a_failed_regeneration_shows_the_set_the_user_had(monkeypatch):
    sets = iter([_title_set(FIRST_SET), None])
    generate = AsyncMock(side_effect=lambda **kwargs: next(sets))
    monkeypatch.setattr(topic_module, "_generate_and_validate_topics", generate)
    monkeypatch.setattr(
        topic_module,
        "topic_generation_model",
        lambda: SimpleNamespace(with_structured_output=lambda schema: object()),
    )
    app = _topic_graph()

    await app.ainvoke(
        {"serp_normalized": {"query": QUERY}, "serp_payload": {"query": QUERY}}, CONFIG
    )
    await app.ainvoke(Command(resume="regenerate"), CONFIG)

    assert (await _pending_gate(app))["topics"] == FIRST_SET
    assert generate.await_count == 2


async def test_a_title_gate_paused_before_the_split_resumes_without_a_model_call(monkeypatch):
    # A thread paused inside the old one-node topic step resumes into the gate
    # node of the same name, with no title set in its state: the answer is
    # read and the run goes on, and nothing calls the model.
    generate = AsyncMock()
    monkeypatch.setattr(topic_module, "_generate_and_validate_topics", generate)
    app = _topic_graph(with_generation=False)

    await app.ainvoke(
        {"serp_normalized": {"query": QUERY}, "serp_payload": {"query": QUERY}}, CONFIG
    )
    done = await app.ainvoke(Command(resume={"selected_topic": FIRST_SET[0]}), CONFIG)

    assert done["content"]["selected_topic"] == FIRST_SET[0]
    assert done["content"][FOCUS_KEYWORD_STATE_KEY] == QUERY
    generate.assert_not_awaited()


def _keyword_graph(store):
    graph = StateGraph(REXT)
    graph.add_node("save_keyword_research", keyword_module.save_keyword_research)
    graph.add_node("keyword_recommendation", keyword_module.keyword_recommendation)
    graph.add_edge(START, "save_keyword_research")
    graph.add_conditional_edges(
        "save_keyword_research",
        keyword_module.keyword_research_router,
        {"keyword_recommendation": "keyword_recommendation", "end": END},
    )
    graph.add_edge("keyword_recommendation", END)
    return graph.compile(checkpointer=InMemorySaver(), store=store)


KEYWORD_STATE = {
    "serp_payload": {"query": QUERY, "country": "us", "user_id": "u1", "workspace_id": "w1"},
    "serp_normalized": {
        "query": QUERY,
        "related_topics": ["content marketing metrics"],
        "normalize_results": [{"title": "A result", "url": "https://example.com", "position": 1}],
    },
    "seo_result": {"serp_backlinks": {"main_intent": "informational", "search_volume": 320}},
}


async def test_answering_the_keyword_gate_saves_the_research_once_and_charges_once(monkeypatch):
    charge = AsyncMock()
    monkeypatch.setattr(keyword_module, "charge_title_generation", charge)
    monkeypatch.setattr(keyword_module, "has_organic_results", lambda state: True)
    store = InMemoryStore()
    app = _keyword_graph(store)

    await app.ainvoke(KEYWORD_STATE, CONFIG)
    gate = await _pending_gate(app)
    assert gate["type"] == "keyword Selection"
    assert gate["Primary Keyword"] == QUERY
    assert gate["Recommendations"] == ["content marketing metrics"]
    assert gate["seo_state"]["volume"] == 320
    # The top ten for the side pane, as the title gate sends them.
    assert [(t["position"], t["title"]) for t in gate["serp_titles"]] == [(1, "A result")]

    done = await app.ainvoke(Command(resume={"Primary Keyword": QUERY}), CONFIG)

    saved = await store.asearch(("library", "u1", "w1"))
    assert len(saved) == 1
    assert done["seo_result"]["keyword_recommendations"]["library_key"] == saved[0].key
    assert done["seo_result"]["keyword_recommendations"]["is_changed"] is False
    charge.assert_awaited_once()


async def test_nothing_saved_means_no_keyword_gate(monkeypatch):
    # No workspace on the run: nothing is written to the Library, and the run
    # leaves the SEO step without a gate, as it did before the split.
    monkeypatch.setattr(keyword_module, "has_organic_results", lambda state: True)
    store = InMemoryStore()
    app = _keyword_graph(store)
    state = {**KEYWORD_STATE, "serp_payload": {"query": QUERY, "user_id": "u1"}}

    done = await app.ainvoke(state, CONFIG)

    assert (await app.aget_state(CONFIG)).tasks == ()
    assert done["seo_result"][keyword_module.KEYWORD_RESEARCH_KEY] is None
    assert await store.asearch(("library", "u1")) == []
