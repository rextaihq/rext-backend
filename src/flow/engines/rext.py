import logging
from langgraph.graph import StateGraph, START, END
from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)

_compiled_graph = None


def create_rext_engine(checkpointer=None):
    """Create and return the compiled REXT workflow graph.

    Returns a cached singleton — the graph is compiled once and reused
    for all subsequent calls. Pass a checkpointer for state persistence
    when invoking the graph directly (outside the LangGraph Platform).
    """
    global _compiled_graph
    if _compiled_graph is not None:
        return _compiled_graph

    from src.flow.engines.serp.serp_engine import create_serp_engine
    from src.flow.engines.seo.seo_engine import create_seo_engine
    from src.flow.engines.content.content_engine import create_content_engine

    flow = StateGraph(REXT)

    flow.add_node("serp_engine", create_serp_engine())
    flow.add_node("seo_engine", create_seo_engine())
    flow.add_node("content_engine", create_content_engine())

    flow.add_edge(START, "serp_engine")
    flow.add_edge("serp_engine", "seo_engine")
    flow.add_edge("seo_engine", "content_engine")
    flow.add_edge("content_engine", END)

    compile_kwargs = {}
    if checkpointer:
        compile_kwargs["checkpointer"] = checkpointer

    _compiled_graph = flow.compile(**compile_kwargs)
    logger.info(
        "REXT workflow graph compiled and cached (checkpointer=%s)",
        "yes" if checkpointer else "no",
    )
    return _compiled_graph