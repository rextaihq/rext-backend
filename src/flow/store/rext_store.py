from langgraph.store.postgres.aio import AsyncPostgresStore
from langgraph.store.postgres.base import PostgresIndexConfig, PoolConfig
from langchain.embeddings import init_embeddings, Embeddings
from typing import Any, cast
import asyncio
import contextlib
import logging
import os

logger = logging.getLogger(__name__)


DB_URI = os.getenv("POSTGRES_URI_CUSTOM")

_store: AsyncPostgresStore | None = None
_store_cm = None


def _build_uri() -> str:
    uri = DB_URI or ""
    for prefix in ("postgresql+asyncpg://", "postgresql+psycopg://", "postgresql+psycopg2://"):
        if uri.startswith(prefix):
            return uri.replace(prefix, "postgresql://", 1)
    return uri


class _MainLoopProxy:
    """Wraps the singleton store and dispatches all async ops to the main loop.

    Allows worker event loops (LangGraph bg-loop-N threads) to use the single
    psycopg pool that lives on the main loop, via run_coroutine_threadsafe —
    same pattern as _bulk_sync_workspace.
    """

    def __init__(self, store: AsyncPostgresStore, main_loop: asyncio.AbstractEventLoop) -> None:
        self._store = store
        self._loop = main_loop

    async def _run(self, coro: Any) -> Any:
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return await asyncio.to_thread(future.result)

    async def aput(self, namespace: tuple, key: str, value: dict, *, index: Any = None, **kw: Any) -> None:
        return await self._run(self._store.aput(namespace, key, value, index=index, **kw))

    async def asearch(self, namespace_prefix: tuple, /, *, query: str | None = None,
                      filter: dict | None = None, limit: int = 10, offset: int = 0, **kw: Any) -> list:
        return await self._run(
            self._store.asearch(namespace_prefix, query=query, filter=filter,
                                limit=limit, offset=offset, **kw)
        )

    async def aget(self, namespace: tuple, key: str, **kw: Any) -> Any:
        return await self._run(self._store.aget(namespace, key, **kw))

    async def adelete(self, namespace: tuple, key: str) -> None:
        return await self._run(self._store.adelete(namespace, key))

    async def alist_namespaces(self, *args: Any, **kwargs: Any) -> Any:
        return await self._run(self._store.alist_namespaces(*args, **kwargs))

    async def setup(self) -> None:
        return await self._run(self._store.setup())

    def __getattr__(self, name: str) -> Any:
        return getattr(self._store, name)


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
            pool_config=PoolConfig(min_size=1, max_size=10),
            index=PostgresIndexConfig(dims=1536, embed=embeddings, fields=[]),
        )
        _store = await _store_cm.__aenter__()
        await _store.setup()
        logger.info("LangGraph Store singleton initialized.")
    except Exception as e:
        logger.error(f"Failed to initialize store: {e}", exc_info=True)
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
    """Yield the singleton store.

    - Main loop: direct access to the real store.
    - Worker loops: _MainLoopProxy that dispatches ops to the main loop pool.
    - Fallback (cold start / scripts / tests): temporary store on the current loop.
    """
    from src.utils import loop_registry
    main_loop = loop_registry.get()
    current_loop = asyncio.get_running_loop()

    if _store is not None and main_loop is not None:
        if current_loop is main_loop:
            yield _store
        else:
            yield _MainLoopProxy(_store, main_loop)
        return

    # Fallback: singleton not ready — create temporary store on current loop
    try:
        embeddings = cast(Embeddings, init_embeddings("openai:text-embedding-3-small"))
        uri = _build_uri()
        async with AsyncPostgresStore.from_conn_string(
            uri,
            pool_config=PoolConfig(min_size=1, max_size=10),
            index=PostgresIndexConfig(dims=1536, embed=embeddings, fields=[]),
        ) as store:
            await store.setup()
            yield store
    except Exception as e:
        logger.error(f"Failed to initialize store provider: {e}", exc_info=True)
        raise
