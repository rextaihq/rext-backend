import logging
from langgraph.graph import StateGraph, START, END
from src.flow.states.rext import REXT

def create_content_engine():
    """
    Create the content generation engine workflow.
    
    Simplified flow:
    1. Generate topic → content type → outline → review outline
    2. Generate content → inject E-E-A-T → humanize
    3. Review content (SEO scoring + readability)
    """
    from src.flow.engines.content.generation.topic_generation import topic_generation
    from src.flow.engines.content.generation.content_type import content_type
    from src.flow.engines.content.generation.outline import generate_outline
    from src.flow.engines.content.generation.content_generation import generate_content
    from src.flow.engines.content.generation.humanization import humanize_content
    from src.flow.engines.content.review.outline import review_outline
    from src.flow.engines.content.review.content.content_review import review_content
    from src.flow.engines.router.outline import outline_router

    graph = StateGraph(REXT)

    # Add nodes
    graph.add_node("topic_generation", topic_generation)
    graph.add_node("content_type", content_type)
    graph.add_node("generate_outline", generate_outline)
    graph.add_node("review_outline", review_outline)
    graph.add_node("generate_content", generate_content)
    graph.add_node("humanize_content", humanize_content)
    graph.add_node("review_content", review_content())

    # Add edges
    graph.add_edge(START, "topic_generation")
    graph.add_edge("topic_generation", "content_type")
    graph.add_edge("content_type", "generate_outline")
    graph.add_edge("generate_outline", "review_outline")

    # Conditional: loop back if outline needs revision
    graph.add_conditional_edges(
        "review_outline",
        outline_router,
        {
            "generate_content": "generate_content",
            "generate_outline": "generate_outline"
        }
    )

    # Direct: generate_content → review_content (eeat + humanize disabled)

    graph.add_edge("generate_content", "humanize_content")
    graph.add_edge("humanize_content", "review_content")
    # Review then end (saving is handled by service after workflow completion)
    graph.add_edge("review_content", END)
    
    # Compile the graph
    app = graph.compile()

    return app