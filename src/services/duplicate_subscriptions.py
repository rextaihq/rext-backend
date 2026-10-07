"""
Two live Lemon Squeezy subscriptions for one customer: keep the newer, settle the older.

It can still happen despite the checkout guard (a payment Lemon Squeezy recovers
late, two tabs, a race), and it bills the customer twice. Founder decision on
F11 (revnix/rext-control#336): the newer subscription stays; the older one is
cancelled at Lemon Squeezy, its latest paid invoice is refunded in full, and we
are alerted.

Money moves here, so nothing is repeated automatically: each settled row records
what was done, a row already settled is skipped, and a step that fails raises a
critical alert for a person to finish instead of a retry. Only the newest invoice
is ever refunded, and only when it is paid in full: one already refunded (an
earlier attempt whose transaction didn't commit) is taken as done, and anything
else (a partial refund, an invoice not paid yet) goes to a person, never an
older invoice in its place.

The cancel and the refund run only when BILLING_AUTO_SETTLE_DUPLICATES is true
(founder, 2026-10-07: off for launch week, on after a week of sandbox runs).
While it is off, a duplicate is recorded on the older row and a critical alert
asks a person to cancel and refund it by hand in Lemon Squeezy; no row's status
or access changes here.
"""

import os
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, text
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


# When Lemon Squeezy created the subscription, from its webhook, kept in the row's metadata.
PROVIDER_CREATED_AT = "provider_created_at"


def auto_settle_enabled() -> bool:
    """Whether a duplicate is cancelled and refunded here, or left to a person (the default)."""
    return os.getenv("BILLING_AUTO_SETTLE_DUPLICATES", "false").strip().lower() == "true"


def is_settled_duplicate(subscription: UserSubscription) -> bool:
    """The subscription was cancelled here as the older of two."""
    return bool((getattr(subscription, "subscription_metadata", None) or {}).get("duplicate_of"))


def is_known_duplicate(subscription: UserSubscription) -> bool:
    """Settled here, or found and left to a person: either way never offered back to resume."""
    metadata = getattr(subscription, "subscription_metadata", None) or {}
    return bool(metadata.get("duplicate_of") or metadata.get("duplicate_found_of"))


def provider_created_record(created_at: Optional[str]) -> dict:
    """The metadata a new row starts with: when Lemon Squeezy created the subscription."""
    return {PROVIDER_CREATED_AT: created_at} if created_at else {}


def _created(subscription: UserSubscription) -> datetime:
    """When Lemon Squeezy created the subscription, else when we stored it.

    Webhooks arrive out of order, so the row stored last isn't always the newer purchase.
    """
    when = subscription.created_at or datetime.min
    stamped = (subscription.subscription_metadata or {}).get(PROVIDER_CREATED_AT)
    if stamped:
        try:
            when = datetime.fromisoformat(str(stamped).replace("Z", "+00:00"))
        except ValueError:
            pass
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


class _NeedsAPerson(Exception):
    """The settlement can't decide the amount itself."""


async def settle_duplicate_subscriptions(
    db: AsyncSession, user_id: UUID, provider=None
) -> List[UUID]:
    """Keep the user's newest live Lemon Squeezy subscription; settle the older ones.

    The payment provider is looked up only when there is something to settle.
    Returns the ids of the subscriptions settled now.
    """
    # One settlement per customer at a time. Two subscription_created webhooks for one
    # customer can run at once, each seeing only its own new row: the second waits here
    # until the first commits, then reads both (each statement reads what's committed).
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"subscriptions:settle:{user_id}"},
    )
    live = sorted(
        (
            await db.scalars(
                select(UserSubscription).where(
                    UserSubscription.user_id == user_id,
                    UserSubscription.lemonsqueezy_subscription_id.is_not(None),
                    UserSubscription.status.in_(LIVE_STATUSES),
                )
            )
        ).all(),
        key=_created,
        reverse=True,
    )
    if len(live) < 2:
        return []

    keep, older = live[0], live[1:]
    if not auto_settle_enabled():
        for subscription in older:
            _leave_to_a_person(subscription, keep)
        await db.flush()
        return []
    provider = provider or get_payment_provider_singleton()
    settled = []
    for subscription in older:
        if is_settled_duplicate(subscription):
            continue
        await _settle(subscription, keep, provider)
        settled.append(subscription.id)
    await db.flush()
    return settled


def _leave_to_a_person(subscription: UserSubscription, keep: UserSubscription) -> None:
    """Record the duplicate and alert once; a person cancels and refunds it in Lemon Squeezy."""
    if (subscription.subscription_metadata or {}).get("duplicate_found_of") == str(keep.id):
        return
    subscription.subscription_metadata = {
        **(subscription.subscription_metadata or {}),
        "duplicate_found_of": str(keep.id),
        "duplicate_found_at": datetime.now(timezone.utc).isoformat(),
    }
    ls_id = subscription.lemonsqueezy_subscription_id
    trigger_payment_alert(
        alert_type="duplicate_subscription",
        message=(
            f"Duplicate subscription {ls_id} for user {subscription.user_id} needs a person: "
            f"cancel it and refund its latest payment in Lemon Squeezy, and keep "
            f"{keep.lemonsqueezy_subscription_id} (BILLING_AUTO_SETTLE_DUPLICATES is off)"
        ),
        severity="critical",
        context={
            "kept_subscription_id": str(keep.id),
            "kept_lemonsqueezy_subscription_id": keep.lemonsqueezy_subscription_id,
            "older_lemonsqueezy_subscription_id": ls_id,
        },
        user_id=str(subscription.user_id),
        subscription_id=str(subscription.id),
        operation="settle_duplicate_subscription",
    )
    logger.warning(
        "Duplicate subscription left to a person (automatic settlement is off)",
        extra={"older_lemonsqueezy_subscription_id": ls_id, "kept_subscription_id": str(keep.id)},
    )


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
        step = "find its latest invoice"
        invoice = await provider.latest_invoice(ls_id)
        step = "refund its latest invoice"
        if invoice is None or invoice["total"] <= 0:
            pass  # nothing was paid
        elif invoice["status"] == "refunded":
            # Refunded already: an earlier attempt whose transaction didn't commit, or a person.
            record["duplicate_refunded_invoice_id"] = invoice["id"]
            record["duplicate_refund_found_done"] = True
        elif invoice["status"] == "paid" and not invoice["refunded"]:
            await provider.refund_subscription_invoice(invoice["id"], invoice["total"])
            record["duplicate_refunded_invoice_id"] = invoice["id"]
            record["duplicate_refunded_cents"] = invoice["total"]
        else:
            raise _NeedsAPerson(
                f"invoice {invoice['id']} is {invoice['status']}, so the amount to refund "
                "needs a person"
            )
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
