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
from src.api.models.user_models.users import Users
from src.utils.lemonsqueezy_webhook import extract_subscription_data, get_user_identifier
from src.utils.logger import logger


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
    logger.info(
        "Processing subscription_created webhook",
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
        existing_sub.trial_end_date = datetime.fromisoformat(trial_ends_at) if trial_ends_at else None
        existing_sub.updated_at = datetime.utcnow()
        await db.flush()
        subscription = existing_sub
    else:
        # Create new subscription
        now = datetime.utcnow()
        trial_end_date = datetime.fromisoformat(trial_ends_at) if trial_ends_at else None

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
            lemonsqueezy_renews_at=datetime.fromisoformat(renews_at) if renews_at else None,
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

    # TODO: Send subscription_created email (Task 1.5.1)
    # This will be implemented when we update email templates
    logger.info(
        f"Subscription created email would be sent to {user.email}",
        extra={"user_id": str(user.id), "subscription_id": str(subscription.id)}
    )

    logger.info(
        "Successfully processed subscription_created webhook",
        extra={
            "event_id": webhook_data.get("event_id"),
            "subscription_id": str(subscription.id),
            "user_id": str(user.id)
        }
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
    lemonsqueezy_variant_id = sub_data.get("variant_id")
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
        error_msg = f"Subscription {lemonsqueezy_subscription_id} not found"
        logger.error(error_msg)
        raise ValueError(error_msg)

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

    # Update subscription fields
    subscription.status = internal_status
    subscription.lemonsqueezy_renews_at = datetime.fromisoformat(renews_at) if renews_at else None
    subscription.end_date = datetime.fromisoformat(ends_at) if ends_at else None
    subscription.trial_end_date = datetime.fromisoformat(trial_ends_at) if trial_ends_at else None
    subscription.cancelled_at = datetime.utcnow() if cancelled and not subscription.cancelled_at else subscription.cancelled_at
    subscription.updated_at = datetime.utcnow()

    await db.flush()

    logger.info(
        f"Successfully updated subscription {subscription.id}",
        extra={
            "subscription_id": str(subscription.id),
            "new_status": internal_status.value,
            "plan_changed": plan_changed
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
    subscription.end_date = datetime.fromisoformat(ends_at) if ends_at else None
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
        error_msg = f"Subscription {lemonsqueezy_subscription_id} not found"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Update subscription - activate if was trial or suspended
    if subscription.status in [SubscriptionStatus.TRIAL, SubscriptionStatus.PAST_DUE]:
        subscription.status = SubscriptionStatus.ACTIVE

    # Update renewal date
    subscription.lemonsqueezy_renews_at = datetime.fromisoformat(renews_at) if renews_at else None

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
    2. Update status to PAST_DUE (grace period)
    3. Send payment failed email with retry instructions

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

    # Update subscription - set to PAST_DUE (grace period)
    subscription.status = SubscriptionStatus.PAST_DUE
    subscription.updated_at = datetime.utcnow()

    await db.flush()

    # TODO: Send payment failed email (Task 1.5.4)
    logger.warning(
        f"Payment failed for subscription {subscription.id}",
        extra={"subscription_id": str(subscription.id)}
    )


async def handle_subscription_payment_recovered(
    webhook_data: Dict[str, Any],
    webhook_event: WebhookEvent,
    db: AsyncSession
) -> None:
    """
    Handle subscription_payment_recovered webhook event.

    This event fires when a previously failed payment is recovered.

    Actions:
    1. Find subscription
    2. Update status back to ACTIVE
    3. Send payment recovered email

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

    # Update subscription - restore to ACTIVE
    subscription.status = SubscriptionStatus.ACTIVE
    subscription.lemonsqueezy_renews_at = datetime.fromisoformat(renews_at) if renews_at else None
    subscription.updated_at = datetime.utcnow()

    await db.flush()

    # TODO: Send payment recovered email
    logger.info(
        f"Payment recovered for subscription {subscription.id}",
        extra={"subscription_id": str(subscription.id)}
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
    subscription.lemonsqueezy_renews_at = datetime.fromisoformat(renews_at) if renews_at else None
    subscription.updated_at = datetime.utcnow()

    await db.flush()

    # TODO: Send subscription resumed email
    logger.info(
        f"Successfully resumed subscription {subscription.id}",
        extra={"subscription_id": str(subscription.id)}
    )

