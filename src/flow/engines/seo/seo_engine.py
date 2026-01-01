from langgraph.graph import StateGraph, START, END
from src.flow.states.wrext import WREXT

from src.flow.engines.seo.keyword_difficulty import keyword_difficulty_node
# from src.flow.engines.seo.competitors_gap import competitors_gap_node
# from src.flow.engines.seo.seo_opportunity import seo_opportunity_node

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

    graph.add_node("keyword_difficulty", debug_node(keyword_difficulty_node, "keyword_difficulty"))
    # graph.add_node("competitors_gap", debug_node(competitors_gap_node, "competitors_gap"))
    # graph.add_node("seo_opportunity", debug_node(seo_opportunity_node, "seo_opportunity"))

    graph.add_edge(START, "keyword_difficulty")
    # graph.add_edge("keyword_difficulty", "competitors_gap")
    # graph.add_edge("competitors_gap", "seo_opportunity")
    graph.add_edge("keyword_difficulty", END)

    return graph.compile()
