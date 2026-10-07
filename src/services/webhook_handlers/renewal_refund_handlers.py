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

The first payment's refund comes through its order (``order_refunded``), which records
it and ends the plan, so an ``initial`` invoice is left to that handler and never counted
twice. Refund rows are keyed by an order id; an invoice has none, so its refunds are
recorded under ``invoice:<id>``.
"""

from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.lib.sentry_config import trigger_payment_alert
from src.api.models.subscription_models.subscriptions import UserSubscription
from src.api.models.subscription_models.webhooks import WebhookEvent
from src.providers.payment.provider_factory import get_payment_provider
from src.services.audit_logger import audit_logger
from src.services.billing_email_service import send_billing_email_in_background
from src.services.refund_cancellation import cancel_at_provider_for_refund, end_for_refund
from src.services.refund_service import RefundService
from src.services.usage_tracking_service import UsageTrackingService
from src.services.webhook_handlers.subscription_handlers import (
    PAID_INVOICE_ID,
    _locked_subscription,
)
from src.utils.datetime_utils import parse_provider_datetime
from src.utils.lemonsqueezy_webhook import extract_subscription_data
from src.utils.logger import logger


def invoice_refund_key(invoice_id: Any) -> str:
    """What a renewal's refund rows are recorded under, in place of an order id."""
    return f"invoice:{invoice_id}"


def _is_current_period_payment(subscription: UserSubscription, invoice_id: str) -> bool:
    """Whether this invoice paid for the period the subscription is in.

    A payment credited before the invoice id was recorded has none to compare: it's
    taken as the current one, since a refund comes within 14 days of its payment.
    """
    paid = (subscription.subscription_metadata or {}).get(PAID_INVOICE_ID)
    return paid is None or str(paid) == str(invoice_id)


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

    if sub_data.get("billing_reason") == "initial":
        # The first payment is an order too: order_refunded records and ends it.
        logger.info(
            "subscription_payment_refunded: the first payment, left to order_refunded",
            extra={"invoice_id": invoice_id},
        )
        return

    subscription = await _locked_subscription(db, sub_data.get("subscription_id"))
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
                "subscription": sub_data.get("subscription_id"),
            },
            operation="subscription_payment_refunded",
        )
        return

    key = invoice_refund_key(invoice_id)
    total = int(attributes.get("total") or 0)
    # Lemon Squeezy's refunded_amount is the invoice's cumulative total, not this refund.
    refunded_total = int(attributes.get("refunded_amount") or 0)
    if not refunded_total and (
        attributes.get("refunded") or attributes.get("status") == "refunded"
    ):
        refunded_total = total
    refunded_at = parse_provider_datetime(attributes.get("refunded_at"))

    refund_service = RefundService(db)
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

    current = _is_current_period_payment(subscription, str(invoice_id))
    fully_refunded = total > 0 and refunded_total >= total

    if not fully_refunded:
        if current:
            adjustment = await UsageTrackingService(db).reconcile_partial_refund_credits(
                user_id=subscription.user_id,
                lemonsqueezy_order_id=key,
                refunded_total=refunded_total,
                original_amount=total,
                latest=True,
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

    if not current:
        _earlier_payment_refunded(subscription, str(invoice_id))
        return

    await cancel_at_provider_for_refund(subscription, order_id=key, provider=get_payment_provider())
    end_for_refund(subscription, order_id=key)
    await db.flush()
    logger.info(
        "Ended subscription after its renewal was fully refunded",
        extra={"subscription_id": str(subscription.id), "invoice_id": str(invoice_id)},
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
