from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from src.flow.states.rext import REXT

# Infrastructure-level retry (transient API/network failures) for nodes that
# make external LLM calls — separate from and in addition to the
# business-logic repair loop below (validate_content <-> repair_content),
# which handles content QUALITY failures, not transient faults.
_LLM_RETRY_POLICY = RetryPolicy(max_attempts=3)


def create_content_engine():
    """
    Create the content generation engine workflow.

    Flow:
    1. Content type -> topic -> outline -> review outline. Each gate's model
       call is a node of its own before the gate (recommend_content_type,
       generate_topics), so the answer that resumes a gate never repeats it
       (rext-control#330).
    2. Generate content
    3. Validate content (deterministic) <-> repair content (targeted LLM fix,
       bounded loop) -- a LangGraph-orchestrated gate the writer agent cannot
       skip or decide to invoke; humanization only runs once this resolves
       (pass, or best-effort give-up).
    4. Humanize -> lightweight final validation (catches humanization
       regressions only, no LLM, no re-running the full check suite)
    5. Review content (SEO scoring + readability + E-E-A-T, unchanged,
       informational-only, as before)

    Credits are deducted inline inside each node function — no wrapper nodes.
    """
    from src.flow.engines.content.generation.cluster_mapping import map_keyword_clusters
    from src.flow.engines.content.generation.content_generation import generate_content
    from src.flow.engines.content.generation.content_type import (
        content_type,
        recommend_content_type,
    )
    from src.flow.engines.content.generation.humanize_content import humanize_content
    from src.flow.engines.content.generation.outline import generate_outline
    from src.flow.engines.content.generation.persist_content import persist_content
    from src.flow.engines.content.generation.repair_content import repair_content
    from src.flow.engines.content.generation.topic_generation import (
        generate_topics,
        topic_gate_router,
        topic_generation,
        topics_failed,
        topics_router,
    )
    from src.flow.engines.content.generation.validation import (
        final_validate_content,
        validate_content,
    )
    from src.flow.engines.content.review.content.content_review import review_content
    from src.flow.engines.content.review.outline import review_outline
    from src.flow.engines.router.content_quality import validation_router
    from src.flow.engines.router.credits import unless_out_of_credits
    from src.flow.engines.router.outline import outline_router
    from src.flow.engines.seo.keyword_clustering import keyword_clustering_node

    graph = StateGraph(REXT)

    graph.add_node("recommend_content_type", recommend_content_type)
    graph.add_node("content_type", content_type)
    graph.add_node("generate_topics", generate_topics)
    graph.add_node("topic_generation", topic_generation)
    graph.add_node("topics_failed", topics_failed)
    graph.add_node("keyword_clustering", keyword_clustering_node)
    graph.add_node("map_keyword_clusters", map_keyword_clusters)
    graph.add_node("generate_outline", generate_outline)
    graph.add_node("review_outline", review_outline)
    graph.add_node("generate_content", generate_content, retry_policy=_LLM_RETRY_POLICY)
    graph.add_node("validate_content", validate_content)
    graph.add_node("repair_content", repair_content, retry_policy=_LLM_RETRY_POLICY)
    graph.add_node("humanize_content", humanize_content, retry_policy=_LLM_RETRY_POLICY)
    graph.add_node("final_validate_content", final_validate_content)
    graph.add_node("review_content", review_content())
    graph.add_node("persist_content", persist_content)

    graph.add_edge(START, "recommend_content_type")
    graph.add_edge("recommend_content_type", "content_type")
    graph.add_edge("content_type", "generate_topics")
    # A topic step with no titles ends the run instead of reaching an empty
    # outline gate (rext-control#359).
    graph.add_conditional_edges(
        "generate_topics",
        topics_router,
        {"topic_generation": "topic_generation", "topics_failed": "topics_failed"},
    )
    graph.add_edge("topics_failed", END)
    # The title gate asks for a new set (back to the model), or goes on.
    graph.add_conditional_edges(
        "topic_generation",
        topic_gate_router,
        {"generate_topics": "generate_topics", "keyword_clustering": "keyword_clustering"},
    )
    graph.add_edge("keyword_clustering", "map_keyword_clusters")
    graph.add_edge("map_keyword_clusters", "generate_outline")
    # A stage whose charge was refused ends the run there: its work isn't handed on,
    # and no later stage runs unpaid (rext-control#524).
    graph.add_conditional_edges(
        "generate_outline",
        unless_out_of_credits("review_outline"),
        {"review_outline": "review_outline", END: END},
    )

    graph.add_conditional_edges(
        "review_outline",
        outline_router,
        {"generate_content": "generate_content", "generate_outline": "generate_outline"},
    )

    graph.add_conditional_edges(
        "generate_content",
        unless_out_of_credits("validate_content"),
        {"validate_content": "validate_content", END: END},
    )
    graph.add_conditional_edges(
        "validate_content",
        validation_router,
        {
            "repair_content": "repair_content",
            "humanize_content": "humanize_content",
        },
    )
    graph.add_edge("repair_content", "validate_content")
    graph.add_edge("humanize_content", "final_validate_content")
    graph.add_edge("final_validate_content", "review_content")
    graph.add_edge("review_content", "persist_content")
    graph.add_edge("persist_content", END)

    return graph.compile()
