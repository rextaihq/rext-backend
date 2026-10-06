"""
Nightly job: reconcile every unfinished subscription with Lemon Squeezy.

See src/services/subscription_reconciler.py. Run by the scheduler
(src/tasks/scheduled_tasks.py, SUBSCRIPTION_RECONCILE_ENABLED); by hand:
    python -m src.api.tasks.subscription_reconcile_task
"""

import asyncio
from typing import Any, Dict

from src.api.database.async_database import AsyncSessionLocal
from src.services.subscription_reconciler import reconcile_subscriptions
from src.utils.logger import logger


async def run_subscription_reconcile_task() -> Dict[str, Any]:
    async with AsyncSessionLocal() as db:
        try:
            result = await reconcile_subscriptions(db)
            await db.commit()
        except Exception:
            await db.rollback()
            logger.error("Subscription reconcile failed", exc_info=True)
            raise

    # Emails go out only once the corrections are committed, as for webhooks.
    from src.api.routes.subscriptions.webhook_routes import (
        _send_webhook_email,
        _send_webhook_notification,
    )

    for task in result.pop("emails"):
        try:
            await _send_webhook_email(task, None)
            await _send_webhook_notification(task)
        except Exception:
            logger.error("Reconcile: could not send an email", exc_info=True)

    logger.info("Subscription reconcile finished", extra=result)
    return result


if __name__ == "__main__":
    print(asyncio.run(run_subscription_reconcile_task()))
