import logging
from langgraph.graph import StateGraph, START, END
from src.flow.states.wrext import WREXT

from src.flow.engines.seo.seo_difficulty_engine.keyword_difficulty.keyword_difficulty import compute_keyword_difficulty
from src.flow.engines.seo.competitors_gap import competitors_gap_node
from src.flow.engines.seo.seo_opportunity import seo_opportunity_node
from src.flow.engines.seo.keyword_finder import relevance_keyword_finder
from src.flow.engines.seo.recomendation.recomendation import recommendation

logger = logging.getLogger(__name__)

def create_seo_engine():
    """
    Creates the Hybrid SEO Engine Graph.
    
    Flow:
    1. Keyword Difficulty (Advanced) - Calculates detailed difficulty breakdown
    2. Competitors Gap - Identifies missing topics and questions
    3. SEO Opportunity - Scores opportunity based on difficulty and gaps
    4. Keyword Finder - Extracts relevant keywords from SERP
    5. Recommendation - Interactive title recommendation
    """
    graph = StateGraph(WREXT)

    # Add Nodes
    graph.add_node("compute_keyword_difficulty", compute_keyword_difficulty)
    graph.add_node("competitors_gap", competitors_gap_node)
    graph.add_node("seo_opportunity", seo_opportunity_node)
    graph.add_node("relevance_keyword_finder", relevance_keyword_finder)
    graph.add_node("keyword_recommendation", recommendation)

    # Add Edges (Linear Flow)
    graph.add_edge(START, "compute_keyword_difficulty")
    graph.add_edge(START, "competitors_gap")
    graph.add_edge(START, "seo_opportunity")
    graph.add_edge(START, "relevance_keyword_finder")


    graph.add_edge("compute_keyword_difficulty", "keyword_recommendation")
    graph.add_edge("competitors_gap", "keyword_recommendation")
    graph.add_edge("seo_opportunity", "keyword_recommendation")
    graph.add_edge("relevance_keyword_finder", "keyword_recommendation")
    graph.add_edge("keyword_recommendation", END)

    return graph.compile()
