import logging
# from langgraph.graph import StateGraph, START, END
# from src.flow.states.wrext import WREXT
# from src.flow.engines.seo.keyword_finder import keyword_finder

# logger = logging.getLogger(__name__)

# def create_seo_engine():
#     flow = StateGraph(WREXT)

#     # add nodes
#     flow.add_node("find_keywords", keyword_finder)


#     # add edges
#     flow.add_edge(START, "find_keywords")
#     flow.add_edge("find_keywords", END)

#     # compile and return
#     app = flow.compile()
#     return app

# src/flow/engines/seo/seo_engine.py

from langgraph.graph import StateGraph, START, END
from src.flow.states.wrext import WREXT

from src.flow.engines.seo.keyword_score import keyword_score_node
from src.flow.engines.seo.keyword_difficulty import keyword_difficulty_node
from src.flow.engines.seo.competetor_gap import competitor_gap_node
from src.flow.engines.seo.seo_opportunity import seo_opportunity_node
from src.flow.engines.seo.article_decision import article_decision_node

logger = logging.getLogger(__name__)

def create_seo_engine():
    graph = StateGraph(WREXT)

    def debug_node(node_func, name):
        def wrapped(state):
            result = node_func(state)
            print(f"\n{'='*20} NODE: {name} {'='*20}")
            print(result)
            print('='*50 + "\n")
            return result
        return wrapped

    # graph.add_node("keyword_score", debug_node(keyword_score_node, "keyword_score"))
    graph.add_node("keyword_difficulty", debug_node(keyword_difficulty_node, "keyword_difficulty"))
    # graph.add_node("competitor_gap", debug_node(competitor_gap_node, "competitor_gap"))
    # graph.add_node("seo_opportunity", debug_node(seo_opportunity_node, "seo_opportunity"))
    # graph.add_node("article_decision", debug_node(article_decision_node, "article_decision"))

    graph.add_edge(START, "keyword_difficulty")
    # graph.add_edge("keyword_score", "keyword_difficulty")
    # graph.add_edge("keyword_difficulty", "competitor_gap")
    # graph.add_edge("competitor_gap", "seo_opportunity")
    # graph.add_edge("seo_opportunity", "article_decision")
    graph.add_edge("keyword_difficulty", END)

    return graph.compile()
