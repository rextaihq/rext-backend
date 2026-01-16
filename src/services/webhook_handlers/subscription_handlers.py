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
3. Sends email notifications
4. Logs actions
"""

from typing import Dict, Any
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.api.models.subscription_models.subscriptions import (
    UserSubscription,
    SubscriptionStatus,
    BillingPeriod
)
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.webhooks import WebhookEvent
from src.api.models.subscription_models.discount_usage import DiscountUsage
from src.api.models.subscription_models.trial_conversions import TrialConversion
from src.api.models.user_models.users import Users
from src.utils.lemonsqueezy_webhook import extract_subscription_data, get_user_identifier
from src.services.audit_logger import audit_logger
from src.utils.logger import logger
from src.services.trial_service import TrialService
from src.api.lib.sentry_config import (
    capture_payment_exception,
    add_payment_breadcrumb,
    set_payment_context,
    alert_subscription_creation_failure,
)
from src.api.lib.logging_config import (
    log_payment_timing,
    generate_payment_correlation_id,
)


async def handle_subscription_created(
    webhook_data: Dict[str, Any],
    webhook_event: WebhookEvent,
    db: AsyncSession
) -> None:
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
    6. Send subscription_created email

    Args:
        webhook_data: Parsed webhook data
        webhook_event: Database record for this webhook
        db: Database session

    Raises:
        Exception: If user not found, plan not found, or database error
    """
    # Generate correlation ID for tracking (Phase 4, Task 4.2.2)
    correlation_id = generate_payment_correlation_id()

    logger.info(
        "Processing subscription_created webhook",
        operation="webhook_subscription_created",
        event_id=webhook_data.get("event_id"),
        correlation_id=correlation_id
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
        }
    )

    add_payment_breadcrumb(
        "Processing subscription_created webhook",
        operation="webhook",
        data={
            "event_id": webhook_data.get("event_id"),
            "subscription_id": sub_data.get("subscription_id"),
        }
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
        logger.error(error_msg, extra={
            "user_identifier": user_identifier,
            "user_email": user_email
        })

        # Trigger critical alert (Phase 4, Task 4.2.3)
        alert_subscription_creation_failure(
            user_id=user_identifier or user_email or "unknown",
            variant_id=lemonsqueezy_variant_id,
            error_message=error_msg,
            event_id=webhook_data.get("event_id")
        )

        raise ValueError(error_msg)

    # Find subscription plan by LemonSqueezy variant_id
    stmt = select(SubscriptionPlan).where(
        (SubscriptionPlan.lemonsqueezy_variant_id_monthly == lemonsqueezy_variant_id) |
        (SubscriptionPlan.lemonsqueezy_variant_id_yearly == lemonsqueezy_variant_id)
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
            event_id=webhook_data.get("event_id")
        )

        raise ValueError(error_msg)

    # Determine billing period based on variant
    billing_period = BillingPeriod.YEARLY if plan.lemonsqueezy_variant_id_yearly == lemonsqueezy_variant_id else BillingPeriod.MONTHLY

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
            extra={"subscription_id": str(existing_sub.id)}
        )
        # Update existing subscription
        existing_sub.status = internal_status
        existing_sub.plan_id = plan.id
        existing_sub.billing_period = billing_period
        existing_sub.lemonsqueezy_customer_id = lemonsqueezy_customer_id
        existing_sub.lemonsqueezy_variant_id = lemonsqueezy_variant_id
        existing_sub.trial_end_date = datetime.fromisoformat(trial_ends_at).replace(tzinfo=None) if trial_ends_at else None
        existing_sub.updated_at = datetime.utcnow()
        await db.flush()
        subscription = existing_sub
    else:
        # IMPORTANT: Cancel any existing active/trial subscriptions for this user
        # This handles the case when user upgrades via a new checkout instead of upgrade endpoint
        existing_active_subs_stmt = select(UserSubscription).where(
            UserSubscription.user_id == user.id,
            UserSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL]),
            UserSubscription.lemonsqueezy_subscription_id != lemonsqueezy_subscription_id
        )
        existing_active_result = await db.execute(existing_active_subs_stmt)
        existing_active_subs = existing_active_result.scalars().all()
        
        for old_sub in existing_active_subs:
            logger.info(
                f"Cancelling old subscription {old_sub.id} (LemonSqueezy: {old_sub.lemonsqueezy_subscription_id}) "
                f"as user is now on new subscription {lemonsqueezy_subscription_id}",
                extra={
                    "old_subscription_id": str(old_sub.id),
                    "new_lemonsqueezy_subscription_id": lemonsqueezy_subscription_id,
                    "user_id": str(user.id)
                }
            )
            old_sub.status = SubscriptionStatus.CANCELLED
            old_sub.cancelled_at = datetime.utcnow()
            old_sub.end_date = datetime.utcnow()
            old_sub.updated_at = datetime.utcnow()
        
        if existing_active_subs:
            await db.flush()
            logger.info(
                f"Cancelled {len(existing_active_subs)} existing subscription(s) for user {user.id}",
                extra={"user_id": str(user.id), "count": len(existing_active_subs)}
            )
        
        # Create new subscription
        now = datetime.utcnow()
        trial_end_date = datetime.fromisoformat(trial_ends_at).replace(tzinfo=None) if trial_ends_at else None

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
            renews_at=datetime.fromisoformat(renews_at).replace(tzinfo=None) if renews_at else None,
            current_api_calls=0,
            usage_reset_date=now + timedelta(days=30),
            created_at=now,
            updated_at=now
        )

        db.add(subscription)
        await db.flush()

        logger.info(
            f"Created subscription {subscription.id} for user {user.id}",
            extra={
                "subscription_id": str(subscription.id),
                "user_id": str(user.id),
                "plan_id": str(plan.id),
                "status": internal_status.value
            }
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
            applied_at=datetime.utcnow(),
            usage_metadata={
                "subscription_id": lemonsqueezy_subscription_id,
                "variant_id": lemonsqueezy_variant_id,
                "webhook_event_id": webhook_data.get("event_id"),
                "affiliate_code": affiliate_code if affiliate_code else None
            }
        )

        db.add(discount_usage)
        await db.flush()

        logger.info(
            f"Tracked discount usage: {discount_code} for user {user.id}" +
            (f" (affiliate: {affiliate_code})" if affiliate_code else ""),
            extra={
                "user_id": str(user.id),
                "discount_code": discount_code,
                "subscription_id": str(subscription.id),
                "affiliate_code": affiliate_code if affiliate_code else None
            }
        )

    # TODO: Send subscription_created email (Task 1.5.1)
    # This will be implemented when we update email templates
    logger.info(
        f"Subscription created email would be sent to {user.email}",
        extra={"user_id": str(user.id), "subscription_id": str(subscription.id)}
    )

    logger.info(
        "Successfully processed subscription_created webhook",
        operation="webhook_subscription_created",
        event_id=webhook_data.get("event_id"),
        subscription_id=str(subscription.id),
        user_id=str(user.id),
        plan_id=str(plan.id),
        status=internal_status.value,
        correlation_id=correlation_id
    )


