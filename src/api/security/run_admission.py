"""Admitting a generation run under the per-user cap, so runs started together can't all pass it (G62).

Counting the user's busy threads alone is a read-then-act check: three runs requested at
once all see none busy before any of them is created. So the count and the admission
happen under a short per-user lock, and an admitted run counts from its admission until
the runtime marks its thread busy: from then on the busy thread counts instead, so the run
stops counting when it ends. The runtime calls this admission from the same call that
inserts the run and marks its thread busy (`Runs.put`, through the `create_run` handler),
so an admission needs to count only for that call; the window is a few seconds, so a run
that ends before any later start sees it busy (or a start the runtime then rejects) stops
counting soon after. Redis holds the lock and the recent admissions, so it holds across
processes; when Redis isn't there, an in-process lock does the same within this process. A
lock another start of the same user's holds past the wait is a refusal, never the
in-process path: that would admit outside the lock. The busy-thread read is bounded well
inside the lock's lifetime, so the lock can't expire while a start still acts on its read.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from uuid import uuid4

from src.api.cache.redis_client import cache

logger = logging.getLogger(__name__)

MAX_ACTIVE_RUNS = 2
# How long an admission counts before its thread shows busy: the rest of the runtime's
# insert, with room for a slow database (rext-control#604).
ADMISSION_WINDOW_S = 10
# The lock outlives the busy-thread read it guards, which is cut off well before; a start
# waits for the lock a little less than its lifetime.
_LOCK_TTL_MS = 15000
_LOCK_WAIT_S = 8.0
_READ_TIMEOUT_S = 5.0

BusyThreads = Callable[[], Awaitable[set[str]]]

_local_locks: dict[str, asyncio.Lock] = {}
_local_admitted: dict[str, dict[str, float]] = {}


class AdmissionBusy(Exception):
    """Another start of the same user's holds the admission lock past the wait."""


async def _read_busy(busy_threads: BusyThreads) -> set[str]:
    """The user's busy threads, or none when the read takes longer than the bound, as when
    it fails (auth._busy_threads): the run isn't held up, and the credit checks still apply."""
    try:
        return await asyncio.wait_for(busy_threads(), _READ_TIMEOUT_S)
    except TimeoutError:
        logger.warning("run admission: the busy-thread read timed out, counting none busy")
        return set()


def _admits(busy: set[str], recent: set[str], thread_id: str) -> bool:
    """Room for this thread's run: the user's other active runs are fewer than the cap."""
    return len((busy | recent) - {thread_id}) < MAX_ACTIVE_RUNS


async def _admit_with_redis(
    redis, identity: str, thread_id: str, busy_threads: BusyThreads
) -> bool:
    lock_key = f"run_admission:lock:{identity}"
    recent_key = f"run_admission:recent:{identity}"
    token = uuid4().hex
    deadline = time.monotonic() + _LOCK_WAIT_S
    while not await redis.set(lock_key, token, nx=True, px=_LOCK_TTL_MS):
        if time.monotonic() > deadline:
            raise AdmissionBusy()
        await asyncio.sleep(0.05)
    try:
        now = time.time()
        await redis.zremrangebyscore(recent_key, 0, now - ADMISSION_WINDOW_S)
        recent = set(await redis.zrange(recent_key, 0, -1))
        busy = await _read_busy(busy_threads)
        # An admitted run the runtime now shows busy counts as busy from here on.
        if seen := recent & busy:
            await redis.zrem(recent_key, *seen)
            recent -= seen
        if not _admits(busy, recent, thread_id):
            return False
        await redis.zadd(recent_key, {thread_id: now})
        await redis.expire(recent_key, ADMISSION_WINDOW_S * 2)
        return True
    finally:
        if await redis.get(lock_key) == token:
            await redis.delete(lock_key)


async def _admit_in_process(identity: str, thread_id: str, busy_threads: BusyThreads) -> bool:
    async with _local_locks.setdefault(identity, asyncio.Lock()):
        now = time.time()
        busy = await _read_busy(busy_threads)
        admitted = {
            t: at
            for t, at in _local_admitted.get(identity, {}).items()
            if at > now - ADMISSION_WINDOW_S and t not in busy
        }
        if not _admits(busy, set(admitted), thread_id):
            _local_admitted[identity] = admitted
            return False
        admitted[thread_id] = now
        _local_admitted[identity] = admitted
        return True


async def admit_run(identity: str, thread_id: object, busy_threads: BusyThreads) -> bool:
    """Whether the user may start (or resume) a run on `thread_id` now; if so, it's counted."""
    thread = str(thread_id)
    if cache.is_enabled and cache.redis is not None:
        try:
            return await _admit_with_redis(cache.redis, identity, thread, busy_threads)
        except AdmissionBusy:
            logger.warning("run admission: another start holds the lock, refusing this one")
            return False
        except Exception as exc:
            logger.warning(
                "run admission: Redis unavailable (%s), admitting in process", type(exc).__name__
            )
    return await _admit_in_process(identity, thread, busy_threads)
