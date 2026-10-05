"""
Subscription Webhook Handlers

Handlers for subscription-related LemonSqueezy webhook events:
- subscription_created
- subscription_updated
- subscription_cancelled
- subscription_expired
- subscription_resumed
- subscription_paused
- subscription_unpaused
- subscription_payment_success
- subscription_payment_failed
- subscription_payment_recovered

Each handler:
1. Extracts relevant data from webhook
2. Updates database (creates/updates subscriptions)
3. Returns email task data (to be sent AFTER commit)
4. Logs actions

IMPORTANT: Email sending happens AFTER database commit to prevent orphaned notifications.
Handlers return email task data instead of sending emails directly.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.lib.logging_config import (
    generate_payment_correlation_id,
)
from src.api.lib.sentry_config import (
    add_payment_breadcrumb,
    alert_subscription_creation_failure,
    set_payment_context,
)
from src.api.models.subscription_models.discount_usage import DiscountUsage
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import (
    PAYMENT_RETRY_STATUSES,
    BillingPeriod,
    SubscriptionStatus,
    UserSubscription,
    retry_deadline,
)
from src.api.models.subscription_models.webhooks import WebhookEvent
from src.api.models.user_models.users import Users
from src.services.audit_logger import audit_logger
from src.services.trial_service import TrialService
from src.utils.datetime_utils import add_months, parse_provider_datetime, utc_now_naive
from src.utils.lemonsqueezy_webhook import extract_subscription_data, get_user_identifier
from src.utils.logger import logger


def _stamp_card_details(subscription: UserSubscription, sub_data: Dict[str, Any]) -> None:
    """Persist the card LemonSqueezy reports on the subscription so the UI can show it.

    Reassigns the dict rather than mutating it: SQLAlchemy does not track
    in-place changes to a plain JSONB column.
    """
    meta = {**(subscription.subscription_metadata or {})}
    if sub_data.get("card_brand"):
        meta["card_brand"] = sub_data["card_brand"]
    if sub_data.get("card_last_four"):
        meta["card_last_four"] = sub_data["card_last_four"]
    if meta != (subscription.subscription_metadata or {}):
        subscription.subscription_metadata = meta


async def handle_subscription_created(
    webhook_data: Dict[str, Any], webhook_event: WebhookEvent, db: AsyncSession
) -> Optional[Dict[str, Any]]:
    """
    Handle subscription_created webhook event.

    This event fires when a new subscription is created in LemonSqueezy.
    It happens after a successful checkout.

    Actions:
    1. Extract subscription data from webhook
    2. Find user by email or custom_data.user_id
    3. Find subscription plan by variant_id
    4. Create UserSubscription record
    5. Update user's provider_customer_id
    6. Return email task data for sending after commit

    Args:
        webhook_data: Parsed webhook data
        webhook_event: Database record for this webhook
        db: Database session

    Returns:
        Email task dict or None

    Raises:
        Exception: If user not found, plan not found, or database error
    """
    # Generate correlation ID for tracking (Phase 4, Task 4.2.2)
    correlation_id = generate_payment_correlation_id()

    logger.info(
        "Processing subscription_created webhook",
        operation="webhook_subscription_created",
        event_id=webhook_data.get("event_id"),
        correlation_id=correlation_id,
    )

    # Extract subscription data
    sub_data = extract_subscription_data(webhook_data)

    # Add Sentry context for webhook processing (Phase 4, Task 4.2.1)
    set_payment_context(
        operation="webhook_subscription_created",
        subscription_id=sub_data.get("subscription_id"),
        customer_id=sub_data.get("customer_id"),
        metadata={
            "event_id": webhook_data.get("event_id"),
            "event_type": "subscription_created",
        },
    )

    add_payment_breadcrumb(
        "Processing subscription_created webhook",
        operation="webhook",
        data={
            "event_id": webhook_data.get("event_id"),
            "subscription_id": sub_data.get("subscription_id"),
        },
    )

    lemonsqueezy_subscription_id = sub_data.get("subscription_id")
    lemonsqueezy_customer_id = sub_data.get("customer_id")
    lemonsqueezy_variant_id = sub_data.get("variant_id")
    user_email = sub_data.get("user_email")
    status = sub_data.get("status", "active")
    renews_at = sub_data.get("renews_at")
    trial_ends_at = sub_data.get("trial_ends_at")

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
        error_msg = f"User not found for subscription {lemonsqueezy_subscription_id}"
        logger.error(
            error_msg, extra={"user_identifier": user_identifier, "user_email": user_email}
        )

        # Trigger critical alert (Phase 4, Task 4.2.3)
        alert_subscription_creation_failure(
            user_id=user_identifier or user_email or "unknown",
            variant_id=lemonsqueezy_variant_id,
            error_message=error_msg,
            event_id=webhook_data.get("event_id"),
        )

        raise ValueError(error_msg)

    # Find subscription plan by LemonSqueezy variant_id
    stmt = select(SubscriptionPlan).where(
        (SubscriptionPlan.lemonsqueezy_variant_id_monthly == lemonsqueezy_variant_id)
        | (SubscriptionPlan.lemonsqueezy_variant_id_yearly == lemonsqueezy_variant_id)
    )
    result = await db.execute(stmt)
    plan = result.scalar_one_or_none()

    if not plan:
        error_msg = f"Plan not found for variant_id {lemonsqueezy_variant_id}"
        logger.error(error_msg)

        # Trigger critical alert (Phase 4, Task 4.2.3)
        alert_subscription_creation_failure(
            user_id=str(user.id),
            variant_id=lemonsqueezy_variant_id,
            error_message=error_msg,
            event_id=webhook_data.get("event_id"),
        )

        raise ValueError(error_msg)

    # Determine billing period based on variant
    billing_period = (
        BillingPeriod.YEARLY
        if plan.lemonsqueezy_variant_id_yearly == lemonsqueezy_variant_id
        else BillingPeriod.MONTHLY
    )

    # Map LemonSqueezy status to internal status
    status_map = {
        "on_trial": SubscriptionStatus.TRIAL,
        "active": SubscriptionStatus.ACTIVE,
        "paused": SubscriptionStatus.PAUSED,
        "past_due": SubscriptionStatus.PAST_DUE,
        "unpaid": SubscriptionStatus.PAST_DUE,
        "cancelled": SubscriptionStatus.CANCELLED,
        "expired": SubscriptionStatus.EXPIRED,
    }
    internal_status = status_map.get(status.lower(), SubscriptionStatus.ACTIVE)

    # Check if subscription already exists (shouldn't happen due to idempotency, but be safe)
    stmt = select(UserSubscription).where(
        UserSubscription.lemonsqueezy_subscription_id == lemonsqueezy_subscription_id
    )
    result = await db.execute(stmt)
    existing_sub = result.scalar_one_or_none()

    if existing_sub:
        logger.warning(
            f"Subscription {lemonsqueezy_subscription_id} already exists - updating",
            extra={"subscription_id": str(existing_sub.id)},
        )
        # Update existing subscription
        existing_sub.status = internal_status
        existing_sub.plan_id = plan.id
        existing_sub.billing_period = billing_period
        existing_sub.lemonsqueezy_customer_id = lemonsqueezy_customer_id
        existing_sub.lemonsqueezy_variant_id = lemonsqueezy_variant_id
        existing_sub.trial_end_date = (
            datetime.fromisoformat(trial_ends_at).replace(tzinfo=None) if trial_ends_at else None
        )
        if plan.credits_per_month is not None:
            existing_sub.current_credits = plan.credits_per_month
            # LemonSqueezy `renews_at` is the authoritative billing-period end;
            # fall back to a calendar month only when it is absent.
            existing_sub.credits_reset_date = parse_provider_datetime(renews_at) or add_months(
                utc_now_naive(), 1
            )
        existing_sub.updated_at = datetime.now(timezone.utc)
        await db.flush()
        subscription = existing_sub
    else:
        # IMPORTANT: Cancel any existing active/trial subscriptions for this user
        # This handles the case when user upgrades via a new checkout instead of upgrade endpoint
        existing_active_subs_stmt = select(UserSubscription).where(
            UserSubscription.user_id == user.id,
            UserSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL]),
            or_(
                UserSubscription.lemonsqueezy_subscription_id.is_(None),
                UserSubscription.lemonsqueezy_subscription_id != lemonsqueezy_subscription_id,
            ),
        )
        existing_active_result = await db.execute(existing_active_subs_stmt)
        existing_active_subs = existing_active_result.scalars().all()

        for old_sub in existing_active_subs:
            was_trial = (
                old_sub.status == SubscriptionStatus.TRIAL or old_sub.trial_end_date is not None
            )
            if not was_trial and old_sub.plan_id:
                old_p_stmt = select(SubscriptionPlan).where(SubscriptionPlan.id == old_sub.plan_id)
                old_p_res = await db.execute(old_p_stmt)
                old_p = old_p_res.scalar_one_or_none()
                if old_p and old_p.name.lower() == "trial":
                    was_trial = True

            if was_trial:
                try:
                    trial_service = TrialService(db)
                    trial_started_at = (
                        old_sub.start_date or old_sub.created_at or datetime.now(timezone.utc)
                    )
                    trial_ended_at = old_sub.trial_end_date or datetime.now(timezone.utc)
                    amount_dollars = (
                        plan.price_yearly
                        if billing_period == BillingPeriod.YEARLY
                        else plan.price_monthly
                    )
                    await trial_service.track_trial_conversion(
                        user_id=user.id,
                        subscription_id=old_sub.id,
                        trial_started_at=trial_started_at,
                        trial_ended_at=trial_ended_at,
                        plan_id=plan.id,
                        billing_period=billing_period.value,
                        payment_amount=amount_dollars,
                        metadata={
                            "new_subscription_id": lemonsqueezy_subscription_id,
                            "conversion_source": "checkout_upgrade",
                        },
                    )
                    logger.info(
                        f"Tracked trial conversion for user {user.id} during checkout upgrade",
                        extra={"user_id": str(user.id), "old_subscription_id": str(old_sub.id)},
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to track trial conversion in subscription_created webhook: {e}",
                        exc_info=True,
                    )

            logger.info(
                f"Cancelling old subscription {old_sub.id} (LemonSqueezy: {old_sub.lemonsqueezy_subscription_id}) "
                f"as user is now on new subscription {lemonsqueezy_subscription_id}",
                extra={
                    "old_subscription_id": str(old_sub.id),
                    "new_lemonsqueezy_subscription_id": lemonsqueezy_subscription_id,
                    "user_id": str(user.id),
                },
            )
            old_sub.status = SubscriptionStatus.CANCELLED
            old_sub.cancelled_at = datetime.now(timezone.utc)
            old_sub.end_date = datetime.now(timezone.utc)
            old_sub.updated_at = datetime.now(timezone.utc)

        if existing_active_subs:
            await db.flush()
            logger.info(
                f"Cancelled {len(existing_active_subs)} existing subscription(s) for user {user.id}",
                extra={"user_id": str(user.id), "count": len(existing_active_subs)},
            )

        # Create new subscription
        now = datetime.now(timezone.utc)
        trial_end_date = (
            datetime.fromisoformat(trial_ends_at).replace(tzinfo=None) if trial_ends_at else None
        )

        subscription = UserSubscription(
            user_id=user.id,
            plan_id=plan.id,
            status=internal_status,
            billing_period=billing_period,
            start_date=now,
            trial_end_date=trial_end_date,
            lemonsqueezy_subscription_id=lemonsqueezy_subscription_id,
            lemonsqueezy_customer_id=lemonsqueezy_customer_id,
            lemonsqueezy_variant_id=lemonsqueezy_variant_id,
            renews_at=parse_provider_datetime(renews_at),
            current_api_calls=0,
            current_credits=plan.credits_per_month or 0,
            # `renews_at` from the provider is the authoritative period end;
            # fall back to a calendar month only when it is absent.
            credits_reset_date=parse_provider_datetime(renews_at) or add_months(utc_now_naive(), 1),
            usage_reset_date=parse_provider_datetime(renews_at) or add_months(utc_now_naive(), 1),
            created_at=now,
            updated_at=now,
        )

        _stamp_card_details(subscription, sub_data)

        db.add(subscription)
        await db.flush()

        logger.info(
            f"Created subscription {subscription.id} for user {user.id}",
            extra={
                "subscription_id": str(subscription.id),
                "user_id": str(user.id),
                "plan_id": str(plan.id),
                "status": internal_status.value,
            },
        )

    # Update user's provider_customer_id if not set
    if not user.provider_customer_id and lemonsqueezy_customer_id:
        user.provider_customer_id = lemonsqueezy_customer_id
        await db.flush()
        logger.info(f"Updated user {user.id} provider_customer_id")

    # Track discount usage if discount was applied
    discount_data = webhook_data.get("meta", {}).get("custom_data", {})
    if discount_data and discount_data.get("discount_code"):
        # Extract discount information from webhook
        discount_code = discount_data.get("discount_code")
        affiliate_code = discount_data.get("affiliate_code")

        # Extract discount details from attributes
        attributes = webhook_data.get("data", {}).get("attributes", {})
        first_subscription_item = attributes.get("first_subscription_item", {})

        # Create discount usage record
        discount_usage = DiscountUsage(
            user_id=user.id,
            subscription_id=subscription.id,
            discount_code=discount_code,
            discount_amount=first_subscription_item.get("discount_total"),
            discount_amount_type="fixed",  # Will be updated based on actual data
            lemonsqueezy_discount_id=first_subscription_item.get("discount_id"),
            order_id=attributes.get("first_order_id"),
            applied_at=datetime.now(timezone.utc),
            usage_metadata={
                "subscription_id": lemonsqueezy_subscription_id,
                "variant_id": lemonsqueezy_variant_id,
                "webhook_event_id": webhook_data.get("event_id"),
                "affiliate_code": affiliate_code if affiliate_code else None,
            },
        )

        db.add(discount_usage)
        await db.flush()

        logger.info(
            f"Tracked discount usage: {discount_code} for user {user.id}"
            + (f" (affiliate: {affiliate_code})" if affiliate_code else ""),
            extra={
                "user_id": str(user.id),
                "discount_code": discount_code,
                "subscription_id": str(subscription.id),
                "affiliate_code": affiliate_code if affiliate_code else None,
            },
        )

    amount_dollars = (
        plan.price_yearly if billing_period == BillingPeriod.YEARLY else plan.price_monthly
    )
    amount_cents = int(round(float(amount_dollars or 0) * 100))

    await audit_logger.log_subscription_created(
        user_id=user.id,
        subscription_id=subscription.id,
        plan_id=plan.id,
        plan_name=plan.display_name or plan.name,
        billing_period=billing_period.value,
        is_trial=internal_status == SubscriptionStatus.TRIAL,
        amount=amount_cents,
        lemonsqueezy_subscription_id=lemonsqueezy_subscription_id,
        metadata={
            "status": internal_status.value,
            "correlation_id": correlation_id,
            "event_id": webhook_data.get("event_id"),
        },
        db=db,
    )

    logger.info(
        "Successfully processed subscription_created webhook",
        operation="webhook_subscription_created",
        event_id=webhook_data.get("event_id"),
        subscription_id=str(subscription.id),
        user_id=str(user.id),
        plan_id=str(plan.id),
        status=internal_status.value,
        correlation_id=correlation_id,
    )

    # Return email task data for subscription_created email
    return {
        "send_email": True,
        "email_type": "subscription_created",
        "email_data": {
            "user_id": str(user.id),
            "user_email": user.email,
            # display_name is what the customer recognises ("Pro Plan"); name
            # is the internal slug and read as "Welcome to pro!" in the email.
            "plan_name": plan.display_name or plan.name,
            # price_monthly/price_yearly are Numeric(10, 2) in *dollars*, not
            # cents — dividing by 100 turned a $189.00 plan into $1.89.
            "plan_price": (
                f"${(plan.price_yearly if billing_period == BillingPeriod.YEARLY else plan.price_monthly) or 0:.2f}"
            ),
            "billing_period": billing_period.value,
            "features": plan.features_list,
            "subscription_id": str(subscription.id),
        },
    }


async def handle_subscription_updated(
    webhook_data: Dict[str, Any], webhook_event: WebhookEvent, db: AsyncSession
) -> Optional[Dict[str, Any]]:
    """
    Handle subscription_updated webhook event.

    This event fires when a subscription is updated (plan change, status change, etc.).

    Actions:
    1. Find existing subscription by lemonsqueezy_subscription_id
    2. Update subscription fields (status, plan, billing_period, etc.)
    3. Return email task data if significant change occurred

    Args:
        webhook_data: Parsed webhook data
        webhook_event: Database record for this webhook
        db: Database session

    Returns:
        Email task dict or None

    Raises:
        Exception: If subscription not found or database error
    """
    logger.info(
        "Processing subscription_updated webhook", extra={"event_id": webhook_data.get("event_id")}
    )

    # Extract subscription data
    sub_data = extract_subscription_data(webhook_data)
    lemonsqueezy_subscription_id = sub_data.get("subscription_id")
    lemonsqueezy_customer_id = sub_data.get("customer_id")
    lemonsqueezy_variant_id = sub_data.get("variant_id")
    user_email = sub_data.get("user_email")
    status = sub_data.get("status", "active")
    renews_at = sub_data.get("renews_at")
    ends_at = sub_data.get("ends_at")
    trial_ends_at = sub_data.get("trial_ends_at")
    cancelled = sub_data.get("cancelled", False)

    # Find existing subscription
    stmt = select(UserSubscription).where(
        UserSubscription.lemonsqueezy_subscription_id == lemonsqueezy_subscription_id
    )
    result = await db.execute(stmt)
    subscription = result.scalar_one_or_none()

    if not subscription:
        # Subscription doesn't exist yet - this can happen if subscription_updated arrives before subscription_created
        # or if subscription_created webhook was missed. Create the subscription now.
        logger.warning(
            f"Subscription {lemonsqueezy_subscription_id} not found in subscription_updated - creating it now",
            extra={
                "event_type": "subscription_updated",
                "subscription_id": lemonsqueezy_subscription_id,
            },
        )

        # Find user (same logic as subscription_created)
        user_identifier = get_user_identifier(webhook_data)
        user = None
        if user_identifier:
            try:
                user_id = UUID(user_identifier)
                stmt = select(Users).where(Users.id == user_id)
                result = await db.execute(stmt)
                user = result.scalar_one_or_none()
            except (ValueError, TypeError):
                pass

        if not user and user_email:
            stmt = select(Users).where(Users.email == user_email)
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()

        if not user:
            error_msg = f"User not found for subscription {lemonsqueezy_subscription_id}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Find plan by variant_id
        stmt = select(SubscriptionPlan).where(
            (SubscriptionPlan.lemonsqueezy_variant_id_monthly == lemonsqueezy_variant_id)
            | (SubscriptionPlan.lemonsqueezy_variant_id_yearly == lemonsqueezy_variant_id)
        )
        result = await db.execute(stmt)
        plan = result.scalar_one_or_none()

        if not plan:
            error_msg = f"Plan not found for variant_id {lemonsqueezy_variant_id}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Determine billing period
        billing_period = (
            BillingPeriod.YEARLY
            if plan.lemonsqueezy_variant_id_yearly == lemonsqueezy_variant_id
            else BillingPeriod.MONTHLY
        )

        # Map status
        status_map = {
            "on_trial": SubscriptionStatus.TRIAL,
            "active": SubscriptionStatus.ACTIVE,
            "paused": SubscriptionStatus.PAUSED,
            "past_due": SubscriptionStatus.PAST_DUE,
            "unpaid": SubscriptionStatus.PAST_DUE,
            "cancelled": SubscriptionStatus.CANCELLED,
            "expired": SubscriptionStatus.EXPIRED,
        }
        internal_status = status_map.get(status.lower(), SubscriptionStatus.ACTIVE)

        # IMPORTANT: Cancel any existing active/trial subscriptions for this user
        # This handles the case when user upgrades via a new checkout instead of upgrade endpoint
        existing_active_subs_stmt = select(UserSubscription).where(
            UserSubscription.user_id == user.id,
            UserSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL]),
            or_(
                UserSubscription.lemonsqueezy_subscription_id.is_(None),
                UserSubscription.lemonsqueezy_subscription_id != lemonsqueezy_subscription_id,
            ),
        )
        existing_active_result = await db.execute(existing_active_subs_stmt)
        existing_active_subs = existing_active_result.scalars().all()

        for old_sub in existing_active_subs:
            logger.info(
                f"Cancelling old subscription {old_sub.id} via subscription_updated webhook",
                extra={
                    "old_subscription_id": str(old_sub.id),
                    "new_lemonsqueezy_subscription_id": lemonsqueezy_subscription_id,
                    "user_id": str(user.id),
                },
            )
            old_sub.status = SubscriptionStatus.CANCELLED
            old_sub.cancelled_at = datetime.now(timezone.utc)
            old_sub.end_date = datetime.now(timezone.utc)
            old_sub.updated_at = datetime.now(timezone.utc)

        if existing_active_subs:
            await db.flush()

        # Create subscription
        now = datetime.now(timezone.utc)
        trial_end_date = (
            datetime.fromisoformat(trial_ends_at).replace(tzinfo=None) if trial_ends_at else None
        )

        subscription = UserSubscription(
            user_id=user.id,
            plan_id=plan.id,
            status=internal_status,
            billing_period=billing_period,
            start_date=now,
            trial_end_date=trial_end_date,
            lemonsqueezy_subscription_id=lemonsqueezy_subscription_id,
            lemonsqueezy_customer_id=lemonsqueezy_customer_id,
            lemonsqueezy_variant_id=lemonsqueezy_variant_id,
            renews_at=parse_provider_datetime(renews_at),
            current_api_calls=0,
            current_credits=plan.credits_per_month or 0,
            # `renews_at` from the provider is the authoritative period end;
            # fall back to a calendar month only when it is absent.
            credits_reset_date=parse_provider_datetime(renews_at) or add_months(utc_now_naive(), 1),
            usage_reset_date=parse_provider_datetime(renews_at) or add_months(utc_now_naive(), 1),
            created_at=now,
            updated_at=now,
        )

        _stamp_card_details(subscription, sub_data)

        db.add(subscription)
        await db.flush()

        logger.info(
            f"Created subscription {subscription.id} via subscription_updated webhook",
            extra={
                "subscription_id": str(subscription.id),
                "user_id": str(user.id),
                "plan_id": str(plan.id),
            },
        )

        # Update user's provider_customer_id if not set
        if not user.provider_customer_id and lemonsqueezy_customer_id:
            user.provider_customer_id = lemonsqueezy_customer_id
            await db.flush()

        # Return early - subscription created, nothing to update
        return None

    # Map status
    status_map = {
        "on_trial": SubscriptionStatus.TRIAL,
        "active": SubscriptionStatus.ACTIVE,
        "paused": SubscriptionStatus.PAUSED,
        "past_due": SubscriptionStatus.PAST_DUE,
        "unpaid": SubscriptionStatus.PAST_DUE,
        "cancelled": SubscriptionStatus.CANCELLED,
        "expired": SubscriptionStatus.EXPIRED,
    }
    internal_status = status_map.get(status.lower(), SubscriptionStatus.ACTIVE)

    # Check if plan changed (variant_id changed)
    plan_changed = False
    old_plan = None
    new_plan = None
    old_billing_period = subscription.billing_period
    if lemonsqueezy_variant_id and subscription.lemonsqueezy_variant_id != lemonsqueezy_variant_id:
        # Fetch current plan before updating plan_id
        if subscription.plan_id:
            old_plan_stmt = select(SubscriptionPlan).where(
                SubscriptionPlan.id == subscription.plan_id
            )
            old_plan_result = await db.execute(old_plan_stmt)
            old_plan = old_plan_result.scalar_one_or_none()

        # Find new plan
        stmt = select(SubscriptionPlan).where(
            (SubscriptionPlan.lemonsqueezy_variant_id_monthly == lemonsqueezy_variant_id)
            | (SubscriptionPlan.lemonsqueezy_variant_id_yearly == lemonsqueezy_variant_id)
        )
        result = await db.execute(stmt)
        new_plan = result.scalar_one_or_none()

        if new_plan:
            subscription.plan_id = new_plan.id
            subscription.lemonsqueezy_variant_id = lemonsqueezy_variant_id
            # Update billing period
            subscription.billing_period = (
                BillingPeriod.YEARLY
                if new_plan.lemonsqueezy_variant_id_yearly == lemonsqueezy_variant_id
                else BillingPeriod.MONTHLY
            )
            if new_plan.credits_per_month is not None:
                subscription.current_credits = new_plan.credits_per_month
                subscription.credits_reset_date = parse_provider_datetime(renews_at) or add_months(
                    utc_now_naive(), 1
                )
            plan_changed = True
            logger.info(f"Subscription plan changed to {new_plan.name}")

    # Check for trial to paid conversion
    trial_converted = False
    if (
        subscription.status == SubscriptionStatus.TRIAL
        and internal_status == SubscriptionStatus.ACTIVE
        and subscription.trial_end_date
    ):
        trial_converted = True
        trial_service = TrialService(db)

        # Get payment amount from webhook if available
        payment_amount = None
        attributes = webhook_data.get("data", {}).get("attributes", {})
        if attributes.get("first_subscription_item"):
            first_item = attributes.get("first_subscription_item", {})
            payment_amount = first_item.get("price")

        # Track the conversion
        try:
            await trial_service.track_trial_conversion(
                user_id=subscription.user_id,
                subscription_id=subscription.id,
                trial_started_at=subscription.start_date,
                trial_ended_at=subscription.trial_end_date,
                plan_id=subscription.plan_id,
                billing_period=subscription.billing_period.value,
                payment_amount=payment_amount,
                metadata={
                    "webhook_event_id": webhook_data.get("event_id"),
                    "lemonsqueezy_subscription_id": lemonsqueezy_subscription_id,
                    "conversion_source": "automatic",
                },
            )
            logger.info(
                f"Trial conversion tracked for subscription {subscription.id}",
                extra={
                    "subscription_id": str(subscription.id),
                    "user_id": str(subscription.user_id),
                },
            )
        except Exception as e:
            # Log error but don't fail the webhook
            logger.error(
                f"Failed to track trial conversion: {str(e)}",
                extra={"subscription_id": str(subscription.id), "error": str(e)},
            )

    # Update subscription fields.
    #
    # Status mirrors LemonSqueezy immediately (including flipping to CANCELLED
    # the instant the user cancels, even for "at period end" cancellations) so
    # the UI reflects it right away and a repeat cancel finds no active
    # subscription. Credits/usage limits are NOT gated on this status directly -
    # they key off `subscription_grants_access()` (status ACTIVE/TRIAL, OR
    # CANCELLED with `end_date` still in the future), so the user keeps their
    # credits until `end_date` regardless of the status flip here.
    end_date_dt = datetime.fromisoformat(ends_at).replace(tzinfo=None) if ends_at else None
    # Cancelled during a payment retry: access ends at the grace deadline, not
    # at Lemon Squeezy's ends_at.
    deadline = retry_deadline(subscription)
    if internal_status == SubscriptionStatus.CANCELLED and deadline is not None:
        end_date_dt = deadline

    subscription.status = internal_status
    if internal_status == SubscriptionStatus.CANCELLED and end_date_dt is not None:
        subscription.cancel_at_period_end = True

    subscription.renews_at = parse_provider_datetime(renews_at)
    subscription.end_date = end_date_dt
    subscription.trial_end_date = (
        datetime.fromisoformat(trial_ends_at).replace(tzinfo=None) if trial_ends_at else None
    )
    subscription.cancelled_at = (
        datetime.now(timezone.utc)
        if cancelled and not subscription.cancelled_at
        else subscription.cancelled_at
    )
    subscription.updated_at = datetime.now(timezone.utc)
    _stamp_card_details(subscription, sub_data)

    await db.flush()

    logger.info(
        f"Successfully updated subscription {subscription.id}",
        extra={
            "subscription_id": str(subscription.id),
            "new_status": internal_status.value,
            "plan_changed": plan_changed,
            "trial_converted": trial_converted,
        },
    )

    if plan_changed and new_plan:
        user_stmt = select(Users).where(Users.id == subscription.user_id)
        user_res = await db.execute(user_stmt)
        sub_user = user_res.scalar_one_or_none()

        old_plan_name = (old_plan.display_name or old_plan.name) if old_plan else "Previous Plan"
        new_plan_name = new_plan.display_name or new_plan.name

        old_price_val = (
            (
                old_plan.price_yearly
                if old_billing_period == BillingPeriod.YEARLY
                else old_plan.price_monthly
            )
            if old_plan
            else 0
        )
        new_price_val = (
            (
                new_plan.price_yearly
                if subscription.billing_period == BillingPeriod.YEARLY
                else new_plan.price_monthly
            )
            if new_plan
            else 0
        )

        old_period_str = old_billing_period.value if old_billing_period else "month"
        new_period_str = (
            subscription.billing_period.value if subscription.billing_period else "month"
        )

        old_price_str = f"${float(old_price_val or 0):.2f}/{old_period_str}"
        new_price_str = f"${float(new_price_val or 0):.2f}/{new_period_str}"

        target_date = subscription.renews_at or subscription.end_date or datetime.now(timezone.utc)
        date_str = target_date.strftime("%B %d, %Y")

        customer_portal_url = None
        data_attrs = webhook_data.get("data", {}).get("attributes", {}) or {}
        if data_attrs.get("urls") and isinstance(data_attrs["urls"], dict):
            customer_portal_url = data_attrs["urls"].get("customer_portal")

        is_downgrade = (
            (float(new_plan.price_monthly or 0) < float(old_plan.price_monthly or 0))
            if old_plan
            else False
        )
        email_type = "subscription_downgraded" if is_downgrade else "subscription_upgraded"

        if is_downgrade:
            await audit_logger.log_subscription_downgraded(
                user_id=subscription.user_id,
                subscription_id=subscription.id,
                old_plan_name=old_plan_name,
                new_plan_name=new_plan_name,
                old_billing_period=old_period_str,
                new_billing_period=new_period_str,
                metadata={
                    "old_price": old_price_str,
                    "new_price": new_price_str,
                    "effective_date": date_str,
                },
                db=db,
            )
        else:
            await audit_logger.log_subscription_upgraded(
                user_id=subscription.user_id,
                subscription_id=subscription.id,
                old_plan_name=old_plan_name,
                new_plan_name=new_plan_name,
                old_billing_period=old_period_str,
                new_billing_period=new_period_str,
                metadata={
                    "old_price": old_price_str,
                    "new_price": new_price_str,
                    "effective_date": date_str,
                },
                db=db,
            )

        return {
            "send_email": True,
            "email_type": email_type,
            "email_data": {
                "user_id": str(subscription.user_id),
                "user_email": sub_user.email if sub_user else user_email,
                "old_plan_name": old_plan_name,
                "new_plan_name": new_plan_name,
                "old_price": old_price_str,
                "new_price": new_price_str,
                "billing_date": date_str,
                "effective_date": date_str,
                "customer_portal_url": customer_portal_url,
                "subscription_id": str(subscription.id),
            },
        }

    await audit_logger.log_subscription_updated(
        user_id=subscription.user_id,
        subscription_id=subscription.id,
        changes={
            "status": {"to": internal_status.value},
        },
        metadata={
            "trial_converted": trial_converted,
            "card_brand": sub_data.get("card_brand"),
            "card_last_four": sub_data.get("card_last_four"),
        },
        db=db,
    )

    return None


async def handle_subscription_cancelled(
    webhook_data: Dict[str, Any], webhook_event: WebhookEvent, db: AsyncSession
) -> Optional[Dict[str, Any]]:
    """
    Handle subscription_cancelled webhook event.

    LemonSqueezy fires this the instant the user (or admin) cancels, even when
    the cancellation is "at period end" - `ends_at` still points to the future
    renewal date.

    Actions:
    1. Find subscription
    2. Flip status to CANCELLED immediately (so the UI reflects it right away
       and a repeat cancel attempt finds no active subscription) and record
       cancel_at_period_end + cancelled_at + end_date. Credits/usage limits
       are NOT gated on this status - they key off `subscription_grants_access()`
       (status ACTIVE/TRIAL, OR CANCELLED with `end_date` still in the future),
       so the user keeps their credits until `end_date`.
    3. Return email task data for cancellation email

    Args:
        webhook_data: Parsed webhook data
        webhook_event: Database record for this webhook
        db: Database session

    Returns:
        Email task dict or None
    """
    logger.info(
        "Processing subscription_cancelled webhook",
        extra={"event_id": webhook_data.get("event_id")},
    )

    sub_data = extract_subscription_data(webhook_data)
    lemonsqueezy_subscription_id = sub_data.get("subscription_id")
    ends_at = sub_data.get("ends_at")

    # Find subscription
    stmt = select(UserSubscription).where(
        UserSubscription.lemonsqueezy_subscription_id == lemonsqueezy_subscription_id
    )
    result = await db.execute(stmt)
    subscription = result.scalar_one_or_none()

    if not subscription:
        error_msg = f"Subscription {lemonsqueezy_subscription_id} not found"
        logger.error(error_msg)
        raise ValueError(error_msg)

    now = datetime.now(timezone.utc)
    end_date = datetime.fromisoformat(ends_at).replace(tzinfo=None) if ends_at else None
    # Cancelled during a payment retry: access ends at the grace deadline, not
    # at Lemon Squeezy's ends_at.
    end_date = retry_deadline(subscription) or end_date

    # Update subscription
    subscription.status = SubscriptionStatus.CANCELLED
    subscription.cancelled_at = now
    subscription.cancel_at_period_end = True
    subscription.end_date = end_date
    subscription.updated_at = now

    await db.flush()

    logger.info(
        f"Successfully processed subscription_cancelled webhook for subscription {subscription.id}",
        extra={"subscription_id": str(subscription.id), "status": subscription.status.value},
    )

    # Fetch user + plan for the cancellation email
    stmt = select(Users).where(Users.id == subscription.user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        logger.warning(f"User {subscription.user_id} not found - skipping cancellation email")
        return None

    stmt = select(SubscriptionPlan).where(SubscriptionPlan.id == subscription.plan_id)
    result = await db.execute(stmt)
    plan = result.scalar_one_or_none()

    await audit_logger.log_subscription_cancelled(
        user_id=subscription.user_id,
        subscription_id=subscription.id,
        plan_name=(plan.display_name or plan.name) if plan else "Your Plan",
        reason=None,
        cancelled_by_admin=False,
        metadata={
            "end_date": end_date.isoformat() if end_date else None,
            "cancel_at_period_end": True,
        },
        db=db,
    )

    return {
        "send_email": True,
        "email_type": "subscription_cancelled",
        "email_data": {
            "user_id": str(user.id),
            "user_email": user.email,
            "plan_name": (plan.display_name or plan.name) if plan else "Your Plan",
            "end_date": end_date.strftime("%B %d, %Y")
            if end_date
            else "the end of your billing period",
        },
    }


async def handle_subscription_expired(
    webhook_data: Dict[str, Any], webhook_event: WebhookEvent, db: AsyncSession
) -> Optional[Dict[str, Any]]:
    """
    Handle subscription_expired webhook event.

    This event fires when a subscription expires (trial ended, payment failed, etc.).

    Actions:
    1. Find subscription
    2. Update status to EXPIRED
    3. Return email task data for expiration email

    Args:
        webhook_data: Parsed webhook data
        webhook_event: Database record for this webhook
        db: Database session

    Returns:
        Email task dict or None
    """
    logger.info(
        "Processing subscription_expired webhook", extra={"event_id": webhook_data.get("event_id")}
    )

    sub_data = extract_subscription_data(webhook_data)
    lemonsqueezy_subscription_id = sub_data.get("subscription_id")

    # Find subscription
    stmt = select(UserSubscription).where(
        UserSubscription.lemonsqueezy_subscription_id == lemonsqueezy_subscription_id
    )
    result = await db.execute(stmt)
    subscription = result.scalar_one_or_none()

    if not subscription:
        error_msg = f"Subscription {lemonsqueezy_subscription_id} not found"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Update subscription
    subscription.status = SubscriptionStatus.EXPIRED
    subscription.end_date = datetime.now(timezone.utc)
    subscription.updated_at = datetime.now(timezone.utc)
    await db.flush()

    await audit_logger.log_subscription_expired(
        user_id=subscription.user_id,
        subscription_id=subscription.id,
        metadata={"event_id": webhook_data.get("event_id")},
        db=db,
    )

    # TODO: Return email task data for expiration email
    logger.info(
        f"Successfully expired subscription {subscription.id}",
        extra={"subscription_id": str(subscription.id)},
    )

    # Return None for now - email sending not implemented yet
    return None


async def handle_subscription_payment_success(
    webhook_data: Dict[str, Any], webhook_event: WebhookEvent, db: AsyncSession
) -> Optional[Dict[str, Any]]:
    """
    Handle subscription_payment_success webhook event.

    This event fires when a subscription payment succeeds.

    Actions:
    1. Find subscription
    2. Update status to ACTIVE (if was TRIAL or SUSPENDED)
    3. Reset usage counters for new billing cycle
    4. Update next renewal date
    5. Return email task data for payment success email with receipt

    Args:
        webhook_data: Parsed webhook data
        webhook_event: Database record for this webhook
        db: Database session

    Returns:
        Email task dict or None
    """
    logger.info(
        "Processing subscription_payment_success webhook",
        extra={"event_id": webhook_data.get("event_id")},
    )

    sub_data = extract_subscription_data(webhook_data)
    lemonsqueezy_subscription_id = sub_data.get("subscription_id")
    renews_at = sub_data.get("renews_at")

    # Find subscription
    stmt = select(UserSubscription).where(
        UserSubscription.lemonsqueezy_subscription_id == lemonsqueezy_subscription_id
    )
    result = await db.execute(stmt)
    subscription = result.scalar_one_or_none()

    if not subscription:
        # Payment success arrived before subscription_created - log and skip
        # The subscription_created or subscription_updated webhook should create it
        logger.warning(
            f"Subscription {lemonsqueezy_subscription_id} not found in payment_success - will be created by subscription_created/updated webhook",
            extra={
                "event_type": "subscription_payment_success",
                "subscription_id": lemonsqueezy_subscription_id,
            },
        )
        # Don't raise error - this is normal webhook ordering issue
        return None

    # Update subscription - activate if was trial or suspended
    if subscription.status in [SubscriptionStatus.TRIAL, SubscriptionStatus.PAST_DUE]:
        subscription.status = SubscriptionStatus.ACTIVE

    # Update renewal date (invoices don't carry one; keep the current value)
    parsed_renews_at = parse_provider_datetime(renews_at)
    if parsed_renews_at:
        subscription.renews_at = parsed_renews_at

    # Reset usage + credit counters for the new billing cycle. The provider's
    # `renews_at` is the authoritative next period end; fall back to a calendar
    # month only when it is absent.
    next_period_end = parsed_renews_at or add_months(utc_now_naive(), 1)
    subscription.current_api_calls = 0
    subscription.usage_reset_date = next_period_end

    # Replenish monthly credits for paid plans so current_credits and
    # credits_reset_date stay in step with the billing period.
    plan_stmt = select(SubscriptionPlan).where(SubscriptionPlan.id == subscription.plan_id)
    plan_row = (await db.execute(plan_stmt)).scalar_one_or_none()
    if plan_row and not plan_row.is_trial_plan and plan_row.credits_per_month is not None:
        subscription.current_credits = plan_row.credits_per_month
        subscription.credits_reset_date = next_period_end

    subscription.updated_at = datetime.now(timezone.utc)
    _stamp_card_details(subscription, sub_data)

    await db.flush()

    # The invoice this event carries holds what was actually charged, in cents
    # — `total` alongside `total_formatted: "$189.00"`. It was previously read
    # as unavailable, so both the audit trail and the receipt email recorded
    # every payment as $0.00. The plan price is only a fallback, and needs
    # converting because it is stored in dollars.
    invoice_attributes = webhook_data.get("data", {}).get("attributes", {}) or {}
    amount_cents = int(invoice_attributes.get("total") or 0)
    if not amount_cents and plan_row:
        plan_price = (
            plan_row.price_monthly
            if subscription.billing_period.value == "monthly"
            else plan_row.price_yearly
        )
        amount_cents = int(round(float(plan_price or 0) * 100))

    # Audit log
    await audit_logger.log_payment_succeeded(
        user_id=subscription.user_id,
        subscription_id=subscription.id,
        amount=amount_cents,
        currency=invoice_attributes.get("currency") or "USD",
        lemonsqueezy_payment_id=lemonsqueezy_subscription_id,
        metadata={"renews_at": renews_at, "is_renewal": True},
        db=db,
    )

    # Return email task data for payment success email
    return {
        "send_email": True,
        "email_type": "payment_succeeded",
        "email_data": {
            "user_id": str(subscription.user_id),
            "plan_name": (
                (subscription.plan.display_name or subscription.plan.name)
                if subscription.plan
                else "Your Plan"
            ),
            "amount_cents": amount_cents,
            "payment_date": datetime.now(timezone.utc).strftime("%B %d, %Y"),
            "next_billing_date": subscription.renews_at.strftime("%B %d, %Y")
            if subscription.renews_at
            else "N/A",
            "subscription_id": str(subscription.id),
        },
    }


GRACE_PERIOD_DAYS = 7


def grace_deadline(subscription: UserSubscription, now: datetime) -> Optional[datetime]:
    """When access ends for a failed renewal: 7 days after the retry began.

    Lemon Squeezy sends subscription_payment_failed for each of its recovery
    attempts, for longer than our grace period. A subscription already in its
    retry keeps the deadline it got at the first failure, so later attempts
    cannot stretch it; an EXPIRED one (the grace job ended its retry) gets none,
    so a late attempt cannot reopen access. Any other status starts a new one.
    """
    if subscription.status == SubscriptionStatus.EXPIRED:
        return None
    if subscription.status in PAYMENT_RETRY_STATUSES and subscription.grace_period_end:
        return subscription.grace_period_end
    return now + timedelta(days=GRACE_PERIOD_DAYS)


async def handle_subscription_payment_failed(
    webhook_data: Dict[str, Any], webhook_event: WebhookEvent, db: AsyncSession
) -> Optional[Dict[str, Any]]:
    """
    Handle subscription_payment_failed webhook event.

    This event fires when a subscription payment fails.

    Actions:
    1. Find subscription
    2. Set status to SUSPENDED (grace period)
    3. Calculate and set grace period (7 days)
    4. Track payment failure timestamp
    5. Return email task data to be sent AFTER commit

    Grace Period Behavior:
    - User retains access during grace period (7 days)
    - LemonSqueezy will automatically retry payment
    - Dunning emails sent at 1, 3, 6 days (Task 3.4.2)
    - Auto-suspend after grace period (Task 3.4.3)

    Args:
        webhook_data: Parsed webhook data
        webhook_event: Database record for this webhook
        db: Database session

    Returns:
        Email task dict with email data to send after commit
    """
    logger.info(
        "Processing subscription_payment_failed webhook",
        extra={"event_id": webhook_data.get("event_id")},
    )

    sub_data = extract_subscription_data(webhook_data)
    lemonsqueezy_subscription_id = sub_data.get("subscription_id")

    # Find subscription
    stmt = select(UserSubscription).where(
        UserSubscription.lemonsqueezy_subscription_id == lemonsqueezy_subscription_id
    )
    result = await db.execute(stmt)
    subscription = result.scalar_one_or_none()

    if not subscription:
        error_msg = f"Subscription {lemonsqueezy_subscription_id} not found"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Get user for email notification
    stmt = select(Users).where(Users.id == subscription.user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        error_msg = f"User {subscription.user_id} not found"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Get plan details for email
    stmt = select(SubscriptionPlan).where(SubscriptionPlan.id == subscription.plan_id)
    result = await db.execute(stmt)
    plan = result.scalar_one_or_none()

    # Grace period: 7 days from the first failure of this retry
    now = datetime.now(timezone.utc)
    grace_period_days = GRACE_PERIOD_DAYS
    grace_period_end = grace_deadline(subscription, now)
    if grace_period_end is None:
        logger.info(
            f"Payment failed for expired subscription {subscription.id}: its grace period "
            "already ran out, so it stays expired"
        )
        return

    # Update subscription - set to SUSPENDED during grace period
    subscription.status = SubscriptionStatus.SUSPENDED
    subscription.grace_period_end = grace_period_end

    # Only set payment_failed_at if not already set (track first failure)
    if not subscription.payment_failed_at:
        subscription.payment_failed_at = now

    subscription.updated_at = now

    await db.flush()

    logger.info(
        f"Payment failed for subscription {subscription.id} - grace period set until {grace_period_end.isoformat()}",
        extra={
            "subscription_id": str(subscription.id),
            "grace_period_end": grace_period_end.isoformat(),
            "grace_period_days": grace_period_days,
        },
    )

    # What the failed charge was for, in cents. The subscription item carries
    # it; the plan price is the fallback and is stored in dollars, so it needs
    # converting. Extracted before the audit entry so both the trail and the
    # email report the same figure instead of a hardcoded zero.
    attributes = webhook_data.get("data", {}).get("attributes", {}) or {}
    first_subscription_item = attributes.get("first_subscription_item", {}) or {}
    amount_cents = int(first_subscription_item.get("price") or 0)
    if not amount_cents and plan:
        plan_price = (
            plan.price_monthly
            if subscription.billing_period.value == "monthly"
            else plan.price_yearly
        )
        amount_cents = int(round(float(plan_price or 0) * 100))

    # Audit log
    await audit_logger.log_payment_failed(
        user_id=subscription.user_id,
        subscription_id=subscription.id,
        amount=amount_cents,
        failure_reason="Payment failed",
        lemonsqueezy_payment_id=lemonsqueezy_subscription_id,
        metadata={"grace_period_end": grace_period_end.isoformat()},
        db=db,
    )

    # Calculate retry date (LemonSqueezy typically retries in 3 days)
    retry_date = (now + timedelta(days=3)).strftime("%B %d, %Y")

    logger.warning(
        f"Payment failed for subscription {subscription.id} - user has access until {grace_period_end.isoformat()}",
        extra={
            "subscription_id": str(subscription.id),
            "user_id": str(user.id),
            "grace_period_end": grace_period_end.isoformat(),
        },
    )

    # IMPORTANT: Return email data to be sent AFTER commit
    # This prevents sending emails before database changes are committed
    return {
        "send_email": True,
        "email_type": "payment_failed",
        "email_data": {
            "user_id": str(user.id),
            "user_email": user.email,
            "plan_name": (plan.display_name or plan.name) if plan else "Your Plan",
            "amount_cents": amount_cents,
            "retry_date": retry_date,
            "subscription_id": str(subscription.id),
        },
    }


async def handle_subscription_payment_recovered(
    webhook_data: Dict[str, Any], webhook_event: WebhookEvent, db: AsyncSession
) -> Optional[Dict[str, Any]]:
    """
    Handle subscription_payment_recovered webhook event.

    This event fires when a previously failed payment is successfully recovered.

    Actions:
    1. Find subscription
    2. Restore status to ACTIVE
    3. Clear grace period tracking (payment resolved)
    4. Update renewal date
    5. Return email task data to be sent AFTER commit

    Recovery Process:
    - Payment fails → SUSPENDED status with grace period
    - Dunning emails sent (days 1, 3, 6)
    - User updates payment method OR automatic retry succeeds
    - This handler → Restore to ACTIVE, clear grace period, return email data

    Args:
        webhook_data: Parsed webhook data
        webhook_event: Database record for this webhook
        db: Database session

    Returns:
        Email task dict with email data to send after commit
    """
    logger.info(
        "Processing subscription_payment_recovered webhook",
        extra={"event_id": webhook_data.get("event_id")},
    )

    sub_data = extract_subscription_data(webhook_data)
    lemonsqueezy_subscription_id = sub_data.get("subscription_id")
    renews_at = sub_data.get("renews_at")

    # Find subscription
    stmt = select(UserSubscription).where(
        UserSubscription.lemonsqueezy_subscription_id == lemonsqueezy_subscription_id
    )
    result = await db.execute(stmt)
    subscription = result.scalar_one_or_none()

    if not subscription:
        error_msg = f"Subscription {lemonsqueezy_subscription_id} not found"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Get user for email
    stmt = select(Users).where(Users.id == subscription.user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        error_msg = f"User {subscription.user_id} not found"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Get plan details for email
    stmt = select(SubscriptionPlan).where(SubscriptionPlan.id == subscription.plan_id)
    result = await db.execute(stmt)
    plan = result.scalar_one_or_none()

    # Track previous status for logging
    previous_status = subscription.status

    # Update subscription - restore to ACTIVE
    now = datetime.now(timezone.utc)
    subscription.status = SubscriptionStatus.ACTIVE
    # Invoices don't carry a renewal date; keep the current value.
    if renews_at:
        subscription.renews_at = parse_provider_datetime(renews_at)
    subscription.updated_at = now

    # Clear grace period tracking (payment resolved)
    subscription.grace_period_end = None
    # Keep payment_failed_at for analytics/history

    await db.flush()

    logger.info(
        f"Payment recovered for subscription {subscription.id} - restored from {previous_status.value} to ACTIVE",
        extra={
            "subscription_id": str(subscription.id),
            "user_id": str(user.id),
            "previous_status": previous_status.value,
            "new_status": "active",
        },
    )

    # Extract payment details from webhook for email
    attributes = webhook_data.get("data", {}).get("attributes", {})
    first_subscription_item = attributes.get("first_subscription_item", {})

    # Format amount
    amount_cents = first_subscription_item.get("price", 0)

    if not amount_cents and plan:
        # Fallback to the plan price. price_monthly/price_yearly are
        # Numeric(10, 2) in *dollars* while this variable — and the email that
        # reads it — are in cents, so the conversion is not optional: without
        # it a $189.00 plan reached the customer as $1.89.
        plan_price = (
            plan.price_monthly
            if subscription.billing_period.value == "monthly"
            else plan.price_yearly
        )
        amount_cents = int(round(float(plan_price or 0) * 100))

    # Format dates
    recovery_date = now.strftime("%B %d, %Y")
    next_billing_date = (
        subscription.renews_at.strftime("%B %d, %Y") if subscription.renews_at else "N/A"
    )

    await audit_logger.log_payment_recovered(
        user_id=subscription.user_id,
        subscription_id=subscription.id,
        metadata={
            "recovery_date": recovery_date,
            "next_billing_date": next_billing_date,
            "amount_cents": amount_cents,
        },
        db=db,
    )

    # IMPORTANT: Return email data to be sent AFTER commit
    # This prevents sending emails before database changes are committed
    return {
        "send_email": True,
        "email_type": "payment_recovered",
        "email_data": {
            "user_id": str(user.id),
            "user_email": user.email,
            "user_name": user.full_name or user.display_name or user.email,
            "plan_name": (plan.display_name or plan.name) if plan else "Your Plan",
            "amount_cents": amount_cents,
            "recovery_date": recovery_date,
            "next_billing_date": next_billing_date,
            "subscription_id": str(subscription.id),
        },
    }


async def handle_subscription_paused(
    webhook_data: Dict[str, Any], webhook_event: WebhookEvent, db: AsyncSession
) -> Optional[Dict[str, Any]]:
    """
    Handle subscription_paused webhook event.

    This event fires when a subscription is paused by admin or user.

    Actions:
    1. Find subscription
    2. Update status to PAUSED
    3. Return email task data for paused notification email

    Args:
        webhook_data: Parsed webhook data
        webhook_event: Database record for this webhook
        db: Database session

    Returns:
        Email task dict or None
    """
    logger.info(
        "Processing subscription_paused webhook", extra={"event_id": webhook_data.get("event_id")}
    )

    sub_data = extract_subscription_data(webhook_data)
    lemonsqueezy_subscription_id = sub_data.get("subscription_id")
    resumes_at = sub_data.get("resumes_at")

    # Find subscription
    stmt = select(UserSubscription).where(
        UserSubscription.lemonsqueezy_subscription_id == lemonsqueezy_subscription_id
    )
    result = await db.execute(stmt)
    subscription = result.scalar_one_or_none()

    if not subscription:
        error_msg = f"Subscription {lemonsqueezy_subscription_id} not found"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Update subscription to PAUSED
    subscription.status = SubscriptionStatus.PAUSED
    subscription.updated_at = datetime.now(timezone.utc)

    await db.flush()

    await audit_logger.log_subscription_paused(
        user_id=subscription.user_id,
        subscription_id=subscription.id,
        resumes_at=parse_provider_datetime(resumes_at) if resumes_at else None,
        db=db,
    )

    # TODO: Return email task data for subscription paused email
    logger.info(
        f"Successfully paused subscription {subscription.id}",
        extra={"subscription_id": str(subscription.id), "resumes_at": resumes_at},
    )

    # Return None for now - email sending not implemented yet
    return None


async def handle_subscription_resumed(
    webhook_data: Dict[str, Any], webhook_event: WebhookEvent, db: AsyncSession
) -> Optional[Dict[str, Any]]:
    """
    Handle subscription_resumed webhook event.

    This event fires when a paused subscription is resumed.

    Actions:
    1. Find subscription
    2. Update status to ACTIVE
    3. Update renewal dates
    4. Return email task data for resumed notification email

    Args:
        webhook_data: Parsed webhook data
        webhook_event: Database record for this webhook
        db: Database session

    Returns:
        Email task dict or None
    """
    logger.info(
        "Processing subscription_resumed webhook", extra={"event_id": webhook_data.get("event_id")}
    )

    sub_data = extract_subscription_data(webhook_data)
    lemonsqueezy_subscription_id = sub_data.get("subscription_id")
    renews_at = sub_data.get("renews_at")

    # Find subscription
    stmt = select(UserSubscription).where(
        UserSubscription.lemonsqueezy_subscription_id == lemonsqueezy_subscription_id
    )
    result = await db.execute(stmt)
    subscription = result.scalar_one_or_none()

    if not subscription:
        error_msg = f"Subscription {lemonsqueezy_subscription_id} not found"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Update subscription - resume to ACTIVE
    subscription.status = SubscriptionStatus.ACTIVE
    subscription.renews_at = parse_provider_datetime(renews_at)
    subscription.updated_at = datetime.now(timezone.utc)

    await db.flush()

    await audit_logger.log_subscription_resumed(
        user_id=subscription.user_id,
        subscription_id=subscription.id,
        metadata={"renews_at": renews_at},
        db=db,
    )

    # TODO: Return email task data for subscription resumed email
    logger.info(
        f"Successfully resumed subscription {subscription.id}",
        extra={"subscription_id": str(subscription.id)},
    )

    # Return None for now - email sending not implemented yet
    return None
