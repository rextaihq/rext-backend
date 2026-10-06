import logging

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)


def create_seo_engine() -> CompiledStateGraph:
    """Create the SEO analysis engine workflow.

    Builds a LangGraph subgraph with parallel SEO analysis nodes
    (keyword difficulty, competitor gap, SEO opportunity, keyword
    finder), then the research saved to the keyword Library, then
    keyword recommendation, which pauses for the user's keyword/country
    selection. The save is a node of its own so the answer that resumes
    the gate never repeats it (rext-control#330).

    Returns:
        CompiledStateGraph: Compiled SEO engine subgraph.
    """
    from src.flow.engines.seo.fetch_dataforseo_backlinks import fetch_dataforseo_backlinks
    from src.flow.engines.seo.keyword_recomendation import (
        keyword_recommendation,
        keyword_research_router,
        save_keyword_research,
    )

    graph = StateGraph(REXT)

    graph.add_node("seo_entry", lambda state: state)

    # Add Nodes
    graph.add_node("fetch_dataforseo_backlinks", fetch_dataforseo_backlinks)
    graph.add_node("save_keyword_research", save_keyword_research)
    graph.add_node("keyword_recommendation", keyword_recommendation)

    graph.add_edge(START, "seo_entry")
    graph.add_edge("seo_entry", "fetch_dataforseo_backlinks")
    graph.add_edge("fetch_dataforseo_backlinks", "save_keyword_research")
    # Nothing saved (no user or workspace, no organic result, a store error):
    # no gate, as before; keyword_router decides what follows.
    graph.add_conditional_edges(
        "save_keyword_research",
        keyword_research_router,
        {"keyword_recommendation": "keyword_recommendation", "end": END},
    )

    # Keyword/country changes are routed by the parent graph (keyword_router),
    # which re-runs the SERP engine first so nothing from the previous
    # keyword/country is reused.
    graph.add_edge("keyword_recommendation", END)

    return graph.compile()
