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
    1. Generate topic -> content type -> outline -> review outline
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
    from src.flow.engines.content.generation.content_type import content_type
    from src.flow.engines.content.generation.humanize_content import humanize_content
    from src.flow.engines.content.generation.outline import generate_outline
    from src.flow.engines.content.generation.persist_content import persist_content
    from src.flow.engines.content.generation.repair_content import repair_content
    from src.flow.engines.content.generation.topic_generation import topic_generation
    from src.flow.engines.content.generation.validation import (
        final_validate_content,
        validate_content,
    )
    from src.flow.engines.content.review.content.content_review import review_content
    from src.flow.engines.content.review.outline import review_outline
    from src.flow.engines.router.content_quality import validation_router
    from src.flow.engines.router.outline import outline_router
    from src.flow.engines.seo.keyword_clustering import keyword_clustering_node

    graph = StateGraph(REXT)

    graph.add_node("topic_generation", topic_generation)
    graph.add_node("content_type", content_type)
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

    graph.add_edge(START, "content_type")
    graph.add_edge("content_type", "topic_generation")
    graph.add_edge("topic_generation", "keyword_clustering")
    graph.add_edge("keyword_clustering", "map_keyword_clusters")
    graph.add_edge("map_keyword_clusters", "generate_outline")
    graph.add_edge("generate_outline", "review_outline")

    graph.add_conditional_edges(
        "review_outline",
        outline_router,
        {"generate_content": "generate_content", "generate_outline": "generate_outline"},
    )

    graph.add_edge("generate_content", "validate_content")
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
