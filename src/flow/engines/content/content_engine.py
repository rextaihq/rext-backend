from langgraph.graph import END, START, StateGraph

from src.flow.states.rext import REXT


def create_content_engine():
    """
    Create the content generation engine workflow.

    Simplified flow:
    1. Generate topic → content type → outline → review outline
    2. Generate content → inject E-E-A-T → humanize
    3. Review content (SEO scoring + readability)

    Credits are deducted inline inside each node function — no wrapper nodes.
    """
    from src.flow.engines.content.generation.cluster_mapping import map_keyword_clusters
    from src.flow.engines.content.generation.content_generation import generate_content
    from src.flow.engines.content.generation.content_type import content_type
    from src.flow.engines.content.generation.outline import generate_outline
    from src.flow.engines.content.generation.persist_content import persist_content
    from src.flow.engines.content.generation.topic_generation import topic_generation
    from src.flow.engines.content.review.content.content_review import review_content
    from src.flow.engines.content.review.outline import review_outline
    from src.flow.engines.router.outline import outline_router
    from src.flow.engines.seo.keyword_clustering import keyword_clustering_node

    graph = StateGraph(REXT)

    graph.add_node("topic_generation", topic_generation)
    graph.add_node("content_type", content_type)
    graph.add_node("keyword_clustering", keyword_clustering_node)
    graph.add_node("map_keyword_clusters", map_keyword_clusters)
    graph.add_node("generate_outline", generate_outline)
    graph.add_node("review_outline", review_outline)
    graph.add_node("generate_content", generate_content)
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
        {
            "generate_content": "generate_content",
            "generate_outline": "generate_outline"
        }
    )

    graph.add_edge("generate_content", "review_content")
    graph.add_edge("review_content", "persist_content")
    graph.add_edge("persist_content", END)

    return graph.compile()
