import os
from contextlib import asynccontextmanager
from langgraph.store.postgres import AsyncPostgresStore
from src.utils.embedding import get_embedding

# Ensure this is set in your .env
DB_URI = os.getenv("POSTGRES_URI_CUSTOM")

def _create_store() -> AsyncPostgresStore:
    """Creates the store instance with OpenAI semantic indexing."""
    embeddings = get_embedding()
    
    async def embed_texts(texts: list[str]) -> list[list[float]]:
        # Required for semantic search to work
        return await embeddings.aembed_documents(texts)

    return AsyncPostgresStore.from_conn_string(
        DB_URI,
        index={
            "dims": 1536,          # Matches text-embedding-3-small
            "embed": embed_texts,
            "fields": ["text"]      # Vectorize the 'text' key only
        }
    )

@asynccontextmanager
async def get_rext_store():
    """Async context manager to safely use the store connection pool."""
    async with _create_store() as store:
        yield store

async def setup_rext_store():
    """Run this once at app startup to create tables and pgvector extension."""
    async with _create_store() as store:
        await store.setup()