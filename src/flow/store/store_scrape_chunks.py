from typing import Dict, Any
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from src.flow.states.rext import REXT
from src.flow.store.rext_store import create_long_term_store

# Chunk config — must match what scrape_content.py used previously
_CHUNK_SIZE = 800
_CHUNK_OVERLAP = 150


def _chunk_document(doc: Document) -> list[Document]:
    """Split a document into overlapping text chunks, preserving metadata."""
    if not doc.page_content:
        return []
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=_CHUNK_SIZE,
        chunk_overlap=_CHUNK_OVERLAP,
    )
    texts = splitter.split_text(doc.page_content)
    total = len(texts)
    return [
        Document(
            page_content=text,
            metadata={**doc.metadata, "chunk_index": idx, "chunk_total": total},
        )
        for idx, text in enumerate(texts)
    ]


async def store_scraped_chunks(state: REXT) -> Dict[str, Any]:
    """
    Async store scraped document chunks into LangGraph Postgres memory
    with user + workspace isolation.

    Chunks are computed here on-the-fly from the Document stored in state.
    We no longer persist chunks in graph state to keep LangSmith payloads small.

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

    async with create_long_term_store() as store:
        await store.setup()

        for item in documents:
            doc: Document = item.get("document")
            if not doc or not doc.page_content:
                continue

            # Re-chunk inline — chunks are no longer stored in graph state
            chunks = _chunk_document(doc)

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
            "stored_chunks": stored_chunks,
        },
    }