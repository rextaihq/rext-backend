import logging
from langgraph.graph import StateGraph, START, END
from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)

def create_seo_engine():
    """
    Creates the Hybrid SEO Engine Graph with keyword_router.
    
    Flow:
    Parallel SEO analysis --> keyword_recommendation --> ROUTER --> Loop/Restart or END
    """
    from src.flow.engines.router.keywword_router import keyword_router
    from src.flow.engines.seo.seo_difficulty_engine.keyword_difficulty.keyword_difficulty import compute_keyword_difficulty
    from src.flow.engines.seo.competitors_gap import competitors_gap_node
    from src.flow.engines.seo.seo_opportunity import seo_opportunity_node
    from src.flow.engines.seo.keyword_finder import relevance_keyword_finder
    from src.flow.engines.seo.recomendation.keyword_recomendation import keyword_recommendation

    graph = StateGraph(REXT)

    def debug_node(func, node_name):
        def wrapped(state):
            result = func(state)
            print(f"\n{'='*20} NODE: {node_name} {'='*20}")
            print('='*50 + "\n")
            return result
        return wrapped

    graph.add_node("seo_entry", debug_node(lambda state: state, "seo_entry"))

    graph.add_node(
    "compute_keyword_difficulty",
    debug_node(compute_keyword_difficulty, "compute_keyword_difficulty")
    )

    # Add Nodes
    graph.add_node("competitors_gap", competitors_gap_node)
    graph.add_node("seo_opportunity", seo_opportunity_node)
    graph.add_node("relevance_keyword_finder", relevance_keyword_finder)
    graph.add_node("keyword_recommendation", keyword_recommendation)

    # ✅ FIX 1: Proper parallel fan-out (single START path)
    graph.add_edge(START, "seo_entry")
    graph.add_edge("seo_entry", "compute_keyword_difficulty")
    graph.add_edge("seo_entry", "competitors_gap")
    graph.add_edge("seo_entry", "seo_opportunity")
    graph.add_edge("seo_entry", "relevance_keyword_finder")

    # ✅ FIX 2: All paths converge to keyword_recommendation
    graph.add_edge("compute_keyword_difficulty", "keyword_recommendation")
    graph.add_edge("competitors_gap", "keyword_recommendation")
    graph.add_edge("seo_opportunity", "keyword_recommendation")
    graph.add_edge("relevance_keyword_finder", "keyword_recommendation")
    # graph.add_edge("keyword_recommendation", END)

    graph.add_conditional_edges(
        "keyword_recommendation",
        keyword_router,
        {
            "END": END,
            "SEO_ENGINE": "seo_entry" 
        }
    )

    return graph.compile()