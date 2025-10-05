from src.states.State import AgentState
from src.utils.helper import load_vector_store

from src.api.lib.logger import auto_logger

logger = auto_logger()

def get_relevnt_doc(state: AgentState) -> AgentState:
    try:
        refine_title = state.get("refine_title", "")
        logger.info("=" * 50)
        logger.info(f"[GetRelevantDoc] Starting retrieval...")
        logger.info(f"[GetRelevantDoc] refine_title: {refine_title}")

        # if not refine_title:
        #     print("[GetRelevantDoc] No refine_title found in state!")
        #     return {"context": []}

        results = load_vector_store().similarity_search(refine_title, k=5)

        logger.info(f"[GetRelevantDoc] Retrieved {len(results)} documents")
        for i, doc in enumerate(results, start=1):
            snippet = doc.page_content[:80].replace("\n", " ")  # preview first 80 chars
            logger.info(f"  - Doc {i}: {snippet}...")

        logger.info("[GetRelevantDoc] Retrieval complete ✅")
        logger.info("=" * 50)

        return {
            "blog_context": [{
                "refine_title": refine_title,
                "docs": results
            }]
        }

    except Exception as e:
        logger.info("[GetRelevantDoc] ERROR:", str(e))
        return {"blog_context": []}