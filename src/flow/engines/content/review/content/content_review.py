import logging
from src.flow.states.wrext import WREXT
from src.flow.engines.content.review.content.readability import calculate_readability
from src.flow.engines.content.review.content.on_page_scoring import calculate_on_page_seo
from langgraph.graph import StateGraph, START, END

def review_content():
    graph = StateGraph(WREXT)
    
    # add nodes 
    graph.add_node("calculate_readability", calculate_readability)
    graph.add_node("calculate_on_page_seo", calculate_on_page_seo)
    
    # add edges
    graph.add_edge(START, "calculate_readability")
    graph.add_edge(START, "calculate_on_page_seo")
    graph.add_edge("calculate_readability", END)
    graph.add_edge("calculate_on_page_seo", END)

    # compile the graph
    app = graph.compile()

    return app
