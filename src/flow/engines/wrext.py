import logging
from langgraph.graph import StateGraph, START, END
from src.flow.states.wrext import WREXT
from src.flow.engines.serp.serp_engine import create_serp_engine
from src.flow.engines.seo.seo_engine import create_seo_engine

logger = logging.getLogger(__name__)

def create_wrext_engine():
    flow = StateGraph(WREXT)

    # add engines
    flow.add_node("serp_engine", create_serp_engine())
    flow.add_node("seo_engine", create_seo_engine())


    # add edges
    flow.add_edge(START, "serp_engine")
    flow.add_edge("serp_engine", "seo_engine")
    flow.add_edge("seo_engine", END)

    # compile engines
    app = flow.compile()
    return app