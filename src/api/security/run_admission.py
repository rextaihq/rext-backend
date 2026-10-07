"""Admitting a generation run under the per-user cap, so runs started together can't all pass it (G62).

Counting the user's busy threads alone is a read-then-act check: three runs requested at
once all see none busy before any of them is created. So the count and the admission
happen under a short per-user lock, and an admitted run counts from its admission until
the runtime marks its thread busy, which follows at once (the window only covers that
gap). Redis holds the lock and the recent admissions, so it holds across processes; when
Redis isn't there, an in-process lock does the same within this process.
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
ADMISSION_WINDOW_S = 30
_LOCK_TTL_MS = 5000
_LOCK_WAIT_S = 3.0

BusyThreads = Callable[[], Awaitable[set[str]]]

_local_locks: dict[str, asyncio.Lock] = {}
_local_admitted: dict[str, dict[str, float]] = {}


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
            raise TimeoutError("run admission lock is held")
        await asyncio.sleep(0.05)
    try:
        now = time.time()
        await redis.zremrangebyscore(recent_key, 0, now - ADMISSION_WINDOW_S)
        recent = set(await redis.zrange(recent_key, 0, -1))
        if not _admits(await busy_threads(), recent, thread_id):
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
        admitted = {
            t: at
            for t, at in _local_admitted.get(identity, {}).items()
            if at > now - ADMISSION_WINDOW_S
        }
        if not _admits(await busy_threads(), set(admitted), thread_id):
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
        except Exception:
            logger.warning("run admission: Redis unavailable, admitting in process", exc_info=True)
    return await _admit_in_process(identity, thread, busy_threads)
