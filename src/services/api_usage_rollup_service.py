"""
API Usage Rollup

Copies the per-minute request counters that RequestTrackerMiddleware writes to
Redis into api_usage_hourly, so usage history outlives the Redis TTL.

Nothing that already worked is removed: Redis keeps counting live, and the
endpoint still reads it. This only adds a durable copy, so "7 days" and
"30 days" have real history instead of whatever ~1h had not yet expired.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.api.lib.logger import auto_logger
from src.api.models.admin_models.api_usage import ApiUsageHourly, ApiUsageRollupState

logger = auto_logger()

# Only drain minutes that are definitely finished, so a bucket still being
# written to is never rolled up and then deleted mid-flight.
_SETTLE_SECONDS = 120
# Cold-start window only: used when no watermark exists yet. Afterwards the
# watermark defines the range exactly, so this cannot cause gaps or overlap.
# Kept below the Redis metric TTL so it never scans minutes that cannot exist.
_LOOKBACK_MINUTES = 180


class ApiUsageRollupService:
    """Moves live Redis counters into the durable hourly table."""

    def __init__(self, db):
        self.db = db

    async def rollup(self) -> Dict[str, Any]:
        """
        Settle finished Redis minute buckets into api_usage_hourly.

        Exact-once by construction: the watermark advances in the SAME
        transaction as the hourly upserts, and readers count Redis only after
        the watermark. Deleting Redis keys afterwards is best-effort cleanup --
        if it fails, or the process dies first, nothing is double counted
        because the watermark already excludes those minutes.
        """
        from src.api.cache.redis_client import cache

        redis = cache.redis
        if redis is None:
            return {"status": "skipped", "reason": "redis unavailable", "hours": 0}

        now_ts = int(datetime.now(timezone.utc).timestamp())
        # Never settle a minute that could still be written to.
        settle_to = now_ts - (now_ts % 60) - _SETTLE_SECONDS

        state = await self._get_state()
        watermark_ts = (
            int(state.settled_through.timestamp()) if state.settled_through else None
        )

        # Only minutes strictly after the watermark are candidates.
        oldest = (
            watermark_ts + 60 if watermark_ts is not None
            else settle_to - (_LOOKBACK_MINUTES * 60)
        )
        if settle_to < oldest:
            return {"status": "ok", "hours": 0, "requests": 0, "settled_through": watermark_ts}

        totals: Dict[datetime, list] = defaultdict(lambda: [0, 0, 0])
        drained: list = []

        for bucket in range(oldest, settle_to + 60, 60):
            count = await redis.get(f"metrics:api:count:{bucket}")
            drained += [
                f"metrics:api:count:{bucket}",
                f"metrics:api:errors:{bucket}",
                f"metrics:api:time_sum:{bucket}",
            ]
            if count is None:
                continue
            errors = await redis.get(f"metrics:api:errors:{bucket}")
            duration = await redis.get(f"metrics:api:time_sum:{bucket}")

            hour = datetime.fromtimestamp(bucket, tz=timezone.utc).replace(
                minute=0, second=0, microsecond=0
            )
            totals[hour][0] += int(count or 0)
            totals[hour][1] += int(errors or 0)
            totals[hour][2] += int(float(duration or 0))

        # Upsert accumulates: one hour is settled across many passes.
        for hour, (count, errs, dur) in totals.items():
            await self.db.execute(
                pg_insert(ApiUsageHourly)
                .values(hour_bucket=hour, request_count=count,
                        error_count=errs, total_duration_ms=dur)
                .on_conflict_do_update(
                    constraint="uq_api_usage_hour",
                    set_={
                        "request_count": ApiUsageHourly.request_count + count,
                        "error_count": ApiUsageHourly.error_count + errs,
                        "total_duration_ms": ApiUsageHourly.total_duration_ms + dur,
                        "updated_at": datetime.now(timezone.utc),
                    },
                )
            )

        # Advance the watermark in the same transaction as the data above.
        # Advanced even when no counters were found, so an idle period does not
        # leave the window growing without bound.
        settled_dt = datetime.fromtimestamp(settle_to, tz=timezone.utc)
        await self.db.execute(
            update(ApiUsageRollupState)
            .where(ApiUsageRollupState.id == 1)
            .values(settled_through=settled_dt, updated_at=datetime.now(timezone.utc))
        )
        await self.db.commit()

        # Best-effort cleanup. Correctness no longer depends on this.
        if drained:
            try:
                await redis.delete(*drained)
            except Exception:
                logger.warning("Redis cleanup after rollup failed", exc_info=True)

        total_requests = sum(v[0] for v in totals.values())
        logger.info("API usage settled",
                    extra={"hours": len(totals), "requests": total_requests,
                           "settled_through": settled_dt.isoformat()})
        return {"status": "ok", "hours": len(totals), "requests": total_requests,
                "settled_through": settled_dt.isoformat()}

    async def _get_state(self) -> ApiUsageRollupState:
        """Fetch the single watermark row, creating it if absent."""
        state = (await self.db.execute(
            select(ApiUsageRollupState).where(ApiUsageRollupState.id == 1)
        )).scalar_one_or_none()
        if state is None:
            state = ApiUsageRollupState(id=1, settled_through=None)
            self.db.add(state)
            await self.db.flush()
        return state

    @staticmethod
    async def settled_through(db) -> Optional[datetime]:
        """
        Watermark for readers: every minute at or before this is in Postgres.

        Readers must count Redis strictly after it, so a request is never
        counted from both stores.
        """
        return (await db.execute(
            select(ApiUsageRollupState.settled_through)
            .where(ApiUsageRollupState.id == 1)
        )).scalar_one_or_none()

    @staticmethod
    async def prune(db, keep_days: int = 90) -> int:
        """Drop rows older than keep_days so the table cannot grow forever."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
        result = await db.execute(
            delete(ApiUsageHourly).where(ApiUsageHourly.hour_bucket < cutoff)
        )
        await db.commit()
        return result.rowcount or 0
