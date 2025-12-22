import logging
from langgraph.graph import StateGraph, START, END
from src.flow.states.wrext import WREXT
from src.flow.engines.serp.fetch_serp import fetch_serp_results
from src.flow.engines.serp.normalization import normalize_serp_results
from src.flow.engines.serp.competitor import extract_competitors_from_serp
from src.flow.engines.scrape.scrape_flow import scrape_flow

logger = logging.getLogger(__name__)

def get_serp_flow() -> StateGraph:
    """
    Initialize and return the SERP processing flow graph.

    The flow consists of:
    1. Fetching SERP results from an external API.
    2. Normalizing the raw results into a structured format.
    3. Extracting competitor information from the results.

    Returns:
        StateGraph: The configured LangGraph StateGraph for the SERP flow.
    """
    logger.info("Initializing SERP flow graph")
    serp_flow = StateGraph(WREXT)

    # Add nodes
    logger.debug("Adding nodes to SERP flow: fetch_serp, normalize_serp, extract_competitor")
    serp_flow.add_node("fetch_serp", fetch_serp_results)
    serp_flow.add_node("normalize_serp", normalize_serp_results)
    serp_flow.add_node("extract_competitor", extract_competitors_from_serp)
    serp_flow.add_node("scrape_flow", scrape_flow())

    # Add edges
    logger.debug("Configuring edges for SERP flow")
    serp_flow.add_edge(START, "fetch_serp") 
    serp_flow.add_edge("fetch_serp", "normalize_serp")
    serp_flow.add_edge("fetch_serp", "extract_competitor")

    # scraping flow
    serp_flow.add_edge("normalize_serp", "scrape_flow")
    serp_flow.add_edge("extract_competitor", "scrape_flow")

    # END FLOW
    serp_flow.add_edge("scrape_flow", END)

    logger.info("SERP flow graph initialization complete")

    logger.info("Compile the flow")
    app = serp_flow.compile()
    return app