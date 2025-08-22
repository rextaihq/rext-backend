from langchain_community.document_transformers import LongContextReorder
from src.states.State import AgentState

def reordering_doc(state: AgentState):
    try:
        print("=" * 50)
        print("[ReOrderingDocument] Starting document reordering...")

        context = state.get("blog_context", [])
        print(f"[ReOrderingDocument] Received {len(context)} documents")

        if not context:
            print("[ReOrderingDocument] No documents found in context!")
            return {"context": []}

        reordering = LongContextReorder()
        print("[ReOrderingDocument] Applying LongContextReorder...")

        reordered_docs = reordering.transform_documents(context)

        print(f"[ReOrderingDocument] Reordering complete. {len(reordered_docs)} documents returned.")

        # Preview reordered docs
        for i, doc in enumerate(reordered_docs, start=1):
            snippet = getattr(doc, "page_content", str(doc))[:80].replace("\n", " ")
            print(f"  - Reordered Doc {i}: {snippet}...")

        print("[ReOrderingDocument] Finished ✅")
        print("=" * 50)

        return {"context": reordered_docs}

    except Exception as e:
        print("[ReOrderingDocument] ERROR:", str(e))
        return {"context": []}