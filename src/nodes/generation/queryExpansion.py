from src.states.State import AgentState
from src.utils.helper import get_multi_query

# Apply Query Expansion and get results for each query
def query_expansion(state: AgentState):
    try:
        print("=" * 50)
        print("[QueryExpansion] Starting query expansion...")

        refine_title = state.get("refine_title", "")
        print(f"[QueryExpansion] refine_title: {refine_title}")

        # if not refine_title:
        #     print("[QueryExpansion] No refine_title found in state!")
        #     return {"context": []}

        # retriever_from_llm = MultiQueryRetriever.from_llm(
        #     retriever=vector_store.as_retriever(), llm=llm
        # )
        print("[QueryExpansion] Created MultiQueryRetriever ✅")

        context = get_multi_query().invoke(refine_title)
        print(f"[QueryExpansion] Retrieved {len(context)} documents")

        # Show preview of results
        for i, doc in enumerate(context, start=1):
            snippet = getattr(doc, "page_content", str(doc))[:80].replace("\n", " ")
            print(f"  - Expanded Doc {i}: {snippet}...")

        print("[QueryExpansion] Expansion complete ✅")
        print("=" * 50)

        return {
            "blog_context": [{
                "refine_title": refine_title,
                "docs": context
            }]
        }

    except Exception as e:
        print("[QueryExpansion] ERROR:", str(e))
        return {"blog_context": []}