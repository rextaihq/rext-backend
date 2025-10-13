from perplexity import Perplexity
from langchain_core.documents import Document
from src.flow.states.content_state import ContentState
from src.flow.utils.progress_helper import update_node_progress
from langsmith import traceable,trace
from dotenv import load_dotenv
import os

load_dotenv()

@traceable(
    run_type="retriever",
    name="Web Context Retrieval",
    metadata={
        "description": "Fetches contextual documents from the web using Perplexity API.",
        "inputs": ["topics", "primaryKeywords"],
        "outputs": ["context", "urls"],
        "source": "Perplexity API",
    },
    tags=["Perplexity", "WebSearch", "ContextGeneration"],
    project_name="WREXT",
)
def web_context(state: ContentState):
    """
    Fetch supporting context from the web using Perplexity.
    Uses the same query-building logic as fetch_knowledge_context.
    """
    node_name = "get_web_context"
    print(f"\n🌐 [{node_name}] Starting...")

    payload = state.get("request_payload", {})

    # Update progress (30%)
    content_id = payload.get("content_id")
    if content_id:
        update_node_progress(content_id, "gathering_web_context")

    # ✅ get title from topics in state
    topics = state.get("topics", [])
    print(f"📝 Topics in state: {len(topics)} found")
    title = topics[0]["title"] if topics else ""
    if len(title)==0:
        title = state.get("title")
    print(f"🏷️ Using title: '{title}'")

    # Build query → combine title + keywords
    # Keywords are in seo_data.content_primary_keywords
    primary_keywords = payload.get("seo_data", {}).get("content_primary_keywords", [])
    keywords = " ".join(primary_keywords) if primary_keywords else ""
    print(f"🔑 Primary keywords: {keywords}")
    query = f"{title} {keywords}".strip() or "general context"
    print(f"🔍 Final query string: '{query}'")

    # -----------------------------
    # Run Perplexity Search
    # -----------------------------
    try:
        print("🌐 Running Perplexity web search...")
        api_key = os.getenv("PERPLEXITY_API_KEY")
        if not api_key:
            error_msg = "Missing PERPLEXITY_API_KEY in environment"
            print(f"⚠️ {error_msg}")
            return {
                "context": [],
                "urls": [],
                "error": [{"node": node_name, "message": error_msg}]
            }

        client = Perplexity(api_key=api_key)

        # Run search
        search = client.search.create(
            query=query,
            max_results=5,
        )# ✅ Create sub-trace for the model call
        with trace(
            name="Perplexity Search",
            run_type="llm",  # or "api_call"
            metadata={"query": query},
        ) as span:
            search = client.search.create(query=query, max_results=5)
            span.end(outputs={"results": len(search.results)})

        # ✅ Access results as objects
        web_results = getattr(search, "results", []) or []
        print(f"🌍 Retrieved {len(web_results)} web results")

        if not web_results:
            error_msg = "No web results returned from Perplexity"
            print(f"⚠️ {error_msg}")
            return {
                "context": [],
                "urls": [],
                "error": [{"node": node_name, "message": error_msg}]
            }

        # Preview first 3 results
        for i, res in enumerate(web_results[:3], start=1):
            print(f"   ➡️ Web {i}: {res.title}")

        # Convert to LangChain Documents
        web_docs = [
            Document(
                page_content=res.snippet or "",
                metadata={
                    "title": res.title,
                    "url": res.url,
                },
            )
            for res in web_results
            if res.snippet
        ]

        return {
            "context": web_docs,
            "urls": [res.url for res in web_results if res.url],
        }

    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        print(f"❌ {error_msg}")
        return {
            "context": [],
            "urls": [],
            "error": [{"node": node_name, "message": error_msg}]
        }
