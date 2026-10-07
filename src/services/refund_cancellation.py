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
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.lib.sentry_config import trigger_payment_alert
from src.api.models.subscription_models.subscriptions import SubscriptionStatus, UserSubscription
from src.utils.logger import logger

# The record on the subscription's metadata: which order's refund ended it, when,
# and what happened to the cancel at Lemon Squeezy.
ENDED_BY_REFUND = "ended_by_refund"


async def refunded_subscription(
    db: AsyncSession,
    *,
    order_id: str,
    user_id: UUID,
    order: Any = None,
    subscription_id: Optional[UUID] = None,
) -> Optional[UserSubscription]:
    """The subscription a full refund of `order_id` ends, or None when none can be told.

    What the order itself leads to comes first: the subscription its row names, the
    one with its Lemon Squeezy subscription id, the one created from it. A
    `subscription_id` sent with the request is used only when the order leads
    nowhere. Either way it must be the refunded customer's: a refund of one
    customer's order never ends another's plan.
    """

    async def one(*conditions) -> Optional[UserSubscription]:
        result = await db.execute(select(UserSubscription).where(*conditions).limit(1))
        return result.scalar_one_or_none()

    found = None
    if order is not None and getattr(order, "subscription_id", None):
        found = await db.get(UserSubscription, order.subscription_id)
    if found is None and order is not None and getattr(order, "lemonsqueezy_subscription_id", None):
        found = await one(
            UserSubscription.lemonsqueezy_subscription_id == str(order.lemonsqueezy_subscription_id)
        )
    if found is None:
        found = await one(UserSubscription.lemonsqueezy_order_id == str(order_id))
    if found is None and subscription_id:
        found = await db.get(UserSubscription, subscription_id)
    if found is not None and str(found.user_id) != str(user_id):
        logger.error(
            "Full refund: the subscription found isn't the refunded customer's; not ended",
            extra={"order_id": str(order_id), "subscription_id": str(found.id)},
        )
        return None
    return found


def no_subscription_to_end(*, order_id: str, user_id: Any) -> None:
    """A full refund whose subscription can't be told: a person checks Lemon Squeezy."""
    trigger_payment_alert(
        alert_type="refund_cancel_failed",
        message=(
            f"Order {order_id} of user {user_id} was fully refunded, but no subscription of "
            "theirs could be found to cancel: check Lemon Squeezy, and cancel it there if it "
            "is still active, or it renews and charges again"
        ),
        severity="critical",
        context={"order_id": str(order_id)},
        user_id=str(user_id),
        operation="cancel_subscription_for_refund",
    )


def is_ended_by_refund(subscription: UserSubscription) -> bool:
    """A full refund ended the subscription: never offered back, never revived by an event."""
    return bool((getattr(subscription, "subscription_metadata", None) or {}).get(ENDED_BY_REFUND))


def refund_ended_at(subscription: UserSubscription) -> Optional[datetime]:
    """When a full refund ended the subscription, or None."""
    value = _record(subscription).get("ended_at")
    try:
        ended = datetime.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None
    if ended is not None and ended.tzinfo is None:
        ended = ended.replace(tzinfo=timezone.utc)
    return ended


def _record(subscription: UserSubscription) -> dict:
    return dict((subscription.subscription_metadata or {}).get(ENDED_BY_REFUND) or {})


def _save(subscription: UserSubscription, record: dict) -> None:
    # Reassigned, not mutated in place: SQLAlchemy doesn't track a plain JSONB's insides.
    subscription.subscription_metadata = {
        **(subscription.subscription_metadata or {}),
        ENDED_BY_REFUND: record,
    }


async def _cancelled_at_provider(provider, ls_id: str) -> bool:
    """Lemon Squeezy says the subscription is cancelled or over (False when it can't be asked)."""
    read = getattr(provider, "get_subscription_attributes", None)
    if read is None:
        return False
    try:
        attributes = await read(ls_id)
    except Exception:
        return False
    return bool(attributes.get("cancelled")) or attributes.get("status") in ("cancelled", "expired")


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
        # Cancelled there already (the other refund path got there first, or a person
        # did it in the dashboard): that is the outcome wanted, not a failure.
        if await _cancelled_at_provider(provider, ls_id):
            record["provider_cancelled_at"] = now.isoformat()
            record["provider_found_cancelled"] = True
            _save(subscription, record)
            return
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
