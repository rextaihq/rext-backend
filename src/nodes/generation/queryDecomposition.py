from src.states.State import AgentState
from src.model.model import query_decomposer_model
from src.utils.helper import load_vector_store

def query_decomposition(state: AgentState):
    try:
        print("=" * 50)
        print("[QueryDecomposition] Starting query decomposition...")

        # Get refine_title
        refine_title = state.get("refine_title", "")
        print(f"[QueryDecomposition] refine_title: {refine_title}")

        # if not refine_title:
        #     print("[QueryDecomposition] No refine_title found in state!")
        #     return {"context": []}

        # Generate sub-queries
        print("[QueryDecomposition] Invoking composer_llm...")
        sub_titled_obj = query_decomposer_model().invoke(refine_title)
        sub_title = sub_titled_obj.compose_title
        print(f"[QueryDecomposition] Generated {len(sub_title)} sub-queries")

        sub_query_context = []

        # Retrieve context for each sub-query
        for idx, sub_q in enumerate(sub_title, start=1):
            print(f"[QueryDecomposition] Processing sub-query {idx}: {sub_q}")
            context = load_vector_store().similarity_search(sub_q, k=5)
            print(f"[QueryDecomposition] Retrieved {len(context)} docs for sub-query {idx}")

            for j, doc in enumerate(context, start=1):
                snippet = getattr(doc, "page_content", str(doc))[:80].replace("\n", " ")
                print(f"   - Doc {j}: {snippet}...")

            sub_query_context.extend(context)

        print(f"[QueryDecomposition] Total docs collected: {len(sub_query_context)}")
        print("[QueryDecomposition] Decomposition complete ✅")
        print("=" * 50)

        return{
            "blog_context": [{
                "refine_title": refine_title,
                "docs": sub_query_context
            }]
        }
    except Exception as e:
        print("[QueryDecomposition] ERROR:", str(e))
        return {"blog_context": []}