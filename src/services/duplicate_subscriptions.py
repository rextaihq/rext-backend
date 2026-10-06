"""
Two live Lemon Squeezy subscriptions for one customer: keep the newer, settle the older.

It can still happen despite the checkout guard (a payment Lemon Squeezy recovers
late, two tabs, a race), and it bills the customer twice. Founder decision on
F11 (revnix/rext-control#336): the newer subscription stays; the older one is
cancelled at Lemon Squeezy, its latest paid invoice is refunded in full, and we
are alerted.

Money moves here, so nothing is repeated automatically: each settled row records
what was done, a row already settled is skipped, and a step that fails raises a
critical alert for a person to finish instead of a retry.
"""

from datetime import datetime, timezone
from typing import List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.lib.sentry_config import trigger_payment_alert
from src.api.models.subscription_models.subscriptions import SubscriptionStatus, UserSubscription
from src.providers.payment.provider_factory import get_payment_provider_singleton
from src.utils.logger import logger

# The statuses of a subscription Lemon Squeezy still bills or can still bill.
LIVE_STATUSES = (
    SubscriptionStatus.ACTIVE,
    SubscriptionStatus.TRIAL,
    SubscriptionStatus.PAST_DUE,
    SubscriptionStatus.UNPAID,
    SubscriptionStatus.PAUSED,
)


def is_settled_duplicate(subscription: UserSubscription) -> bool:
    """The subscription was cancelled here as the older of two."""
    return bool((getattr(subscription, "subscription_metadata", None) or {}).get("duplicate_of"))


async def settle_duplicate_subscriptions(
    db: AsyncSession, user_id: UUID, provider=None
) -> List[UUID]:
    """Keep the user's newest live Lemon Squeezy subscription; settle the older ones.

    The payment provider is looked up only when there is something to settle.
    Returns the ids of the subscriptions settled now.
    """
    live = (
        await db.scalars(
            select(UserSubscription)
            .where(
                UserSubscription.user_id == user_id,
                UserSubscription.lemonsqueezy_subscription_id.is_not(None),
                UserSubscription.status.in_(LIVE_STATUSES),
            )
            .order_by(UserSubscription.created_at.desc())
        )
    ).all()
    if len(live) < 2:
        return []

    keep, older = live[0], live[1:]
    provider = provider or get_payment_provider_singleton()
    settled = []
    for subscription in older:
        if is_settled_duplicate(subscription):
            continue
        await _settle(subscription, keep, provider)
        settled.append(subscription.id)
    await db.flush()
    return settled


async def _settle(subscription: UserSubscription, keep: UserSubscription, provider) -> None:
    ls_id = subscription.lemonsqueezy_subscription_id
    context = {
        "kept_subscription_id": str(keep.id),
        "kept_lemonsqueezy_subscription_id": keep.lemonsqueezy_subscription_id,
        "older_lemonsqueezy_subscription_id": ls_id,
    }
    now = datetime.now(timezone.utc)
    record = {**(subscription.subscription_metadata or {}), "duplicate_of": str(keep.id)}
    step = "cancel at Lemon Squeezy"
    try:
        await provider.cancel_subscription(ls_id)
        record["duplicate_cancelled_at"] = now.isoformat()
        step = "find its latest paid invoice"
        invoice = await provider.latest_paid_invoice(ls_id)
        if invoice and invoice["total"] > 0:
            step = "refund its latest paid invoice"
            await provider.refund_subscription_invoice(invoice["id"], invoice["total"])
            record["duplicate_refunded_invoice_id"] = invoice["id"]
            record["duplicate_refunded_cents"] = invoice["total"]
    except Exception as e:
        record["duplicate_settle_failed"] = f"{step}: {e}"
        trigger_payment_alert(
            alert_type="duplicate_subscription",
            message=(
                f"Duplicate subscription {ls_id} for user {subscription.user_id} needs a person: "
                f"could not {step} ({e})"
            ),
            severity="critical",
            context=context,
            user_id=str(subscription.user_id),
            subscription_id=str(subscription.id),
            operation="settle_duplicate_subscription",
        )
        logger.error(
            "Duplicate subscription could not be settled",
            extra={**context, "step": step, "error": str(e)},
        )
    else:
        trigger_payment_alert(
            alert_type="duplicate_subscription",
            message=(
                f"Duplicate subscription {ls_id} for user {subscription.user_id} cancelled "
                f"and refunded ({record.get('duplicate_refunded_cents', 0)} cents); kept "
                f"{keep.lemonsqueezy_subscription_id}"
            ),
            severity="high",
            context=context,
            user_id=str(subscription.user_id),
            subscription_id=str(subscription.id),
            operation="settle_duplicate_subscription",
        )

    # The newer subscription gives the plan; the older one ends here.
    subscription.status = SubscriptionStatus.CANCELLED
    subscription.cancelled_at = now
    subscription.cancel_at_period_end = False
    subscription.end_date = now
    subscription.subscription_metadata = record
