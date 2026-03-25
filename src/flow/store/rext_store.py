from langgraph.store.postgres.aio import AsyncPostgresStore
from src.utils.embedding import get_embedding
from langchain.embeddings import init_embeddings, Embeddings
from langgraph.store.base import IndexConfig
from typing import cast
import contextlib
import os
import sys
import traceback


DB_URI = os.getenv("POSTGRES_URI_CUSTOM")

# Initialize embeddings once at startup
embeddings = cast(Embeddings, init_embeddings("openai:text-embedding-3-small"))

@contextlib.asynccontextmanager
async def generate_store():
    """Yield a BaseStore, open for the duration of the server.
    
    AsyncPostgresStore uses psycopg3 (NOT asyncpg) under the hood.
    It requires a plain postgresql:// URI — NOT postgresql+asyncpg://.
    Strip any driver prefix so psycopg can parse it correctly.
    """
    uri = DB_URI
    
    # AsyncPostgresStore.from_conn_string uses psycopg3 which does NOT accept
    # SQLAlchemy-style driver prefixes like +asyncpg or +psycopg.
    # Strip the driver suffix to get a plain postgresql:// URI.
    if uri:
        for prefix in ("postgresql+asyncpg://", "postgresql+psycopg://", "postgresql+psycopg2://"):
            if uri.startswith(prefix):
                uri = uri.replace(prefix, "postgresql://", 1)
                break

    print(f"DEBUG: Initializing LangGraph Store with URI: {uri.split('@')[-1] if uri else None}", file=sys.stderr)
    
    try:
        async with AsyncPostgresStore.from_conn_string(
            uri,
            index=IndexConfig(
                dims=1536,
                embed=embeddings,
                fields=[],
            ),
        ) as store:
            await store.setup()
            print("DEBUG: LangGraph Store setup complete.", file=sys.stderr)
            yield store
    except Exception as e:
        print(f"ERROR: Failed to initialize store provider: {e}", file=sys.stderr)
        traceback.print_exc()
        raise