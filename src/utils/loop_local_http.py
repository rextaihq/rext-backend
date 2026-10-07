"""An OpenAI HTTP client whose connections never cross event loops (G80, rext-control #644).

LangGraph runs each background job on its own event loop (BG_JOB_ISOLATED_LOOPS), while
langchain_openai caches ONE process-wide async client for every chat model. A pooled
connection, and the asyncio locks and events inside the pool, belong to the loop that first used
them, so two runs at once failed with "<asyncio.locks.Event …> is bound to a different event
loop", with "Event loop is closed" once a finished run's loop had gone, or stalled.

``loop_local_async_client`` is one client to share, as before, whose transport keeps a separate
connection pool for each event loop: a run's calls only ever use connections made on its own
loop. A pool goes once its loop has closed.

It is the OpenAI SDK's own default client (``openai.DefaultAsyncHttpxClient``, on httpx2) with
the SDK's connection limits, so the SDK keeps its native request path and defaults; only the
transport is ours. A client given a transport takes no proxy from the environment.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

import httpx2
from openai import DefaultAsyncHttpxClient
from openai._constants import DEFAULT_CONNECTION_LIMITS

# Built once, here: a TLS context reads the CA bundle from disk, which must not happen inside a
# request on an event loop. Every per-loop pool shares it.
_SSL_CONTEXT = httpx2.create_ssl_context()


class _PerLoopTransport(httpx2.AsyncBaseTransport):
    """Hands each request to a connection pool of the event loop it runs on."""

    def __init__(self, **transport_kwargs: Any) -> None:
        self._transport_kwargs = transport_kwargs
        # Not a WeakKeyDictionary: a pool's connections hold their loop, so the loop would never be
        # collected. Pools of closed loops are dropped instead.
        self._pools: dict[asyncio.AbstractEventLoop, httpx2.AsyncHTTPTransport] = {}
        # Requests on different loops run in different threads.
        self._lock = threading.Lock()

    def _pool(self) -> httpx2.AsyncHTTPTransport:
        loop = asyncio.get_running_loop()
        with self._lock:
            for closed in [other for other in self._pools if other.is_closed()]:
                # Its connections can't be closed from here; the sockets go with them.
                del self._pools[closed]
            pool = self._pools.get(loop)
            if pool is None:
                pool = httpx2.AsyncHTTPTransport(**self._transport_kwargs)
                self._pools[loop] = pool
            return pool

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        return await self._pool().handle_async_request(request)

    async def aclose(self) -> None:
        # Only the calling loop's pool can be closed from here; the others are dropped once their
        # loops have closed.
        with self._lock:
            pool = self._pools.pop(asyncio.get_running_loop(), None)
        if pool is not None:
            await pool.aclose()


def loop_local_async_client(**client_kwargs: Any) -> DefaultAsyncHttpxClient:
    """The OpenAI SDK's default async client, safe to share between runs on different loops."""
    return DefaultAsyncHttpxClient(
        transport=_PerLoopTransport(limits=DEFAULT_CONNECTION_LIMITS, verify=_SSL_CONTEXT),
        **client_kwargs,
    )


# The one client the chat models and the OpenAI SDK calls share. Never close it: every model
# call in the process goes through it.
SHARED_ASYNC_CLIENT = loop_local_async_client()