async def handle_subscription_updated(
    webhook_data: Dict[str, Any],
    webhook_event: WebhookEvent,
    db: AsyncSession
) -> None:
    """
    Handle subscription_updated webhook event.

    This event fires when a subscription is updated (plan change, status change, etc.).

    Actions:
    1. Find existing subscription by lemonsqueezy_subscription_id
    2. Update subscription fields (status, plan, billing_period, etc.)
    3. Send notification if significant change

    Args:
        webhook_data: Parsed webhook data
        webhook_event: Database record for this webhook
        db: Database session

    Raises:
        Exception: If subscription not found or database error
    """
    logger.info(
        "Processing subscription_updated webhook",
        extra={"event_id": webhook_data.get("event_id")}
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
            extra={"event_type": "subscription_updated", "subscription_id": lemonsqueezy_subscription_id}
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
            (SubscriptionPlan.lemonsqueezy_variant_id_monthly == lemonsqueezy_variant_id) |
            (SubscriptionPlan.lemonsqueezy_variant_id_yearly == lemonsqueezy_variant_id)
        )
        result = await db.execute(stmt)
        plan = result.scalar_one_or_none()

        if not plan:
            error_msg = f"Plan not found for variant_id {lemonsqueezy_variant_id}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Determine billing period
        billing_period = BillingPeriod.YEARLY if plan.lemonsqueezy_variant_id_yearly == lemonsqueezy_variant_id else BillingPeriod.MONTHLY

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
            UserSubscription.lemonsqueezy_subscription_id != lemonsqueezy_subscription_id
        )
        existing_active_result = await db.execute(existing_active_subs_stmt)
        existing_active_subs = existing_active_result.scalars().all()
        
        for old_sub in existing_active_subs:
            logger.info(
                f"Cancelling old subscription {old_sub.id} via subscription_updated webhook",
                extra={
                    "old_subscription_id": str(old_sub.id),
                    "new_lemonsqueezy_subscription_id": lemonsqueezy_subscription_id,
                    "user_id": str(user.id)
                }
            )
            old_sub.status = SubscriptionStatus.CANCELLED
            old_sub.cancelled_at = datetime.utcnow()
            old_sub.end_date = datetime.utcnow()
            old_sub.updated_at = datetime.utcnow()
        
        if existing_active_subs:
            await db.flush()

        # Create subscription
        now = datetime.utcnow()
        trial_end_date = datetime.fromisoformat(trial_ends_at).replace(tzinfo=None) if trial_ends_at else None

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
            renews_at=datetime.fromisoformat(renews_at).replace(tzinfo=None) if renews_at else None,
            current_api_calls=0,
            usage_reset_date=now + timedelta(days=30),
            created_at=now,
            updated_at=now
        )

        db.add(subscription)
        await db.flush()

        logger.info(
            f"Created subscription {subscription.id} via subscription_updated webhook",
            extra={
                "subscription_id": str(subscription.id),
                "user_id": str(user.id),
                "plan_id": str(plan.id)
            }
        )

        # Update user's provider_customer_id if not set
        if not user.provider_customer_id and lemonsqueezy_customer_id:
            user.provider_customer_id = lemonsqueezy_customer_id
            await db.flush()

        # Return early - subscription created, nothing to update
        return

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
    if lemonsqueezy_variant_id and subscription.lemonsqueezy_variant_id != lemonsqueezy_variant_id:
        # Find new plan
        stmt = select(SubscriptionPlan).where(
            (SubscriptionPlan.lemonsqueezy_variant_id_monthly == lemonsqueezy_variant_id) |
            (SubscriptionPlan.lemonsqueezy_variant_id_yearly == lemonsqueezy_variant_id)
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
            plan_changed = True
            logger.info(f"Subscription plan changed to {new_plan.name}")

    # Check for trial to paid conversion
    trial_converted = False
    if (subscription.status == SubscriptionStatus.TRIAL and
        internal_status == SubscriptionStatus.ACTIVE and
        subscription.trial_end_date):

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
                    "conversion_source": "automatic"
                }
            )
            logger.info(
                f"Trial conversion tracked for subscription {subscription.id}",
                extra={
                    "subscription_id": str(subscription.id),
                    "user_id": str(subscription.user_id)
                }
            )
        except Exception as e:
            # Log error but don't fail the webhook
            logger.error(
                f"Failed to track trial conversion: {str(e)}",
                extra={
                    "subscription_id": str(subscription.id),
                    "error": str(e)
                }
            )

    # Update subscription fields
    subscription.status = internal_status
    subscription.renews_at = datetime.fromisoformat(renews_at).replace(tzinfo=None) if renews_at else None
    subscription.end_date = datetime.fromisoformat(ends_at).replace(tzinfo=None) if ends_at else None
    subscription.trial_end_date = datetime.fromisoformat(trial_ends_at).replace(tzinfo=None) if trial_ends_at else None
    subscription.cancelled_at = datetime.utcnow() if cancelled and not subscription.cancelled_at else subscription.cancelled_at
    subscription.updated_at = datetime.utcnow()

    await db.flush()

    logger.info(
        f"Successfully updated subscription {subscription.id}",
        extra={
            "subscription_id": str(subscription.id),
            "new_status": internal_status.value,
            "plan_changed": plan_changed,
            "trial_converted": trial_converted
        }
    )


