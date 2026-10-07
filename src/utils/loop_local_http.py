"""An httpx client whose connections never cross event loops (G80, rext-control #644).

LangGraph runs each background job on its own event loop (BG_JOB_ISOLATED_LOOPS), while
langchain_openai caches ONE process-wide ``httpx.AsyncClient`` for every chat model. A pooled
connection, and the asyncio locks and events inside the pool, belong to the loop that first used
them, so two runs at once failed with "<asyncio.locks.Event …> is bound to a different event
loop", with "Event loop is closed" once a finished run's loop had gone, or stalled.

``loop_local_async_client`` is one client to share, as before, whose transport keeps a separate
connection pool for each event loop: a run's calls only ever use connections made on its own
loop. A pool goes once its loop has closed.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

import httpx

# As the OpenAI SDK's own default client.
_DEFAULT_LIMITS = httpx.Limits(max_connections=1000, max_keepalive_connections=100)


class _PerLoopTransport(httpx.AsyncBaseTransport):
    """Hands each request to a connection pool of the event loop it runs on."""

    def __init__(self, **transport_kwargs: Any) -> None:
        self._transport_kwargs = transport_kwargs
        # Not a WeakKeyDictionary: a pool's connections hold their loop, so the loop would never be
        # collected. Pools of closed loops are dropped instead.
        self._pools: dict[asyncio.AbstractEventLoop, httpx.AsyncHTTPTransport] = {}
        # Requests on different loops run in different threads.
        self._lock = threading.Lock()

    def _pool(self) -> httpx.AsyncHTTPTransport:
        loop = asyncio.get_running_loop()
        with self._lock:
            for closed in [other for other in self._pools if other.is_closed()]:
                # Its connections can't be closed from here; the sockets go with them.
                del self._pools[closed]
            pool = self._pools.get(loop)
            if pool is None:
                pool = httpx.AsyncHTTPTransport(**self._transport_kwargs)
                self._pools[loop] = pool
            return pool

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return await self._pool().handle_async_request(request)

    async def aclose(self) -> None:
        # Only the calling loop's pool can be closed from here; the others are dropped once their
        # loops have closed.
        with self._lock:
            pool = self._pools.pop(asyncio.get_running_loop(), None)
        if pool is not None:
            await pool.aclose()


def loop_local_async_client(**client_kwargs: Any) -> httpx.AsyncClient:
    """An ``httpx.AsyncClient`` safe to share between runs on different event loops."""
    return httpx.AsyncClient(transport=_PerLoopTransport(limits=_DEFAULT_LIMITS), **client_kwargs)


# The one client the chat models and the OpenAI SDK calls share.
SHARED_ASYNC_CLIENT = loop_local_async_client()
