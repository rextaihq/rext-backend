"""Scheduled task: drain live API usage counters into api_usage_hourly."""
from src.api.database.async_database import AsyncSessionLocal
from src.services.api_usage_rollup_service import ApiUsageRollupService
from src.utils.logger import logger


async def run_api_usage_rollup_task():
    """
    Move settled per-minute Redis counters into the durable hourly table.

    Runs often enough that the Redis TTL (2h) can never lap it, so no bucket is
    lost even if a pass is missed.
    """
    try:
        async with AsyncSessionLocal() as db:
            result = await ApiUsageRollupService(db).rollup()
        logger.info("API usage rollup complete", extra=result)
        return result
    except Exception as e:
        logger.error(f"API usage rollup failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}
