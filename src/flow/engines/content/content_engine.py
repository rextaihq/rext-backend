import logging
from langgraph.graph import StateGraph, START, END
from src.flow.states.wrext import WREXT
from src.flow.engines.content.outline import generate_outline
from src.flow.engines.content.review_outline import review_outline

def create_content_engine():
    graph = StateGraph(WREXT)

    # add nodes
    graph.add_node("generate_outline", generate_outline)
    graph.add_node("review_outline", review_outline)

    # add edges
    graph.add_edge(START, "generate_outline")
    graph.add_edge("generate_outline", "review_outline")
    # graph.add_edge("review_outline", END)

    # compile the graph
    app = graph.compile()

    return app