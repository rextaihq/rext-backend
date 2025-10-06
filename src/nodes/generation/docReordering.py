from langchain_community.document_transformers import LongContextReorder
from src.states.State import AgentState

from src.api.lib.logger import auto_logger

logger = auto_logger()

def reordering_doc(state: AgentState):
    try:
        logger.info("=" * 50)
        logger.info("[ReOrderingDocument] Starting document reordering...")

        context = state.get("blog_context", [])
        logger.info(f"[ReOrderingDocument] Received {len(context)} documents")

        if not context:
            logger.info("[ReOrderingDocument] No documents found in context!")
            return {"context": []}

        reordering = LongContextReorder()
        logger.info("[ReOrderingDocument] Applying LongContextReorder...")

        reordered_docs = reordering.transform_documents(context)

        logger.info(f"[ReOrderingDocument] Reordering complete. {len(reordered_docs)} documents returned.")

        # Preview reordered docs
        for i, doc in enumerate(reordered_docs, start=1):
            snippet = getattr(doc, "page_content", str(doc))[:80].replace("\n", " ")
            logger.info(f"  - Reordered Doc {i}: {snippet}...")

        logger.info("[ReOrderingDocument] Finished ✅")
        logger.info("=" * 50)

        return {"blog_context": reordered_docs}

    except Exception as e:
        logger.info("[ReOrderingDocument] ERROR:", str(e))
        return {"blog_context": []}