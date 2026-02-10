import logging
from src.flow.states.rext import REXT
from langgraph.graph import StateGraph, START, END

def review_content():
    from src.flow.engines.content.review.content.readability import calculate_readability
    from src.flow.engines.content.review.content.on_page_scoring import calculate_on_page_seo
    from src.flow.engines.content.review.content.eeat_trust import calculate_eeat_trust
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
