import logging
from src.flow.states.wrext import WREXT
from src.flow.engines.content.review.content.readability import calculate_readability
from langgraph.graph import StateGraph, START, END

def review_content():
    graph = StateGraph(WREXT)
    
    # add nodes 
    graph.add_node("calculate_readability", calculate_readability)
    # add edges
    graph.add_edge(START, "calculate_readability")
    graph.add_edge("calculate_readability", END)

    # compile the graph
    app = graph.compile()

    return app
