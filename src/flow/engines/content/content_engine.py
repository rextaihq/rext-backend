import logging
from langgraph.graph import StateGraph, START, END
from src.flow.states.wrext import WREXT
from src.flow.engines.content.generation.topic_generation import topic_generation
from src.flow.engines.content.generation.content_type import content_type
from src.flow.engines.content.generation.outline import generate_outline
from src.flow.engines.content.generation.content_generation import generate_content
from src.flow.engines.content.generation.eeat_injection import inject_eeat
from src.flow.engines.content.generation.humanize_content import humanize_content
from src.flow.engines.content.review.outline import review_outline
from src.flow.engines.content.review.content.content_review import review_content
from src.flow.engines.content.review.review_action import review_action
from src.flow.engines.content.publish.handle_publish import handle_publish
from src.flow.engines.content.publish.handle_edit import handle_edit
from src.flow.engines.content.publish.handle_save import handle_save
from src.flow.engines.router.outline import outline_router
from src.flow.engines.router.content_action_router import content_action_router

def create_content_engine():
    graph = StateGraph(WREXT)

    # add nodes
    graph.add_node("topic_generation", topic_generation)
    graph.add_node("content_type", content_type)
    graph.add_node("generate_outline", generate_outline)
    graph.add_node("review_outline", review_outline)
    graph.add_node("generate_content", generate_content)
    graph.add_node("inject_eeat", inject_eeat)
    graph.add_node("humanize_content", humanize_content)
    graph.add_node("review_content", review_content())
    
    # Post-review action nodes
    graph.add_node("review_action", review_action)
    graph.add_node("handle_publish", handle_publish)
    graph.add_node("handle_edit", handle_edit)
    graph.add_node("handle_save", handle_save)

    # add edges
    graph.add_edge(START, "topic_generation")
    graph.add_edge("topic_generation", "content_type")
    graph.add_edge("content_type", "generate_outline")
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
    
    # Post-review action flow with user interrupt
    graph.add_edge("review_content", "review_action")
    graph.add_conditional_edges(
        "review_action",
        content_action_router,
        {
            "handle_publish": "handle_publish",
            "handle_edit": "handle_edit",
            "handle_save": "handle_save",
            END: END
        }
    )
    
    # All action handlers lead to END
    graph.add_edge("handle_publish", END)
    graph.add_edge("handle_edit", END)
    graph.add_edge("handle_save", END)

    
    # compile the graph
    app = graph.compile()

    return app