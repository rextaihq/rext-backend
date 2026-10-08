"""
A refunded renewal (F8b, revnix/rext-control#537).

Lemon Squeezy bills a renewal as a subscription invoice, not an order, and a refund of
one arrives as ``subscription_payment_refunded``. Nothing handled that event, so a
refunded renewal was never recorded and left the month's credits and access in place,
although the refund rule (DECISIONS.md, #88) covers any payment within 14 days.

- A full refund of the current period's payment ends the subscription the way a
  refunded first payment does (F8c, #538): cancelled at Lemon Squeezy once, ended here
  with provider_updated_at moved on, so no later event revives it.
- A partial one keeps the plan and shrinks the period's unused credits, as a partial
  order refund does.
- A full refund of an earlier payment leaves the current, separately paid period alone
  and alerts a person.

- A refund of a plan change's invoice (``billing_reason`` ``updated``, the proration
  charged at once) is recorded and alerts a person: the period it adjusts stays paid.

Refund rows are keyed by an order id; an invoice has none, so a renewal's refunds are
recorded under ``invoice:<id>``. The first payment's invoice is recorded under its order's
id instead: refunded through the order, Lemon Squeezy also sends ``order_refunded``, and
the shared key lets whichever arrives second record nothing.

Lemon Squeezy may deliver a refund before the payment it refunds. An invoice newer than
the one the plan last credited is the coming period's: a full refund ends the plan (the
late payment is then ignored), and a partial one is recorded and applied by
``apply_early_invoice_refund`` once the payment's month is granted.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.lib.sentry_config import trigger_payment_alert
from src.api.models.subscription_models.orders import Order
from src.api.models.subscription_models.subscriptions import UserSubscription
from src.api.models.subscription_models.webhooks import WebhookEvent

# The one shared provider and its HTTP client, as the order's refund handler takes it: a new
# provider for each refund would open a client that nothing closes.
from src.providers.payment.provider_factory import (
    get_payment_provider_singleton as get_payment_provider,
)
from src.services.audit_logger import audit_logger
from src.services.billing_email_service import send_billing_email_in_background
from src.services.refund_cancellation import cancel_at_provider_for_refund, end_for_refund
from src.services.refund_service import RefundService
from src.services.usage_tracking_service import UsageTrackingService
from src.services.webhook_handlers.subscription_handlers import (
    PAID_INVOICE_AT,
    PAID_INVOICE_ID,
    _locked_subscription,
)
from src.utils.datetime_utils import parse_provider_datetime
from src.utils.lemonsqueezy_webhook import extract_subscription_data
from src.utils.logger import logger


def invoice_refund_key(invoice_id: Any) -> str:
    """What a renewal's refund rows are recorded under, in place of an order id."""
    return f"invoice:{invoice_id}"


CURRENT, EARLIER, UPCOMING = "current", "earlier", "upcoming"

# The invoice whose partial refund came before its payment: its month is cut once granted.
EARLY_REFUND_INVOICE = "early_refund_invoice"


def _period_of(
    subscription: UserSubscription, invoice_id: str, invoice_created_at: Optional[datetime]
) -> str:
    """Which period this invoice paid for, against the payment the plan last credited.

    ``current``: the credited one. ``upcoming``: a newer invoice whose payment hasn't been
    credited yet (its refund arrived first). ``earlier``: an older one. A payment credited
    before invoice ids were recorded has none to compare: unless the invoice is newer than
    that payment, it's taken as the current one, since a refund comes within 14 days of
    its payment.
    """
    meta = subscription.subscription_metadata or {}
    paid = meta.get(PAID_INVOICE_ID)
    if paid is not None and str(paid) == str(invoice_id):
        return CURRENT
    paid_at = parse_provider_datetime(meta.get(PAID_INVOICE_AT))
    if invoice_created_at and paid_at and invoice_created_at > paid_at:
        return UPCOMING
    return CURRENT if paid is None else EARLIER


