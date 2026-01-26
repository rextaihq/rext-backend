from typing import Dict, Any
from langchain_core.documents import Document
from src.flow.states.wrext import WREXT
from src.flow.store.postgress_store import create_long_term_store


async def store_scraped_chunks(state: WREXT) -> Dict[str, Any]:
    """
    Async store scraped document chunks into LangGraph Postgres memory
    with user + workspace isolation.

    Each Document chunk is stored as a JSON-serializable dict:
        {
            "text": chunk.page_content,
            "metadata": chunk.metadata
        }
    """
    scrape_context = state.get("scrape_context", {})
    documents = scrape_context.get("documents", [])

    user_id = state.get("serp_payload", {}).get("user_id")
    workspace_id = state.get("serp_payload", {}).get("workspace_id")

    if not user_id or not workspace_id:
        raise ValueError("user_id and workspace_id are required for storage")

    stored_chunks = 0

    # Async store
    async with create_long_term_store() as store:
        # Optional setup (if LangGraph version requires it)
        await store.setup()

        for item in documents:
            chunks: list[Document] = item.get("chunks", [])
            for chunk in chunks:
                url = chunk.metadata.get("url", "unknown_url")
                chunk_index = chunk.metadata.get("chunk_index", 0)

                await store.aput(
                    namespace=("scraped_chunks", user_id, workspace_id),
                    key=f"{url}::chunk::{chunk_index}",
                    value={
                        "text": chunk.page_content,
                        "metadata": chunk.metadata,
                    },
                )
                stored_chunks += 1

    return {
        **state,
        "storage_context": {
            "stored_chunks": stored_chunks
        }
    }
