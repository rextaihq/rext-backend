import logging
from langgraph.graph import StateGraph, START, END
from src.flow.states.wrext import WREXT
from src.flow.engines.content.generation.topic_generation import topic_generation
from src.flow.engines.content.generation.outline import generate_outline
from src.flow.engines.content.generation.content_generation import generate_content
from src.flow.engines.content.generation.eeat_injection import inject_eeat
from src.flow.engines.content.generation.humanize_content import humanize_content
from src.flow.engines.content.review.outline import review_outline
from src.flow.engines.content.review.content.content_review import review_content
from src.flow.engines.router.outline import outline_router

def create_content_engine():
    graph = StateGraph(WREXT)

    # add nodes
    graph.add_node("topic_generation", topic_generation)
    graph.add_node("generate_outline", generate_outline)
    graph.add_node("review_outline", review_outline)
    graph.add_node("generate_content", generate_content)
    graph.add_node("inject_eeat", inject_eeat)
    graph.add_node("humanize_content", humanize_content)
    graph.add_node("review_content", review_content())

    # add edges
    graph.add_edge(START, "topic_generation")
    graph.add_edge("topic_generation", "generate_outline")
    graph.add_edge("generate_outline", "review_outline")
    graph.add_conditional_edges(
        "review_outline",
        outline_router,
        {
            "generate_content": "generate_content",
            "generate_outline": "generate_outline" 
        }
    )
    # Three-step content flow: generate → E-E-A-T → humanize → review
    graph.add_edge("generate_content", "inject_eeat")
    graph.add_edge("inject_eeat", "humanize_content")
    graph.add_edge("humanize_content", "review_content")
    graph.add_edge("review_content", END)

    
    # compile the graph
    app = graph.compile()

    return app