async def handle_subscription_cancelled(
    webhook_data: Dict[str, Any],
    webhook_event: WebhookEvent,
    db: AsyncSession
) -> None:
    """
    Handle subscription_cancelled webhook event.

    This event fires when a subscription is cancelled (cancels at period end by default).

    Actions:
    1. Find subscription
    2. Update status to CANCELLED
    3. Set cancelled_at timestamp
    4. Send cancellation email

    Args:
        webhook_data: Parsed webhook data
        webhook_event: Database record for this webhook
        db: Database session
    """
    logger.info(
        "Processing subscription_cancelled webhook",
        extra={"event_id": webhook_data.get("event_id")}
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

    # Update subscription
    subscription.status = SubscriptionStatus.CANCELLED
    subscription.cancelled_at = datetime.utcnow()
    subscription.end_date = datetime.fromisoformat(ends_at).replace(tzinfo=None) if ends_at else None
    subscription.updated_at = datetime.utcnow()

    await db.flush()

    # TODO: Send cancellation email (Task 1.5.2)
    logger.info(
        f"Successfully cancelled subscription {subscription.id}",
        extra={"subscription_id": str(subscription.id)}
    )


async def handle_subscription_expired(
    webhook_data: Dict[str, Any],
    webhook_event: WebhookEvent,
    db: AsyncSession
) -> None:
    """
    Handle subscription_expired webhook event.

    This event fires when a subscription expires (trial ended, payment failed, etc.).

    Actions:
    1. Find subscription
    2. Update status to EXPIRED
    3. Send expiration email

    Args:
        webhook_data: Parsed webhook data
        webhook_event: Database record for this webhook
        db: Database session
    """
    logger.info(
        "Processing subscription_expired webhook",
        extra={"event_id": webhook_data.get("event_id")}
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
    subscription.end_date = datetime.utcnow()
    subscription.updated_at = datetime.utcnow()

    await db.flush()

    # TODO: Send expiration email
    logger.info(
        f"Successfully expired subscription {subscription.id}",
        extra={"subscription_id": str(subscription.id)}
    )


async def handle_subscription_payment_success(
    webhook_data: Dict[str, Any],
    webhook_event: WebhookEvent,
    db: AsyncSession
) -> None:
    """
    Handle subscription_payment_success webhook event.

    This event fires when a subscription payment succeeds.

    Actions:
    1. Find subscription
    2. Update status to ACTIVE (if was TRIAL or SUSPENDED)
    3. Reset usage counters for new billing cycle
    4. Update next renewal date
    5. Send payment success email with receipt

    Args:
        webhook_data: Parsed webhook data
        webhook_event: Database record for this webhook
        db: Database session
    """
    logger.info(
        "Processing subscription_payment_success webhook",
        extra={"event_id": webhook_data.get("event_id")}
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
            extra={"event_type": "subscription_payment_success", "subscription_id": lemonsqueezy_subscription_id}
        )
        # Don't raise error - this is normal webhook ordering issue
        return

    # Update subscription - activate if was trial or suspended
    if subscription.status in [SubscriptionStatus.TRIAL, SubscriptionStatus.PAST_DUE]:
        subscription.status = SubscriptionStatus.ACTIVE

    # Update renewal date
    subscription.renews_at = datetime.fromisoformat(renews_at).replace(tzinfo=None) if renews_at else None

    # Reset usage counters for new billing cycle
    subscription.current_api_calls = 0
    subscription.usage_reset_date = datetime.utcnow() + timedelta(days=30)
    subscription.updated_at = datetime.utcnow()

    await db.flush()

    # TODO: Send payment success email (Task 1.5.3)
    logger.info(
        f"Successfully processed payment for subscription {subscription.id}",
        extra={"subscription_id": str(subscription.id)}
    )

    # Audit log
    audit_logger.log_payment_succeeded(
        user_id=subscription.user_id,
        subscription_id=subscription.id,
        amount=0,  # Amount not available in webhook data
        currency="USD",
        lemonsqueezy_payment_id=lemonsqueezy_subscription_id,
        metadata={"renews_at": renews_at}
    )


async def handle_subscription_payment_failed(
    webhook_data: Dict[str, Any],
    webhook_event: WebhookEvent,
    db: AsyncSession
) -> None:
    """
    Handle subscription_payment_failed webhook event.

    This event fires when a subscription payment fails.

    Actions:
    1. Find subscription
    2. Set status to SUSPENDED (grace period)
    3. Calculate and set grace period (7 days)
    4. Track payment failure timestamp
    5. Send payment failed email immediately with retry instructions

    Grace Period Behavior:
    - User retains access during grace period (7 days)
    - LemonSqueezy will automatically retry payment
    - Dunning emails sent at 1, 3, 6 days (Task 3.4.2)
    - Auto-suspend after grace period (Task 3.4.3)

    Args:
        webhook_data: Parsed webhook data
        webhook_event: Database record for this webhook
        db: Database session
    """
    logger.info(
        "Processing subscription_payment_failed webhook",
        extra={"event_id": webhook_data.get("event_id")}
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

    # Calculate grace period (7 days from now)
    now = datetime.utcnow()
    grace_period_days = 7
    grace_period_end = now + timedelta(days=grace_period_days)

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
            "grace_period_days": grace_period_days
        }
    )

    # Audit log
    audit_logger.log_payment_failed(
        user_id=subscription.user_id,
        subscription_id=subscription.id,
        amount=0,  # Amount not available in webhook data
        failure_reason="Payment failed",
        lemonsqueezy_payment_id=lemonsqueezy_subscription_id,
        metadata={"grace_period_end": grace_period_end.isoformat()}
    )

    # Send payment failed email immediately
    try:
        from src.services.billing_email_service import BillingEmailService

        # Extract payment details from webhook
        attributes = webhook_data.get("data", {}).get("attributes", {})
        first_subscription_item = attributes.get("first_subscription_item", {})

        # Format amount
        amount_cents = first_subscription_item.get("price", 0)
        amount = f"${amount_cents / 100:.2f}" if amount_cents else "N/A"

        # Calculate retry date (LemonSqueezy typically retries in 3 days)
        retry_date = (now + timedelta(days=3)).strftime("%B %d, %Y")

        # Send email
        email_service = BillingEmailService(db)
        await email_service.send_payment_failed_email(
            user_id=user.id,
            plan_name=plan.name if plan else "Your Plan",
            amount=amount,
            retry_date=retry_date
        )

        logger.info(
            f"Payment failed email sent to {user.email}",
            extra={
                "user_id": str(user.id),
                "subscription_id": str(subscription.id),
                "amount": amount
            }
        )
    except Exception as e:
        # Log error but don't fail the webhook - email is non-critical
        logger.error(
            f"Failed to send payment failed email: {str(e)}",
            extra={
                "user_id": str(user.id),
                "subscription_id": str(subscription.id),
                "error": str(e)
            },
            exc_info=True
        )

        # Capture email failure to Sentry (Phase 4, Task 4.2.1)
        # Non-critical but worth tracking
        capture_payment_exception(
            e,
            operation="webhook_email_payment_failed",
            user_id=str(user.id),
            subscription_id=str(subscription.id),
            level="warning",  # Non-critical
            context={
                "email_type": "payment_failed",
                "plan_name": plan.name if plan else "Unknown",
            }
        )

    logger.warning(
        f"Payment failed for subscription {subscription.id} - user has access until {grace_period_end.isoformat()}",
        extra={
            "subscription_id": str(subscription.id),
            "user_id": str(user.id),
            "grace_period_end": grace_period_end.isoformat()
        }
    )


async def handle_subscription_payment_recovered(
    webhook_data: Dict[str, Any],
    webhook_event: WebhookEvent,
    db: AsyncSession
) -> None:
    """
    Handle subscription_payment_recovered webhook event.

    This event fires when a previously failed payment is successfully recovered.

    Actions:
    1. Find subscription
    2. Restore status to ACTIVE
    3. Clear grace period tracking (payment resolved)
    4. Update renewal date
    5. Send payment recovered email with celebration message

    Recovery Process:
    - Payment fails → SUSPENDED status with grace period
    - Dunning emails sent (days 1, 3, 6)
    - User updates payment method OR automatic retry succeeds
    - This handler → Restore to ACTIVE, clear grace period, send success email

    Args:
        webhook_data: Parsed webhook data
        webhook_event: Database record for this webhook
        db: Database session
    """
    logger.info(
        "Processing subscription_payment_recovered webhook",
        extra={"event_id": webhook_data.get("event_id")}
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
    now = datetime.utcnow()
    subscription.status = SubscriptionStatus.ACTIVE
    subscription.renews_at = datetime.fromisoformat(renews_at).replace(tzinfo=None) if renews_at else None
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
            "new_status": "active"
        }
    )

    # Send payment recovered email
    try:
        from src.services.billing_email_service import BillingEmailService
        from emails.templates.billing import render_payment_recovered_email

        # Extract payment details from webhook
        attributes = webhook_data.get("data", {}).get("attributes", {})
        first_subscription_item = attributes.get("first_subscription_item", {})

        # Format amount
        amount_cents = first_subscription_item.get("price", 0)
        if not amount_cents and plan:
            # Fallback to plan price
            if subscription.billing_period.value == "monthly":
                amount_cents = plan.price_monthly
            else:
                amount_cents = plan.price_yearly
        amount = f"${amount_cents / 100:.2f}" if amount_cents else "N/A"

        # Format dates
        recovery_date = now.strftime("%B %d, %Y")
        next_billing_date = subscription.renews_at.strftime("%B %d, %Y") if subscription.renews_at else "N/A"

        # Render email
        user_name = user.first_name or user.display_name or user.email
        plan_name = plan.name if plan else "Your Plan"

        html_content = render_payment_recovered_email(
            user_name=user_name,
            plan_name=plan_name,
            amount=amount,
            recovery_date=recovery_date,
            next_billing_date=next_billing_date
        )

        # Send email
        email_service = BillingEmailService(db)
        await email_service._send_email(
            to_email=user.email,
            subject=f"Payment Successful - {plan_name} Reactivated!",
            html_content=html_content
        )

        logger.info(
            f"Payment recovered email sent to {user.email}",
            extra={
                "user_id": str(user.id),
                "subscription_id": str(subscription.id),
                "amount": amount
            }
        )

    except Exception as e:
        # Log error but don't fail the webhook - email is non-critical
        logger.error(
            f"Failed to send payment recovered email: {str(e)}",
            extra={
                "user_id": str(user.id),
                "subscription_id": str(subscription.id),
                "error": str(e)
            },
            exc_info=True
        )


