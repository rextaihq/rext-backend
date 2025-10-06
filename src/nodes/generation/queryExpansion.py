from src.states.State import AgentState
from src.utils.helper import get_multi_query

from src.api.lib.logger import auto_logger

logger = auto_logger()

# Apply Query Expansion and get results for each query
def query_expansion(state: AgentState):
    try:
        logger.info("=" * 50)
        logger.info("[QueryExpansion] Starting query expansion...")

        refine_title = state.get("refine_title", "")
        logger.info(f"[QueryExpansion] refine_title: {refine_title}")

        # if not refine_title:
        #     print("[QueryExpansion] No refine_title found in state!")
        #     return {"context": []}

        # retriever_from_llm = MultiQueryRetriever.from_llm(
        #     retriever=vector_store.as_retriever(), llm=llm
        # )
        logger.info("[QueryExpansion] Created MultiQueryRetriever ✅")

        context = get_multi_query().invoke(refine_title)
        logger.info(f"[QueryExpansion] Retrieved {len(context)} documents")

        # Show preview of results
        for i, doc in enumerate(context, start=1):
            snippet = getattr(doc, "page_content", str(doc))[:80].replace("\n", " ")
            logger.info(f"  - Expanded Doc {i}: {snippet}...")

        logger.info("[QueryExpansion] Expansion complete ✅")
        logger.info("=" * 50)

        return {
            "blog_context": [{
                "refine_title": refine_title,
                "docs": context
            }]
        }

    except Exception as e:
        logger.info("[QueryExpansion] ERROR:", str(e))
        return {"blog_context": []}