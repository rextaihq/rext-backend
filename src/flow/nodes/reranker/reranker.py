from typing import Dict, List
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from src.flow.states.content_state import ContentState
from src.utils.helper import get_compressor
from src.flow.utils.progress_helper import update_node_progress
from langsmith import traceable, trace


@traceable(
    run_type="chain",
    name="Document Reranking",
    metadata={
        "description": "Reranks retrieved documents based on query relevance using CohereRerank.",
        "inputs": ["topics", "primaryKeywords", "context"],
        "outputs": ["relavant_context"],
        "dependencies": ["CohereRerank", "RecursiveCharacterTextSplitter"],
    },
    tags=["Reranking", "Cohere", "ContextRefinement"],
    project_name="WREXT"
)
def rerank_documents(state: ContentState) -> Dict[str, List[Document]]:
    """
    Rerank documents from context based on relevance to the query using CohereRerank.
    Returns a dictionary update for the state, including error handling.
    """
    node_name = "rerank_documents"
    print(f"\n⚖️ [{node_name}] Starting...")

    try:
        payload = state.get("request_payload", {})

        # Update progress (60%)
        content_id = payload.get("content_id")
        if content_id:
            update_node_progress(content_id, "reranking_documents")

        # ✅ get title from topics in state
        topics = state.get("topics", [])
        print(f"📝 Topics in state: {len(topics)} found")
        title = topics[0]["title"] if topics else ""
        print(f"🏷️ Using title: '{title}'")

        # Build query → combine title + keywords
        # Keywords are in seo_data.content_primary_keywords
        primary_keywords = payload.get("seo_data", {}).get("content_primary_keywords", [])
        keywords = " ".join(primary_keywords) if primary_keywords else ""
        print(f"🔑 Primary keywords: {keywords}")
        query = f"{title} {keywords}".strip() or "general context"
        print(f"🔍 Final query string: '{query}'")

        # ✅ Get documents from state
        docs = state.get("context", [])
        if not docs:
            error_msg = "No documents found in state['context'] for reranking"
            print(f"⚠️ {error_msg}")
            return {"relavant_context": [], "error": [{"node": node_name, "message": error_msg}]}

        # -----------------------------
        # 3️⃣ Text splitting
        # -----------------------------
        with trace(name="Text Chunking", run_type="data_processing") as chunk_trace:
            text_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200)
            texts = text_splitter.split_documents(docs)
            chunk_trace.end(outputs={"num_chunks": len(texts)})


        if not texts:
            error_msg = "No text chunks produced from context documents"
            print(f"⚠️ {error_msg}")
            return {"relavant_context": [], "error": [{"node": node_name, "message": error_msg}]}

        print("📑 Total chunks:", len(texts))

        with trace(
            name="Cohere Rerank",
            run_type="reranker",
            metadata={"model": "CohereRerank"},
        ) as rerank_trace:
            compressor = get_compressor()
            ranked_docs = compressor.compress_documents(
                query=query,
                documents=texts
            )
            rerank_trace.end(outputs={"num_ranked_docs": len(ranked_docs)})


        # Rerank with Cohere
        ranked_docs = compressor.compress_documents(
            query=query,
            documents=texts
        )

        if not ranked_docs:
            error_msg = "CohereRerank returned no results"
            print(f"⚠️ {error_msg}")
            return {"relavant_context": [], "error": [{"node": node_name, "message": error_msg}]}

        # Number of docs to return = half the reranked docs (rounded up)
        half = max(1, len(ranked_docs) // 2)

        print("✅ Total Reranked Docs:", len(ranked_docs))
        return {"relavant_context": ranked_docs[:half]}

    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        print(f"❌ {error_msg}")
        return {"relavant_context": [], "error": [{"node": node_name, "message": error_msg}]}