async def handle_subscription_paused(
    webhook_data: Dict[str, Any],
    webhook_event: WebhookEvent,
    db: AsyncSession
) -> None:
    """
    Handle subscription_paused webhook event.

    This event fires when a subscription is paused by admin or user.

    Actions:
    1. Find subscription
    2. Update status to PAUSED
    3. Send paused notification email

    Args:
        webhook_data: Parsed webhook data
        webhook_event: Database record for this webhook
        db: Database session
    """
    logger.info(
        "Processing subscription_paused webhook",
        extra={"event_id": webhook_data.get("event_id")}
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
    subscription.updated_at = datetime.utcnow()

    await db.flush()

    # TODO: Send subscription paused email
    logger.info(
        f"Successfully paused subscription {subscription.id}",
        extra={
            "subscription_id": str(subscription.id),
            "resumes_at": resumes_at
        }
    )


async def handle_subscription_resumed(
    webhook_data: Dict[str, Any],
    webhook_event: WebhookEvent,
    db: AsyncSession
) -> None:
    """
    Handle subscription_resumed webhook event.

    This event fires when a paused subscription is resumed.

    Actions:
    1. Find subscription
    2. Update status to ACTIVE
    3. Update renewal dates
    4. Send resumed notification email

    Args:
        webhook_data: Parsed webhook data
        webhook_event: Database record for this webhook
        db: Database session
    """
    logger.info(
        "Processing subscription_resumed webhook",
        extra={"event_id": webhook_data.get("event_id")}
    )

    sub_data = extract_subscription_data(webhook_data)
    lemonsqueezy_subscription_id = sub_data.get("subscription_id")
    renews_at = sub_data.get("renews_at")
    status = sub_data.get("status", "active")

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
    subscription.renews_at = datetime.fromisoformat(renews_at).replace(tzinfo=None) if renews_at else None
    subscription.updated_at = datetime.utcnow()

    await db.flush()

    # TODO: Send subscription resumed email
    logger.info(
        f"Successfully resumed subscription {subscription.id}",
        extra={"subscription_id": str(subscription.id)}
    )

