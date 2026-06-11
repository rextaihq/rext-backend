import logging
from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph
from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)

def create_seo_engine() -> CompiledStateGraph:
    """Create the SEO analysis engine workflow.

    Builds a LangGraph subgraph with parallel SEO analysis nodes
    (keyword difficulty, competitor gap, SEO opportunity, keyword
    finder) followed by keyword recommendation with conditional
    routing for user-driven keyword iteration.
 
    Returns:
        CompiledStateGraph: Compiled SEO engine subgraph.
    """
    from src.flow.engines.router.keyword_router import keyword_router
    from src.flow.engines.seo.fetch_dataforseo_backlinks import fetch_dataforseo_backlinks
    from src.flow.engines.seo.keyword_recomendation import keyword_recommendation

    graph = StateGraph(REXT)

    graph.add_node("seo_entry", lambda state: state)

    # Add Nodes
    graph.add_node("fetch_dataforseo_backlinks", fetch_dataforseo_backlinks)
    graph.add_node("keyword_recommendation", keyword_recommendation)
    

    graph.add_edge(START, "seo_entry")
    graph.add_edge("seo_entry", "fetch_dataforseo_backlinks")
    graph.add_edge("fetch_dataforseo_backlinks", "keyword_recommendation")


    graph.add_conditional_edges(
        "keyword_recommendation",
        keyword_router,
        {
            "END": END,
            "SEO_ENGINE": "seo_entry" 
        }
    )

    return graph.compile()