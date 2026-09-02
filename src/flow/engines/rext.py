import logging

from langgraph.graph import END, START, StateGraph

from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)


def create_rext_engine():
    """Create and return the compiled REXT workflow graph.

    Returns a cached singleton — the graph is compiled once and reused
    for all subsequent calls. Pass a checkpointer for state persistence
    when invoking the graph directly (outside the LangGraph Platform).
    """

    from src.flow.engines.content.content_engine import create_content_engine
    from src.flow.engines.router.library_router import library_router
    from src.flow.engines.seo.seo_engine import create_seo_engine
    from src.flow.engines.serp.serp_engine import create_serp_engine

    flow = StateGraph(REXT)

    flow.add_node("serp_engine", create_serp_engine())
    flow.add_node("seo_engine", create_seo_engine())
    flow.add_node("content_engine", create_content_engine())
    flow.add_node("insufficient_credits", _insufficient_credits)

    flow.add_conditional_edges(
        START,
        library_router,
        {
            "serp_engine": "serp_engine",
            "content_engine": "content_engine",
            "insufficient_credits": "insufficient_credits",
        },
    )

    flow.add_edge("serp_engine", "seo_engine")
    flow.add_edge("seo_engine", "content_engine")
    flow.add_edge("content_engine", END)
    flow.add_edge("insufficient_credits", END)

    return flow.compile()


async def _insufficient_credits(state: REXT) -> dict:
    """Terminal node for runs blocked by the credit gate in library_router."""
    return {
        "content": {
            "error": "Insufficient credits to generate content. Please upgrade your plan.",
            "error_code": "insufficient_credits",
        }
    }
