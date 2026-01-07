import logging
from langgraph.graph import StateGraph, START, END
from src.flow.states.wrext import WREXT
from src.flow.engines.content.generation.outline import generate_outline
from src.flow.engines.content.generation.content import generate_content
from src.flow.engines.content.review.outline import review_outline
from src.flow.engines.content.review.content.content_review import review_content

def create_content_engine():
    graph = StateGraph(WREXT)

    # add nodes
    graph.add_node("generate_outline", generate_outline)
    graph.add_node("review_outline", review_outline)
    graph.add_node("generate_content", generate_content)
    graph.add_node("review_content", review_content())

    # add edges
    graph.add_edge(START, "generate_outline")
    graph.add_edge("generate_outline", "review_outline")
    graph.add_edge("review_outline", "generate_content")
    graph.add_edge("generate_content", "review_content")
    graph.add_edge("review_content", END)

    # compile the graph
    app = graph.compile()

    return app