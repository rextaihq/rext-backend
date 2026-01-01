import logging
from langgraph.graph import StateGraph, START, END
from src.flow.states.wrext import WREXT
from src.flow.engines.seo.seo_difficulty_engine.keyword_difficulty.keyword_difficulty import compute_keyword_difficulty
from src.flow.engines.seo.keyword_finder import relevance_keyword_finder
from src.flow.engines.seo.recomendation import recommendation
# from src.flow.engines.seo.seo_engine.keyword
logger = logging.getLogger(__name__)

def create_seo_engine():
    flow = StateGraph(WREXT)

    # add nodes
    # flow.add_node("seo_engine", SEOEngine)
    flow.add_node("seo_engine", compute_keyword_difficulty)
    flow.add_node("relevance_keyword_finder", relevance_keyword_finder)
    flow.add_node("recommendation", recommendation)

    # add edges
    # flow.add_edge(START, "seo_engine")
    flow.add_edge(START, "seo_engine")
    flow.add_edge("seo_engine", "relevance_keyword_finder")
    flow.add_edge("relevance_keyword_finder", "recommendation")
    flow.add_edge("recommendation", END)

    # compile and return
    app = flow.compile()
    return app