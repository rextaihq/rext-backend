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

    def debug_node(func, node_name):
        def wrapped(state):
            result = func(state)
            print(f"\n{'='*20} NODE: {node_name} {'='*20}")
            print(result)
            print('='*50 + "\n")
            return result
        return wrapped


    flow.add_node(
    "keyword_difficulty_engine",
    debug_node(compute_keyword_difficulty, "keyword_difficulty_engine")
    )


    # add nodes
    # flow.add_node("seo_engine", SEOEngine)
    # flow.add_node("seo_engine", compute_keyword_difficulty)
    # flow.add_node("relevance_keyword_finder", relevance_keyword_finder)
    # flow.add_node("recommendation", recommendation)

    # add edges
    # flow.add_edge(START, "seo_engine")
    flow.add_edge(START, "keyword_difficulty_engine")
    # flow.add_edge("keyword_difficulty_engine", "relevance_keyword_finder")
    # flow.add_edge("relevance_keyword_finder", "recommendation")
    flow.add_edge("keyword_difficulty_engine", END)

    # compile and return
    app = flow.compile()
    return app