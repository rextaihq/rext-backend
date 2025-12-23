import logging
from langgraph.graph import StateGraph, START, END
from src.flow.states.wrext import WREXT
from src.flow.engines.seo.keyword_finder import keyword_finder

logger = logging.getLogger(__name__)

def create_seo_engine():
    flow = StateGraph(WREXT)

    # add nodes
    flow.add_node("find_keywords", keyword_finder)


    # add edges
    flow.add_edge(START, "find_keywords")
    flow.add_edge("find_keywords", END)

    # compile and return
    app = flow.compile()
    return app