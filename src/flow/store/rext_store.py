import asyncio
import contextlib
import os
import sys
import traceback
from typing import cast
from urllib.parse import urlsplit

from dotenv import load_dotenv
from langchain.embeddings import Embeddings, init_embeddings
from langgraph.store.base import IndexConfig
from langgraph.store.memory import InMemoryStore
from langgraph.store.postgres.aio import AsyncPostgresStore


load_dotenv()

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def _normalize_postgres_uri(uri: str | None) -> str | None:
    """Return a psycopg-compatible postgres URI."""
    if not uri:
        return None
    for prefix in (
        "postgresql+asyncpg://",
        "postgresql+psycopg://",
        "postgresql+psycopg2://",
    ):
        if uri.startswith(prefix):
            return uri.replace(prefix, "postgresql://", 1)
    return uri


def _store_uri_for_logs(uri: str | None) -> str:
    """Log-safe connection target (no credentials)."""
    if not uri:
        return "None"
    parsed = urlsplit(uri)
    if not parsed.scheme:
        return "invalid-uri"
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    db = parsed.path.lstrip("/") or "postgres"
    return f"{host}:{port}/{db}"


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _allow_fallback_to_in_memory() -> bool:
    """Enable fallback by default in local/dev to avoid hard startup failures."""
    env = os.getenv("ENVIRONMENT", "development").strip().lower()
    default = env in {"development", "dev", "local", "test"}
    return _env_bool("STORE_FALLBACK_TO_INMEM", default=default)


@contextlib.asynccontextmanager
async def generate_store():
    """Yield a LangGraph store with optional local fallback."""
    embeddings = cast(Embeddings, init_embeddings("openai:text-embedding-3-small"))
    index = IndexConfig(dims=1536, embed=embeddings, fields=[])

    raw_uri = os.getenv("LANGGRAPH_STORE_URI") or os.getenv("POSTGRES_URI_CUSTOM")
    uri = _normalize_postgres_uri(raw_uri)
    target = _store_uri_for_logs(uri)

    if not uri:
        if _allow_fallback_to_in_memory():
            print(
                "WARNING: No store URI configured. Falling back to in-memory store.",
                file=sys.stderr,
            )
            yield InMemoryStore(index=index)
            return
        raise RuntimeError(
            "POSTGRES_URI_CUSTOM (or LANGGRAPH_STORE_URI) is required for store startup."
        )

    print(f"DEBUG: Initializing LangGraph Store with URI: {target}", file=sys.stderr)

    try:
        async with AsyncPostgresStore.from_conn_string(uri, index=index) as store:
            await store.setup()
            print("DEBUG: LangGraph Store setup complete.", file=sys.stderr)
            yield store
            return
    except Exception as exc:
        print(f"ERROR: Failed to initialize store provider at {target}: {exc}", file=sys.stderr)
        traceback.print_exc()
        if not _allow_fallback_to_in_memory():
            raise
        print(
            "WARNING: Falling back to in-memory LangGraph store. "
            "Set STORE_FALLBACK_TO_INMEM=false to disable this behavior.",
            file=sys.stderr,
        )

    yield InMemoryStore(index=index)
