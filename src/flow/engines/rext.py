import logging
from langgraph.graph import StateGraph, START, END
from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)


def create_rext_engine():
    """Create and return the compiled REXT workflow graph.

    Returns a cached singleton — the graph is compiled once and reused
    for all subsequent calls. Pass a checkpointer for state persistence
    when invoking the graph directly (outside the LangGraph Platform).
    """

    from src.flow.engines.serp.serp_engine import create_serp_engine
    from src.flow.engines.seo.seo_engine import create_seo_engine
    from src.flow.engines.content.content_engine import create_content_engine
    from src.flow.engines.router.library_router import library_router

    flow = StateGraph(REXT)

    flow.add_node("serp_engine", create_serp_engine())
    flow.add_node("seo_engine", create_seo_engine())
    flow.add_node("content_engine", create_content_engine())

    flow.add_conditional_edges(
        START,
        library_router,
        {
            "serp_engine": "serp_engine",
            "content_engine": "content_engine"
        }
    )




    flow.add_edge("serp_engine", "seo_engine")
    flow.add_edge("seo_engine", "content_engine")
    flow.add_edge("content_engine", END)

    return flow.compile()