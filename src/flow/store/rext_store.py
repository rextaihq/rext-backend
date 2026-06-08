from langgraph.store.postgres.aio import AsyncPostgresStore
from langchain.embeddings import init_embeddings, Embeddings
from langgraph.store.base import IndexConfig
from typing import cast
import contextlib
import os
import sys
import traceback


DB_URI = os.getenv("POSTGRES_URI_CUSTOM")

_store: AsyncPostgresStore | None = None
_store_cm = None


def _build_uri() -> str:
    uri = DB_URI or ""
    for prefix in ("postgresql+asyncpg://", "postgresql+psycopg://", "postgresql+psycopg2://"):
        if uri.startswith(prefix):
            return uri.replace(prefix, "postgresql://", 1)
    return uri


async def init_store() -> None:
    """Initialize the singleton store at server startup. Call once from lifespan."""
    global _store, _store_cm
    if _store is not None:
        return
    try:
        embeddings = cast(Embeddings, init_embeddings("openai:text-embedding-3-small"))
        uri = _build_uri()
        _store_cm = AsyncPostgresStore.from_conn_string(
            uri,
            index=IndexConfig(dims=1536, embed=embeddings, fields=[]),
        )
        _store = await _store_cm.__aenter__()
        await _store.setup()
        print("DEBUG: LangGraph Store initialized.", file=sys.stderr)
    except Exception as e:
        print(f"ERROR: Failed to initialize store: {e}", file=sys.stderr)
        traceback.print_exc()
        _store = None
        _store_cm = None
        raise


async def close_store() -> None:
    """Close the singleton store at server shutdown."""
    global _store, _store_cm
    if _store_cm is not None:
        try:
            await _store_cm.__aexit__(None, None, None)
        except Exception:
            pass
    _store = None
    _store_cm = None


@contextlib.asynccontextmanager
async def generate_store():
    """Yield the shared store. Falls back to a temporary store for scripts/tests."""
    if _store is not None:
        yield _store
        return

    # Fallback: create a temporary store (scripts, tests, cold starts before init)
    try:
        embeddings = cast(Embeddings, init_embeddings("openai:text-embedding-3-small"))
        uri = _build_uri()
        async with AsyncPostgresStore.from_conn_string(
            uri,
            index=IndexConfig(dims=1536, embed=embeddings, fields=[]),
        ) as store:
            await store.setup()
            yield store
    except Exception as e:
        print(f"ERROR: Failed to initialize store provider: {e}", file=sys.stderr)
        traceback.print_exc()
        raise
