"""
API Usage Rollup Service

Drains the live per-minute Redis counters written by RequestTrackerMiddleware
into api_usage_hourly, so usage history survives Redis eviction/restart and
periods longer than the Redis TTL can be answered honestly.

Before this existed, API usage was Redis-only with a 1h TTL: "24 hours",
"7 days" and "30 days" all summed the same ~1h window, and a wider period could
report a *smaller* total as buckets aged out mid-read.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.api.lib.logger import auto_logger
from src.api.models.admin_models.api_usage import ApiUsageHourly

logger = auto_logger()

# Only drain minutes that are definitely finished, so we never roll up a bucket
# that is still being written to and then delete it mid-flight.
_SETTLE_SECONDS = 120
# How far back to look for un-drained buckets. Comfortably wider than the
# rollup interval so a missed run self-heals on the next pass.
_LOOKBACK_MINUTES = 90


class ApiUsageRollupService:
    """Moves live Redis counters into the durable hourly table."""

    def __init__(self, db):
        self.db = db

    async def rollup(self) -> Dict[str, Any]:
        """
        Drain settled minute buckets into api_usage_hourly.

        Returns a summary dict; safe to call repeatedly. Buckets are deleted
        only after their contents are committed.
        """
        from src.api.cache.redis_client import cache

        redis = cache.redis
        if redis is None:
            return {"status": "skipped", "reason": "redis unavailable", "buckets": 0, "rows": 0}

        now_ts = int(datetime.now(timezone.utc).timestamp())
        newest = now_ts - (now_ts % 60) - _SETTLE_SECONDS

        # (hour, endpoint, method) -> [count, errors, duration_ms]
        totals: Dict[tuple, list] = defaultdict(lambda: [0, 0, 0])
        drained_keys: list = []
        buckets = 0

        for i in range(_LOOKBACK_MINUTES):
            bucket = newest - (i * 60)
            counts = await redis.hgetall(f"metrics:api:endpoint:{bucket}")
            if not counts:
                continue

            durations = await redis.hgetall(f"metrics:api:endpoint_time:{bucket}") or {}
            errors = await redis.hgetall(f"metrics:api:endpoint_errors:{bucket}") or {}

            hour = datetime.fromtimestamp(bucket, tz=timezone.utc).replace(
                minute=0, second=0, microsecond=0
            )
            for field, raw_count in counts.items():
                method, _, endpoint = str(field).partition(" ")
                if not endpoint:
                    method, endpoint = "GET", str(field)
                key = (hour, endpoint[:255], method[:10])
                totals[key][0] += int(raw_count or 0)
                totals[key][1] += int(errors.get(field, 0) or 0)
                totals[key][2] += int(float(durations.get(field, 0) or 0))

            drained_keys += [
                f"metrics:api:endpoint:{bucket}",
                f"metrics:api:endpoint_time:{bucket}",
                f"metrics:api:endpoint_errors:{bucket}",
            ]
            buckets += 1

        if not totals:
            return {"status": "ok", "buckets": 0, "rows": 0}

        # Upsert: a given hour is written across many rollup passes, so counts
        # must accumulate onto whatever is already stored, not overwrite it.
        for (hour, endpoint, method), (count, errs, dur) in totals.items():
            stmt = pg_insert(ApiUsageHourly).values(
                hour_bucket=hour, endpoint=endpoint, method=method,
                request_count=count, error_count=errs, total_duration_ms=dur,
            ).on_conflict_do_update(
                constraint="uq_api_usage_hour_endpoint_method",
                set_={
                    "request_count": ApiUsageHourly.request_count + count,
                    "error_count": ApiUsageHourly.error_count + errs,
                    "total_duration_ms": ApiUsageHourly.total_duration_ms + dur,
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            await self.db.execute(stmt)

        await self.db.commit()

        # Only now that the data is committed is it safe to drop the source.
        if drained_keys:
            await redis.delete(*drained_keys)

        logger.info("API usage rolled up",
                    extra={"buckets": buckets, "rows": len(totals)})
        return {"status": "ok", "buckets": buckets, "rows": len(totals)}

    @staticmethod
    async def prune(db, keep_days: int = 90) -> int:
        """Drop rollup rows older than keep_days so the table cannot grow forever."""
        from sqlalchemy import delete
        cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
        result = await db.execute(
            delete(ApiUsageHourly).where(ApiUsageHourly.hour_bucket < cutoff)
        )
        await db.commit()
        return result.rowcount or 0
