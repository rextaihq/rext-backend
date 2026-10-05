import logging

from langgraph.graph import END, START, StateGraph

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
    from src.flow.engines.serp.competitor import extract_competitors_from_serp
    from src.flow.engines.serp.fetch_serp import fetch_serp_results
    from src.flow.engines.serp.normalization import has_organic_results, normalize_serp_results

    serp_flow = StateGraph(REXT)

    # Add nodes
    serp_flow.add_node("fetch_serp", fetch_serp_results)
    serp_flow.add_node("normalize_serp", normalize_serp_results)
    serp_flow.add_node("extract_competitor", extract_competitors_from_serp)

    # Add edges
    serp_flow.add_edge(START, "fetch_serp")
    serp_flow.add_edge("fetch_serp", "normalize_serp")
    # With no organic result there are no competitors to analyse, and the main
    # graph ends the run; skip the model call that would be thrown away.
    serp_flow.add_conditional_edges(
        "normalize_serp",
        has_organic_results,
        {True: "extract_competitor", False: END},
    )
    serp_flow.add_edge("extract_competitor", END)

    logger.info("Compile the flow")
    app = serp_flow.compile()
    return app
