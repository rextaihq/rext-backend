from langgraph.graph import END, START, StateGraph

from src.flow.states.rext import REXT


def review_content():
    """Create the content review subgraph.

    Builds a parallel LangGraph subgraph that runs readability
    calculation, on-page SEO scoring, and E-E-A-T trust scoring
    concurrently on the final content.

    Returns:
        CompiledStateGraph: Compiled review subgraph ready to be
        used as a node in the content engine.
    """
    from src.flow.engines.content.review.content.eeat_trust import calculate_eeat_trust
    from src.flow.engines.content.review.content.on_page_scoring import calculate_on_page_seo
    from src.flow.engines.content.review.content.readability import calculate_readability

    graph = StateGraph(REXT)

    # add nodes
    graph.add_node("calculate_readability", calculate_readability)
    graph.add_node("calculate_on_page_seo", calculate_on_page_seo)
    graph.add_node("calculate_eeat_trust", calculate_eeat_trust)

    # add edges
    graph.add_edge(START, "calculate_readability")
    graph.add_edge(START, "calculate_on_page_seo")
    graph.add_edge(START, "calculate_eeat_trust")
    graph.add_edge("calculate_readability", END)
    graph.add_edge("calculate_on_page_seo", END)
    graph.add_edge("calculate_eeat_trust", END)

    # compile the graph
    app = graph.compile()

    return app
