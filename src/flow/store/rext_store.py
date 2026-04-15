from langgraph.store.postgres.aio import AsyncPostgresStore
from langchain.embeddings import init_embeddings, Embeddings
from langgraph.store.base import IndexConfig
from typing import cast, Optional
import contextlib
import os
import sys
import traceback


DB_URI = os.getenv("POSTGRES_URI_CUSTOM")

# Singleton set by generate_store() when LangGraph Platform enters its context.
# FastAPI routes should call get_store() to obtain this reference.
_store_instance: Optional[AsyncPostgresStore] = None


def get_store() -> AsyncPostgresStore:
    """Return the store singleton initialized by LangGraph at startup.

    Raises RuntimeError if called before LangGraph has entered the
    generate_store() context (i.e., before the server is ready).
    """
    if _store_instance is None:
        raise RuntimeError(
            "LangGraph store has not been initialized. "
            "Ensure the server has fully started before making store calls."
        )
    return _store_instance


@contextlib.asynccontextmanager
async def generate_store():
    """LangGraph store factory — referenced in langgraph.json as store.path.

    LangGraph Platform calls this once at server startup and holds the context
    open for the lifetime of the process.  The yielded store is injected into
    graph nodes by LangGraph; FastAPI routes access it via get_store().

    Do NOT call this from HTTP route handlers — use get_store() instead.
    Scripts and migrations may use it directly (see scripts/db.py).
    """
    global _store_instance

    embeddings = cast(Embeddings, init_embeddings("openai:text-embedding-3-small"))

    uri = DB_URI
    if uri:
        for prefix in ("postgresql+asyncpg://", "postgresql+psycopg://", "postgresql+psycopg2://"):
            if uri.startswith(prefix):
                uri = uri.replace(prefix, "postgresql://", 1)
                break

    print(
        f"DEBUG: Initializing LangGraph Store with URI: {uri.split('@')[-1] if uri else None}",
        file=sys.stderr,
    )

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
            _store_instance = store
            try:
                yield store
            finally:
                _store_instance = None
    except Exception as e:
        print(f"ERROR: Failed to initialize store provider: {e}", file=sys.stderr)
        traceback.print_exc()
        raise
