"""
Order webhook handlers.

- order_created: records every order (first purchases and every subscription
  renewal), so an order id resolves to its user for refunds and billing history.
  Access and credits come from the subscription webhooks.
- order_refunded: records the refund and, on a full refund, cancels the
  subscription.
"""

from datetime import datetime, timezone
from typing import Any, Dict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.subscription_models.subscriptions import (
    UserSubscription,
)
from src.api.models.subscription_models.webhooks import WebhookEvent
from src.api.models.user_models.users import Users

# The one shared provider and its HTTP client, under the name these handlers call (G80a): a new
# provider per refund opened an HTTP client that nothing closed. The handlers run on the serving
# loop, as every caller of the payment provider does.
from src.providers.payment.provider_factory import (
    get_payment_provider_singleton as get_payment_provider,
)
from src.services.audit_logger import audit_logger
from src.services.billing_email_service import (
    send_billing_email_in_background,
)
from src.services.order_service import (
    OrderService,
    apply_refund_state,
    refundable_amount,
)
from src.services.order_service import (
    _parse_datetime as _parse_ls_datetime,
)
from src.services.refund_cancellation import (
    cancel_at_provider_for_refund,
    end_for_refund,
    no_subscription_to_end,
    refunded_subscription,
)
from src.services.refund_service import RefundService
from src.services.usage_tracking_service import UsageTrackingService
from src.utils.lemonsqueezy_webhook import (
    extract_order_data,
    get_user_identifier,
)
from src.utils.logger import logger


async def handle_order_created(
    webhook_data: Dict[str, Any], webhook_event: WebhookEvent, db: AsyncSession
) -> None:
    """
    Handle order_created: record the order.

    Lemon Squeezy raises an order for every charge, first purchases and
    subscription renewals alike, and this is the only place they all pass
    through. Without a local row an order id cannot be resolved back to its
    user, which refunds and billing history need.
    """
    logger.info(
        "Processing order_created webhook",
        extra={"event_id": webhook_data.get("event_id")},
    )

    # Extract order data
    order_data = extract_order_data(webhook_data)

    lemonsqueezy_order_id = order_data.get("order_id")
    user_email = order_data.get("user_email")

    # Get user identifier from custom_data or email
    user_identifier = get_user_identifier(webhook_data)

    # Find user
    user = None
    if user_identifier:
        # Try to find by user_id first (if passed in custom_data)
        try:
            user_id = UUID(user_identifier)
            stmt = select(Users).where(Users.id == user_id)
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()
        except (ValueError, TypeError):
            # Not a valid UUID, try email
            pass

    if not user and user_email:
        # Find by email
        stmt = select(Users).where(Users.email == user_email)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

    if not user:
        # An order we cannot attribute. Nothing here grants access, so log and
        # move on rather than failing the webhook.
        logger.warning(
            f"User not found for order {lemonsqueezy_order_id} - skipping",
            extra={"user_identifier": user_identifier, "user_email": user_email},
        )
        return

    await OrderService(db).record_order(
        user_id=user.id,
        order_data=order_data,
    )


