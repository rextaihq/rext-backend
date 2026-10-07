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
            # Each subscription is committed by itself, and its email goes out right
            # after its own commit (deliver), as for webhooks.
            result = await reconcile_subscriptions(db, deliver=deliver_reconcile_email)
            await db.commit()
        except Exception:
            await db.rollback()
            logger.error("Subscription reconcile failed", exc_info=True)
            raise

    result.pop("emails", None)
    logger.info("Subscription reconcile finished", extra=result)
    return result


async def deliver_reconcile_email(task: Dict[str, Any]) -> None:
    """One subscription's email and in-app notice, each sent whatever happens to the other."""
    from src.api.routes.subscriptions.webhook_routes import (
        _send_webhook_email,
        _send_webhook_notification,
    )

    try:
        await _send_webhook_email(task, None)
    except Exception:
        logger.error("Reconcile: could not send an email", exc_info=True)
    try:
        if task.get("email_type") == "subscription_cancelled":
            await _notify_cancellation(task)
        else:
            await _send_webhook_notification(task)
    except Exception:
        logger.error("Reconcile: could not send an in-app notice", exc_info=True)


async def _notify_cancellation(task: Dict[str, Any]) -> None:
    """The in-app notice for a cancellation the reconcile found.

    A cancellation made in the app sends its own notice; one made in Lemon
    Squeezy's portal gets it from its webhook's path, which this one replaces when
    that webhook was missed.
    """
    from src.services.notification_helper import notify_now

    data = task.get("email_data", {})
    if not data.get("user_id"):
        return
    await notify_now(
        user_id=data["user_id"],
        pref_flag="billing_subscription_cancelled",
        message=(
            f"Your subscription has been cancelled. Your {data.get('plan_name') or 'plan'} "
            f"lasts until {data.get('end_date') or 'the end of your billing period'}."
        ),
        payload={"plan_name": data.get("plan_name"), "end_date": data.get("end_date")},
    )


if __name__ == "__main__":
    print(asyncio.run(run_subscription_reconcile_task()))
