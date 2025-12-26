import logging
from langgraph.graph import StateGraph, START, END
from src.flow.states.wrext import WREXT
from src.flow.engines.seo.keyword_finder import relevance_keyword_finder

logger = logging.getLogger(__name__)

def create_seo_engine():
    flow = StateGraph(WREXT)

    # add nodes
    flow.add_node("relevance_keyword_finder", relevance_keyword_finder)


    # add edges
    flow.add_edge(START, "relevance_keyword_finder")
    flow.add_edge("relevance_keyword_finder", END)

    # compile and return
    app = flow.compile()
    return app