async def handle_order_refunded(
    webhook_data: Dict[str, Any], webhook_event: WebhookEvent, db: AsyncSession
) -> None:
    """
    Handle order_refunded webhook event.

    This event fires when an order is refunded.

    Actions:
    1. Find the order and its subscription
    2. Record the refund (delta against Lemon Squeezy's total)
    3. On a full refund, cancel the subscription
    4. Send refund confirmation email

    Args:
        webhook_data: Parsed webhook data
        webhook_event: Database record for this webhook
        db: Database session
    """
    logger.info(
        "Processing order_refunded webhook", extra={"event_id": webhook_data.get("event_id")}
    )

    # Extract order data. LemonSqueezy reports `refunded_amount` as the total
    # refunded against the order so far, not the amount of this refund.
    order_data = extract_order_data(webhook_data)
    lemonsqueezy_order_id = order_data.get("order_id")
    total_amount = order_data.get("total", 0) or 0
    provider_refunded_total = order_data.get("refunded_amount") or 0
    if not provider_refunded_total and order_data.get("refunded"):
        # Payload may omit refunded_amount on order_refunded. Attempt to fetch
        # the authoritative total directly from LemonSqueezy before assuming full refund.
        if lemonsqueezy_order_id:
            try:
                provider = get_payment_provider()
                ls_order = await provider.get_refund(str(lemonsqueezy_order_id))
                attributes = (ls_order.get("attributes", {}) or {}) if ls_order else {}
                provider_refunded_total = int(attributes.get("refunded_amount") or 0)
            except Exception as exc:
                logger.warning(
                    f"Could not fetch order refund details from provider for {lemonsqueezy_order_id}: {exc}"
                )

        if not provider_refunded_total:
            # Fall back to total_amount ONLY if status explicitly indicates a full refund
            status_val = str(order_data.get("status") or "").lower()
            if status_val == "refunded":
                provider_refunded_total = total_amount
    user_email = order_data.get("user_email")

    # Find and expire associated subscription
    stmt = select(UserSubscription).where(
        UserSubscription.lemonsqueezy_order_id == lemonsqueezy_order_id
    )
    result = await db.execute(stmt)
    subscription = result.scalar_one_or_none()

    # The orders table is the general case: user_subscriptions.lemonsqueezy_order_id
    # is only set on some rows, so
    # without this lookup most refunds could not be attributed at all.
    order_service = OrderService(db)
    order = await order_service.get_by_lemonsqueezy_id(lemonsqueezy_order_id)

    # Need at least one to process refund
    if not subscription and not order:
        logger.warning(f"No order or subscription found for refunded order {lemonsqueezy_order_id}")
        return  # Not an error - the order may predate local order recording

    if subscription:
        user_id = subscription.user_id
    else:
        user_id = order.user_id

    subscription_id = (
        subscription.id if subscription else (order.subscription_id if order else None)
    )

    # Keep the local order's own details in step with LemonSqueezy. Its refund
    # status is set below from the totals instead, so a replayed webhook cannot
    # move an order between refunded and partially refunded.
    if order:
        await order_service.record_order(
            user_id=user_id,
            order_data=order_data,
            subscription_id=subscription_id,
        )
        # The order carries the authoritative amount paid.
        total_amount = order.total or total_amount

    # The webhook is the source of truth for money actually returned. Recording
    # is delta-based against LemonSqueezy's cumulative total, so a replay of
    # this event writes nothing and the totals stay correct.
    refund_service = RefundService(db)
    new_refund = await refund_service.record_provider_refund(
        lemonsqueezy_order_id=lemonsqueezy_order_id,
        user_id=user_id,
        provider_refunded_total=provider_refunded_total,
        original_amount=total_amount,
        subscription_id=subscription_id,
        reason="Refund processed via LemonSqueezy",
        currency=order_data.get("currency") or "USD",
        refunded_at=_parse_ls_datetime(order_data.get("refunded_at")),
    )

    # Tell the customer their money is on its way — but only for money this
    # event actually recorded. A refund issued through our own admin screens
    # has already sent this email, and its webhook records nothing new, so the
    # same delta that keeps the totals right also stops the mail duplicating.
    if new_refund is not None:
        await send_billing_email_in_background(
            "send_refund_issued_email",
            user_id=user_id,
            order_id=str(lemonsqueezy_order_id),
            refund_amount=(
                f"{(new_refund.refund_amount or 0) / 100:.2f} {new_refund.currency or 'USD'}"
            ),
            refund_date=datetime.now(timezone.utc).strftime("%B %d, %Y"),
            original_plan_name=order.product_name if order else None,
        )

        await audit_logger.log_payment_refunded(
            user_id=user_id,
            refund_id=new_refund.id,
            subscription_id=subscription_id,
            amount=new_refund.refund_amount,
            reason=new_refund.reason,
            is_partial=new_refund.is_partial,
            lemonsqueezy_refund_id=new_refund.lemonsqueezy_refund_id,
            metadata={
                "lemonsqueezy_order_id": lemonsqueezy_order_id,
                "provider_refunded_total": provider_refunded_total,
                "original_amount": total_amount,
            },
            db=db,
        )

    refunded_total = await refund_service.get_refunded_total(lemonsqueezy_order_id)

    if order:
        apply_refund_state(
            order,
            refunded_total,
            refunded_at=_parse_ls_datetime(order_data.get("refunded_at")),
        )
        await db.flush()
        fully_refunded = refundable_amount(order, refunded_total) <= 0
    else:
        fully_refunded = total_amount > 0 and refunded_total >= total_amount

    # Only a full refund revokes access. A partial refund leaves the customer
    # paid up for the rest, so cancelling on one would take away access they
    # still own.
    if not fully_refunded:
        logger.info(
            f"Partial refund on order {lemonsqueezy_order_id}: "
            f"{refunded_total} of {total_amount} cents refunded, access retained",
            extra={"order_id": lemonsqueezy_order_id},
        )

        # Access stays, the unused half of the entitlement does not. Spent
        # credits and everything already generated with them are untouched.
        adjustment = await UsageTrackingService(db).reconcile_partial_refund_credits(
            user_id=user_id,
            lemonsqueezy_order_id=lemonsqueezy_order_id,
            refunded_total=refunded_total,
            original_amount=total_amount,
        )
        if adjustment:
            logger.info(
                f"Reduced unused credits after partial refund on order "
                f"{lemonsqueezy_order_id}: "
                f"{adjustment['credits_before']} -> {adjustment['credits_after']}",
                extra={"order_id": lemonsqueezy_order_id, **adjustment},
            )
            # There is no credit ledger, so this audit line is the only record
            # of why a balance moved.
            await audit_logger.log_payment_refunded(
                user_id=user_id,
                refund_id=new_refund.id if new_refund else None,
                subscription_id=subscription_id,
                amount=refunded_total,
                reason="Partial refund: unused credit entitlement reduced",
                is_partial=True,
                metadata=adjustment,
                db=db,
            )
        return

    # A full refund ends the subscription at Lemon Squeezy and here (F8c,
    # revnix/rext-control#538). A refund made in Lemon Squeezy's dashboard arrives only
    # here, so the cancel is made here too; one made through _issue_refund has made it
    # already (recorded, so not again), and one that lands in between is found
    # cancelled there. Ended with provider_updated_at moved on, so Lemon Squeezy's
    # later events (still active, or cancelled with a grace period) can't bring it back.
    subscription = await refunded_subscription(
        db,
        order_id=str(lemonsqueezy_order_id),
        user_id=user_id,
        order=order,
        subscription_id=subscription.id if subscription else subscription_id,
    )
    if subscription:
        await cancel_at_provider_for_refund(
            subscription, order_id=str(lemonsqueezy_order_id), provider=get_payment_provider()
        )
        end_for_refund(subscription, order_id=str(lemonsqueezy_order_id))
        await db.flush()

        logger.info(
            f"Cancelled subscription {subscription.id} due to refund",
            extra={"subscription_id": str(subscription.id)},
        )
    else:
        no_subscription_to_end(order_id=str(lemonsqueezy_order_id), user_id=user_id)

    # TODO: Send refund confirmation email
    # For now, logging that email should be sent
    logger.info(
        f"Refund processed for order {lemonsqueezy_order_id} - Email notification should be sent to {user_email}",
        extra={
            "order_id": lemonsqueezy_order_id,
            "user_email": user_email,
            "subscription_id": str(subscription.id) if subscription else None,
        },
    )
