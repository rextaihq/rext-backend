from src.langgraph_flow.states.content_state import ContentState
from src.utils.vector_store import load_vector_store
from langsmith import traceable, trace


@traceable(
    run_type="retriever",
    name="Workspace Knowledge Context",
    metadata={
        "description": "Fetches relevant context from the FAISS vector store for a specific workspace.",
        "inputs": ["workspace_id", "topics", "primaryKeywords"],
        "outputs": ["context", "urls"],
        "source": "FAISS Vector Store",
    },
    tags=["FAISS", "ContextRetrieval", "KnowledgeBase"],
    project_name="WREXT"
)
def workspace_context(state: ContentState):
    node_name = "fetch_knowledge_context"
    print(f"\n🚀 [{node_name}] Starting...")

    payload = state.get("request_payload", {})
    workspace_id = payload.get("workspace_id")

    print(f"🔎 Payload keys: {list(payload.keys())}")
    print(f"📌 workspace_id={workspace_id}")

    if not workspace_id:
        error_msg = "Missing required field: workspace_id"
        print(f"⚠️ {error_msg}")
        return {
            "context": [],
            "urls": [],
            "error": [{"node": node_name, "message": error_msg}]
        }

    try:
        print("📂 Loading FAISS vector store...")
        vector_store = load_vector_store()
        print("✅ Vector store loaded successfully")

        # ✅ get title from topics in state
        topics = state.get("topics", [])
        print(f"📝 Topics in state: {len(topics)} found")
        title = topics[0]["title"] if topics else ""
        print(f"🏷️ Using title: '{title}'")

        # Build query → combine title + keywords
        keywords = " ".join(payload.get("primaryKeywords", []))
        print(f"🔑 Primary keywords: {keywords}")
        query = f"{title} {keywords}".strip() or "general context"
        print(f"🔍 Final query string: '{query}'")

        # Run FAISS similarity search inside a sub-trace
        with trace(
            name="FAISS Similarity Search",
            run_type="retriever",
            metadata={
                "query": query,
                "workspace_id": workspace_id,
            },
        ) as span:
            print("🔎 Running FAISS similarity search...")
            raw_docs = vector_store.similarity_search(
                query=query,
                k=5,
                # filter={"workspace_id": workspace_id}  # Correct filter usage
            )
            span.end(outputs={"num_docs": len(raw_docs)})

        print(f"📚 Retrieved {len(raw_docs)} raw docs")

        for i, doc in enumerate(raw_docs[:3], start=1):  # show first 3 docs
            print(f"   ➡️ Doc {i}: metadata={doc.metadata}")

        return {
            "context": raw_docs,
            "urls": list(set([doc.metadata.get("url", "") for doc in raw_docs if doc.metadata.get("url")])),
        }

    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        print(f"❌ {error_msg}")
        return {
            "context": [],
            "urls": [],
            "error": [{"node": node_name, "message": error_msg}]
        }