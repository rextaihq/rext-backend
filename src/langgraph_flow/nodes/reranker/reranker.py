from typing import Dict, List
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from src.langgraph_flow.states.content_state import ContentState
from src.utils.helper import get_compressor

def rerank_documents(state: ContentState) -> Dict[str, List[Document]]:
    """
    Rerank documents from context based on relevance to the query using CohereRerank.
    Returns a dictionary update for the state, including error handling.
    """
    node_name = "rerank_documents"
    print(f"\n⚖️ [{node_name}] Starting...")

    try:
        payload = state.get("request_payload", {})

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

        # ✅ Get documents from state
        docs = state.get("context", [])
        if not docs:
            error_msg = "No documents found in state['context'] for reranking"
            print(f"⚠️ {error_msg}")
            return {"relavant_context": [], "error": [{"node": node_name, "message": error_msg}]}

        # Split into smaller chunks
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200)
        texts = text_splitter.split_documents(docs)

        if not texts:
            error_msg = "No text chunks produced from context documents"
            print(f"⚠️ {error_msg}")
            return {"relavant_context": [], "error": [{"node": node_name, "message": error_msg}]}

        print("📑 Total chunks:", len(texts))

        compressor = get_compressor()

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