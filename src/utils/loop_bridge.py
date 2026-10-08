"""
Cross-event-loop coroutine dispatch for LangGraph worker threads.

LangGraph background jobs run each unit of work on its own isolated event loop
(BG_JOB_ISOLATED_LOOPS), in a worker thread. SQLAlchemy's pooled async engine,
and the asyncpg connections it hands out, are bound to the loop that created
them, so the pool can only be used safely from the loop that owns it (the main
FastAPI loop). This dispatches a worker-loop coroutine onto the registered main
loop and blocks a thread-pool thread for the result, so the pooled engine never
sees a cross-loop connection.

It never runs a job thread's coroutine on the job's own loop. It used to,
whenever no main loop was registered yet, and the runtime takes runs from its
queue before this app's startup has finished: a run resumed in the seconds after
a restart then used the pool's connections from another loop, left one inside a
transaction, and later requests on that connection were answered as saved and
never were (rext-control#858). A job's thread now waits for the main loop, for
a bounded time, and fails its step loudly if none appears.

The one bridge: credit_manager, the notifications and the pipeline's nodes all
come through here.
"""

import asyncio
import threading
import time
from typing import Awaitable, Optional, TypeVar

from src.utils import loop_registry

T = TypeVar("T")

# How long a job's thread waits for the server's main loop to be registered. Startup
# registers it as its first statement, so this is waited out only if startup itself is stuck.
MAIN_LOOP_WAIT_SECONDS = 30.0
_POLL_SECONDS = 0.05
# How the runtime names the threads that run a job on a loop of its own
# (langgraph_runtime_inmem/queue.py: thread_name_prefix=f"bg-loop-{idx}"). A test reads the
# runtime's source for it, so an upgrade that renames them fails there, not in production.
JOB_THREAD_PREFIX = "bg-loop-"


class MainLoopNotReady(RuntimeError):
    """A worker thread needed the server's main loop and none was registered in time."""


def get_main_loop_context():
    """Return (main_loop, current_loop). Either may be None."""
    main_loop = loop_registry.get()
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None
    return main_loop, current_loop


def on_worker_thread() -> bool:
    """Whether this thread is one of the runtime's job threads, each running a job on a loop
    of its own. Any other thread's loop (the server's, a script's, a test's, a test client's)
    is, with no main loop registered, the only loop there is to use the pool from."""
    return threading.current_thread().name.startswith(JOB_THREAD_PREFIX)


async def wait_for_main_loop(timeout: Optional[float] = None) -> asyncio.AbstractEventLoop:
    """The registered main loop, waited for up to ``timeout`` seconds (MAIN_LOOP_WAIT_SECONDS
    when None). Raises MainLoopNotReady when none is registered in that time."""
    limit = MAIN_LOOP_WAIT_SECONDS if timeout is None else timeout
    deadline = time.monotonic() + limit
    while True:
        main_loop = loop_registry.get()
        if main_loop is not None:
            return main_loop
        if time.monotonic() >= deadline:
            raise MainLoopNotReady(
                f"The server's main event loop was not registered within {limit:g} seconds: "
                "this step cannot reach the database or the cache from its own loop."
            )
        await asyncio.sleep(_POLL_SECONDS)


async def run_on_main_loop(coro: Awaitable[T]) -> T:
    """
    Run `coro` on the registered main event loop and await the result.

    On the main loop itself, awaits directly. From any other loop, dispatches via
    run_coroutine_threadsafe and waits using asyncio.to_thread(future.result) so the
    caller's own loop stays unblocked.

    With no main loop registered: outside the runtime's job threads (a script, a test, the
    server's own loop before startup registered it) the current loop is the one the pool
    belongs to, and `coro` is awaited directly. On a job's thread it never is: the call waits
    for the main loop (see wait_for_main_loop) and raises MainLoopNotReady without running
    `coro`.
    """
    main_loop, current_loop = get_main_loop_context()

    if main_loop is not None and current_loop is main_loop:
        return await coro

    if main_loop is None:
        if not on_worker_thread():
            return await coro
        try:
            main_loop = await wait_for_main_loop()
        except MainLoopNotReady:
            # Never started: closed, so it is not reported as a coroutine nobody awaited.
            close = getattr(coro, "close", None)
            if close is not None:
                close()
            raise

    future = asyncio.run_coroutine_threadsafe(coro, main_loop)
    return await asyncio.to_thread(future.result)
