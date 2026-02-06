import logging
from langgraph.graph import StateGraph, START, END
from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)

def create_serp_engine() -> StateGraph:
    """
    Initialize and return the SERP processing flow graph.

    The flow consists of:
    1. Fetching SERP results from an external API.
    2. Normalizing the raw results into a structured format.
    3. Extracting competitor information from the results.

    Returns:
        StateGraph: The configured LangGraph StateGraph for the SERP flow.
    """
    from src.flow.engines.serp.fetch_serp import fetch_serp_results
    # from src.flow.engines.serp.serp_backlinks import get_serp_backlinks
    # from src.flow.engines.serp.normalization import normalize_serp_results
    # from src.flow.engines.serp.competitor import extract_competitors_from_serp
    # from src.flow.engines.scrape.scrape_engine import create_scrape_engine

    serp_flow = StateGraph(REXT)

    # Add nodes
    serp_flow.add_node("fetch_serp", fetch_serp_results)
    # serp_flow.add_node("serp_backlinks", get_serp_backlinks)
    # serp_flow.add_node("normalize_serp", normalize_serp_results)
    # serp_flow.add_node("extract_competitor", extract_competitors_from_serp)
    # serp_flow.add_node("scrape_flow", create_scrape_engine())

    # Add edges
    serp_flow.add_edge(START, "fetch_serp") 
    serp_flow.add_edge(START, "serp_backlinks")
    serp_flow.add_edge("fetch_serp", "normalize_serp")
    serp_flow.add_edge("fetch_serp", "extract_competitor")

    scraping flow
    serp_flow.add_edge("normalize_serp", "scrape_flow")
    serp_flow.add_edge("extract_competitor", "scrape_flow")

    END FLOW
    serp_flow.add_edge("serp_backlinks", END)
    serp_flow.add_edge("scrape_flow", END)
    # serp_flow.add_edge("fetch_serp", END)

    logger.info("SERP flow graph initialization complete")

    logger.info("Compile the flow")
    app = serp_flow.compile()
    return app