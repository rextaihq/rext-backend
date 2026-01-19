import logging
from langgraph.graph import StateGraph, START, END
from src.flow.states.wrext import WREXT
logger = logging.getLogger(__name__)

def create_wrext_engine():
    from src.flow.engines.serp.serp_engine import create_serp_engine
    from src.flow.engines.seo.seo_engine import create_seo_engine
    from src.flow.engines.content.content_engine import create_content_engine

    flow = StateGraph(WREXT)

    # add enginess and do connection
    flow.add_node("serp_engine", create_serp_engine())
    flow.add_node("seo_engine", create_seo_engine())
    flow.add_node("content_engine", create_content_engine())

    # add edges
    flow.add_edge(START, "serp_engine")
    flow.add_edge("serp_engine", "seo_engine")
    flow.add_edge("seo_engine", "content_engine")
    flow.add_edge("content_engine", END)

    # compile engines
    app = flow.compile()
    return app