async def _refund_key(
    db: AsyncSession,
    lemonsqueezy_subscription_id: Optional[str],
    billing_reason: Optional[str],
    invoice_id: Any,
) -> str:
    """What this invoice's refunds are recorded under, read without locking anything.

    The first payment's invoice shares its order's id with ``order_refunded``. The
    subscription's row names that order; an older row that doesn't is found through the
    order recorded for the subscription (it has one order, the first payment's: renewals
    are invoices). Every other invoice, and a first one whose order can't be found, has
    its own key.
    """
    if billing_reason == "initial" and lemonsqueezy_subscription_id:
        row = (
            await db.execute(
                select(UserSubscription.id, UserSubscription.lemonsqueezy_order_id).where(
                    UserSubscription.lemonsqueezy_subscription_id
                    == str(lemonsqueezy_subscription_id)
                )
            )
        ).first()
        if row is not None and row.lemonsqueezy_order_id:
            return str(row.lemonsqueezy_order_id)
        if row is not None:
            order_id = (
                await db.execute(
                    select(Order.lemonsqueezy_order_id)
                    .where(Order.subscription_id == row.id)
                    .order_by(Order.created_at.asc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if order_id:
                return str(order_id)
    return invoice_refund_key(invoice_id)


async def handle_subscription_payment_refunded(
    webhook_data: Dict[str, Any], webhook_event: WebhookEvent, db: AsyncSession
) -> None:
    """Handle subscription_payment_refunded: a subscription invoice refunded in part or full."""
    data = webhook_data.get("data", {}) or {}
    attributes = data.get("attributes", {}) or {}
    invoice_id = data.get("id")
    sub_data = extract_subscription_data(webhook_data)
    logger.info(
        "Processing subscription_payment_refunded webhook",
        extra={"event_id": webhook_data.get("event_id"), "invoice_id": invoice_id},
    )

    billing_reason = sub_data.get("billing_reason")
    lemonsqueezy_subscription_id = sub_data.get("subscription_id")
    refund_service = RefundService(db)
    # The refund's lock before the subscription's row: order_refunded records first and
    # writes the subscription after, so the two handlers of one first-payment refund take
    # them in the same order and neither holds what the other waits for.
    key = await _refund_key(db, lemonsqueezy_subscription_id, billing_reason, invoice_id)
    if invoice_id:
        await refund_service.lock_order(key)
    subscription = await _locked_subscription(db, lemonsqueezy_subscription_id)
    if subscription is None or not invoice_id:
        trigger_payment_alert(
            alert_type="refund_unmatched",
            message=(
                f"Subscription invoice {invoice_id} was refunded, but no subscription here "
                "matches it: check Lemon Squeezy, and the customer's credits and access"
            ),
            severity="medium",
            context={
                "invoice_id": str(invoice_id),
                "subscription": lemonsqueezy_subscription_id,
            },
            operation="subscription_payment_refunded",
        )
        if invoice_id and lemonsqueezy_subscription_id:
            # The refund can come before subscription_created has made the row (that
            # event delayed, or failed and waiting for its retry). Marked processed,
            # the refund would be lost and the plan granted in full afterwards, so
            # the event fails and the reprocessing job runs it again, as
            # subscription_payment_success does for the same reason.
            raise ValueError(
                f"Subscription {lemonsqueezy_subscription_id} not found in "
                "subscription_payment_refunded - retried once it has been created"
            )
        return

    # The first payment's refund shares its order's key (_refund_key), so order_refunded
    # and this event record it once between them, whichever comes first.
    total = int(attributes.get("total") or 0)
    # Lemon Squeezy's refunded_amount is the invoice's cumulative total, not this refund.
    refunded_total = int(attributes.get("refunded_amount") or 0)
    if not refunded_total and (
        attributes.get("refunded") or attributes.get("status") == "refunded"
    ):
        refunded_total = total
    refunded_at = parse_provider_datetime(attributes.get("refunded_at"))

    new_refund = await refund_service.record_provider_refund(
        lemonsqueezy_order_id=key,
        user_id=subscription.user_id,
        provider_refunded_total=refunded_total,
        original_amount=total,
        subscription_id=subscription.id,
        reason="Renewal refunded via Lemon Squeezy",
        currency=attributes.get("currency") or "USD",
        refunded_at=refunded_at,
    )
    if new_refund is not None:
        await send_billing_email_in_background(
            "send_refund_issued_email",
            user_id=subscription.user_id,
            order_id=str(invoice_id),
            refund_amount=(
                f"{(new_refund.refund_amount or 0) / 100:.2f} {new_refund.currency or 'USD'}"
            ),
            refund_date=datetime.now(timezone.utc).strftime("%B %d, %Y"),
        )
        await audit_logger.log_payment_refunded(
            user_id=subscription.user_id,
            refund_id=new_refund.id,
            subscription_id=subscription.id,
            amount=new_refund.refund_amount,
            reason=new_refund.reason,
            is_partial=new_refund.is_partial,
            metadata={
                "lemonsqueezy_invoice_id": str(invoice_id),
                "provider_refunded_total": refunded_total,
                "original_amount": total,
            },
            db=db,
        )

    if billing_reason == "updated":
        _plan_change_refunded(subscription, str(invoice_id), refunded_total, total)
        return

    period = _period_of(
        subscription, str(invoice_id), parse_provider_datetime(attributes.get("created_at"))
    )
    fully_refunded = total > 0 and refunded_total >= total

    if not fully_refunded:
        if period == UPCOMING:
            # Its month isn't granted yet: apply_early_invoice_refund cuts it when it is.
            subscription.subscription_metadata = {
                **(subscription.subscription_metadata or {}),
                EARLY_REFUND_INVOICE: str(invoice_id),
            }
            logger.info(
                "Partial refund recorded before its payment; applied when the payment arrives",
                extra={"subscription_id": str(subscription.id), "invoice_id": str(invoice_id)},
            )
        elif period == CURRENT:
            adjustment = await UsageTrackingService(db).reconcile_partial_refund_credits(
                user_id=subscription.user_id,
                lemonsqueezy_order_id=key,
                refunded_total=refunded_total,
                original_amount=total,
                latest=True,
                subscription_id=subscription.id,
            )
            if adjustment:
                await audit_logger.log_payment_refunded(
                    user_id=subscription.user_id,
                    refund_id=new_refund.id if new_refund else None,
                    subscription_id=subscription.id,
                    amount=refunded_total,
                    reason="Partial refund of a renewal: unused credit entitlement reduced",
                    is_partial=True,
                    metadata=adjustment,
                    db=db,
                )
        return

    if period == EARLIER:
        _earlier_payment_refunded(subscription, str(invoice_id))
        return

    await cancel_at_provider_for_refund(subscription, order_id=key, provider=get_payment_provider())
    end_for_refund(subscription, order_id=key)
    await db.flush()
    logger.info(
        "Ended subscription after its renewal was fully refunded",
        extra={"subscription_id": str(subscription.id), "invoice_id": str(invoice_id)},
    )


async def apply_early_invoice_refund(
    db: AsyncSession, subscription: UserSubscription, invoice_id: Optional[str], total: int
) -> Optional[Dict[str, Any]]:
    """A partial refund of this invoice recorded before its payment: shrink the month just
    granted by it, as if it had come after. Called by subscription_payment_success; a
    payment with no such refund costs one dictionary lookup."""
    meta = subscription.subscription_metadata or {}
    if not invoice_id or total <= 0 or meta.get(EARLY_REFUND_INVOICE) != str(invoice_id):
        return None
    subscription.subscription_metadata = {
        k: v for k, v in meta.items() if k != EARLY_REFUND_INVOICE
    }
    key = invoice_refund_key(invoice_id)
    refunded_total = await RefundService(db).get_refunded_total(key)
    if not refunded_total or refunded_total >= total:
        return None
    adjustment = await UsageTrackingService(db).reconcile_partial_refund_credits(
        user_id=subscription.user_id,
        lemonsqueezy_order_id=key,
        refunded_total=refunded_total,
        original_amount=total,
        latest=True,
        subscription_id=subscription.id,
    )
    if adjustment:
        # Nothing else records a change to the balance: the cut is audited here as it
        # is when the refund comes after its payment.
        await audit_logger.log_payment_refunded(
            user_id=subscription.user_id,
            refund_id=None,
            subscription_id=subscription.id,
            amount=refunded_total,
            reason=(
                "Partial refund of a renewal, received before its payment: "
                "unused credit entitlement reduced"
            ),
            is_partial=True,
            metadata={**adjustment, "lemonsqueezy_invoice_id": str(invoice_id)},
            db=db,
        )
    return adjustment


def _plan_change_refunded(
    subscription: UserSubscription, invoice_id: str, refunded_total: int, total: int
) -> None:
    """A refund of a plan change's prorated invoice: recorded, and left to a person.

    The period it adjusts was paid by its own invoice, so the plan isn't ended, and the
    month's credits came with the change (F8a), so they aren't scaled by this invoice.
    """
    trigger_payment_alert(
        alert_type="refund_of_plan_change",
        message=(
            f"Plan-change invoice {invoice_id} was refunded ({refunded_total} of {total}): "
            "the plan was left as it is; check whether its credits or plan should change"
        ),
        severity="medium",
        context={"invoice_id": invoice_id, "subscription_id": str(subscription.id)},
        user_id=str(subscription.user_id),
        operation="subscription_payment_refunded",
    )


def _earlier_payment_refunded(subscription: UserSubscription, invoice_id: str) -> None:
    """A full refund of a payment before the current period's: the period stays paid."""
    trigger_payment_alert(
        alert_type="refund_of_earlier_payment",
        message=(
            f"Subscription invoice {invoice_id} was fully refunded, but a later payment "
            "paid for the current period, so the plan was left running: check whether "
            "it should end"
        ),
        severity="medium",
        context={"invoice_id": invoice_id, "subscription_id": str(subscription.id)},
        user_id=str(subscription.user_id),
        operation="subscription_payment_refunded",
    )
