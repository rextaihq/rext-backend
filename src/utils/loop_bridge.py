"""
Cross-event-loop coroutine dispatch for LangGraph worker threads.

LangGraph background jobs run each unit of work on its own isolated event loop
(BG_JOB_ISOLATED_LOOPS). SQLAlchemy's pooled async engine — and the asyncpg
connections it hands out — are bound to the loop that created them, so the
pool can only be used safely from the loop that owns it (the main FastAPI
loop). This dispatches a worker-loop coroutine onto the registered main loop
and blocks a thread-pool thread for the result, so the pooled engine never
sees a cross-loop connection.

Same pattern as credit_manager._run_on_main_loop, rext_store._MainLoopProxy,
and outline._bulk_sync_workspace's stated intent — consolidated here so new
call sites don't each redefine it.
"""

import asyncio
from typing import Awaitable, TypeVar

from src.utils import loop_registry

T = TypeVar("T")


def get_main_loop_context():
    """Return (main_loop, current_loop). Either may be None."""
    main_loop = loop_registry.get()
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None
    return main_loop, current_loop


async def run_on_main_loop(coro: Awaitable[T]) -> T:
    """
    Run `coro` on the registered main event loop and await the result.

    If already on the main loop, or no main loop is registered yet (cold
    start / scripts / tests), awaits directly on the current loop. Otherwise
    dispatches via run_coroutine_threadsafe and waits using
    asyncio.to_thread(future.result) so the caller's own loop stays unblocked.
    """
    main_loop, current_loop = get_main_loop_context()

    if main_loop is None or current_loop is main_loop:
        return await coro

    future = asyncio.run_coroutine_threadsafe(coro, main_loop)
    return await asyncio.to_thread(future.result)
