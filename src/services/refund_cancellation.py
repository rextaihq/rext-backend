"""
A full refund ends the subscription at Lemon Squeezy too (F8c, revnix/rext-control#538).

Refunding an order's whole balance returns the money but leaves Lemon Squeezy's
subscription active: it renews and charges the refunded customer again next month,
and its next "active" update gives the plan back. So a full refund issued here (the
admin's "Create refund", or an approved customer request) also cancels the
subscription at Lemon Squeezy, once, and the subscription ends locally there and
then.

Money moves around here, so nothing is repeated automatically: the cancel is
recorded on the row, a row already recorded is skipped, and a cancel that fails
raises a critical alert for a person to finish in Lemon Squeezy. The refund itself
is never undone.

Lemon Squeezy's cancellation leaves the subscription a grace period, and its events
say so (cancelled, with ends_at in the future). A row ended by a refund ignores them,
as a settled duplicate does (`subscription_handlers`), so they can't give the plan back.
"""

from datetime import datetime, timezone
from typing import Optional

from src.api.lib.sentry_config import trigger_payment_alert
from src.api.models.subscription_models.subscriptions import SubscriptionStatus, UserSubscription
from src.utils.logger import logger

# The record on the subscription's metadata: which order's refund ended it, when,
# and what happened to the cancel at Lemon Squeezy.
ENDED_BY_REFUND = "ended_by_refund"


def is_ended_by_refund(subscription: UserSubscription) -> bool:
    """A full refund ended the subscription: never offered back, never revived by an event."""
    return bool((getattr(subscription, "subscription_metadata", None) or {}).get(ENDED_BY_REFUND))


def _record(subscription: UserSubscription) -> dict:
    return dict((subscription.subscription_metadata or {}).get(ENDED_BY_REFUND) or {})


def _save(subscription: UserSubscription, record: dict) -> None:
    # Reassigned, not mutated in place: SQLAlchemy doesn't track a plain JSONB's insides.
    subscription.subscription_metadata = {
        **(subscription.subscription_metadata or {}),
        ENDED_BY_REFUND: record,
    }


def end_for_refund(
    subscription: UserSubscription, *, order_id: str, now: Optional[datetime] = None
) -> None:
    """End the subscription here and now, for a full refund of `order_id`.

    `provider_updated_at` moves to now too, so a Lemon Squeezy event carrying an
    older state of the subscription is ignored as well.
    """
    now = now or datetime.now(timezone.utc)
    record = _record(subscription)
    record.setdefault("order_id", str(order_id))
    record.setdefault("ended_at", now.isoformat())
    _save(subscription, record)
    subscription.status = SubscriptionStatus.CANCELLED
    subscription.cancelled_at = subscription.cancelled_at or now
    subscription.cancel_at_period_end = False
    subscription.end_date = now
    subscription.updated_at = now
    stored = subscription.provider_updated_at
    if stored is not None and stored.tzinfo is None:
        stored = stored.replace(tzinfo=timezone.utc)
    if stored is None or stored < now:
        subscription.provider_updated_at = now


async def cancel_at_provider_for_refund(
    subscription: UserSubscription, *, order_id: str, provider
) -> None:
    """Cancel the subscription at Lemon Squeezy for a full refund of `order_id`, once.

    A cancel already made, or one that failed and went to a person, isn't tried
    again. A failure raises a critical alert; the refund stands either way.
    """
    record = _record(subscription)
    if record.get("provider_cancelled_at") or record.get("provider_cancel_failed"):
        return
    ls_id = subscription.lemonsqueezy_subscription_id
    if not ls_id:
        return
    now = datetime.now(timezone.utc)
    record.setdefault("order_id", str(order_id))
    try:
        await provider.cancel_subscription(ls_id)
    except Exception as e:
        record["provider_cancel_failed"] = str(e)[:500]
        trigger_payment_alert(
            alert_type="refund_cancel_failed",
            message=(
                f"Subscription {ls_id} for user {subscription.user_id} was fully refunded "
                f"(order {order_id}) but couldn't be cancelled at Lemon Squeezy ({e}): "
                "cancel it there by hand, or it renews and charges again"
            ),
            severity="critical",
            context={"lemonsqueezy_subscription_id": ls_id, "order_id": str(order_id)},
            user_id=str(subscription.user_id),
            subscription_id=str(subscription.id),
            operation="cancel_subscription_for_refund",
        )
        logger.error(
            "Fully refunded subscription could not be cancelled at Lemon Squeezy",
            extra={"lemonsqueezy_subscription_id": ls_id, "order_id": str(order_id)},
        )
    else:
        record["provider_cancelled_at"] = now.isoformat()
        logger.info(
            "Fully refunded subscription cancelled at Lemon Squeezy",
            extra={"lemonsqueezy_subscription_id": ls_id, "order_id": str(order_id)},
        )
    _save(subscription, record)
