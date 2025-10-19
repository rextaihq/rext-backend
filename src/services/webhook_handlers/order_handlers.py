"""
Order and License Webhook Handlers

Handlers for one-time purchase and license-related LemonSqueezy webhook events:
- order_created (for LTD purchases)
- order_refunded (for refunds)
- license_key_created (for license key generation)

These handlers support Lifetime Deal (LTD) purchases where customers
pay once and get permanent access.

Each handler:
1. Extracts relevant data from webhook
2. Creates/updates licenses in database
3. Links licenses to users
4. Sends email notifications
5. Logs actions
"""

from typing import Dict, Any
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.api.models.subscription_models.licenses import License, LicenseStatus
from src.api.models.subscription_models.subscriptions import (
    UserSubscription,
    SubscriptionStatus,
    BillingPeriod
)
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.webhooks import WebhookEvent
from src.api.models.user_models.users import Users
from src.services.refund_service import RefundService
from src.utils.lemonsqueezy_webhook import (
    extract_order_data,
    extract_license_key_data,
    get_user_identifier
)
from src.utils.logger import logger


async def handle_order_created(
    webhook_data: Dict[str, Any],
    webhook_event: WebhookEvent,
    db: AsyncSession
) -> None:
    """
    Handle order_created webhook event (for one-time purchases / LTDs).

    This event fires when a one-time purchase is completed.
    For LTDs, this creates a permanent subscription and license key.

    Actions:
    1. Extract order data from webhook
    2. Find user by email or custom_data.user_id
    3. Find subscription plan by product_id
    4. Create license record
    5. Create permanent UserSubscription (no end_date)
    6. Send purchase confirmation email with license key

    Args:
        webhook_data: Parsed webhook data
        webhook_event: Database record for this webhook
        db: Database session

    Raises:
        Exception: If user not found, plan not found, or database error
    """
    logger.info(
        "Processing order_created webhook (LTD purchase)",
        extra={"event_id": webhook_data.get("event_id")}
    )

    # Extract order data
    order_data = extract_order_data(webhook_data)

    lemonsqueezy_order_id = order_data.get("order_id")
    lemonsqueezy_customer_id = order_data.get("customer_id")
    lemonsqueezy_variant_id = order_data.get("variant_id")
    lemonsqueezy_product_id = order_data.get("product_id")
    product_name = order_data.get("product_name")
    user_email = order_data.get("user_email")
    total = order_data.get("total")
    status = order_data.get("status", "paid")

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
        error_msg = f"User not found for order {lemonsqueezy_order_id}"
        logger.error(error_msg, extra={
            "user_identifier": user_identifier,
            "user_email": user_email
        })
        raise ValueError(error_msg)

    # Find subscription plan by LemonSqueezy variant_id (for LTDs)
    stmt = select(SubscriptionPlan).where(
        (SubscriptionPlan.lemonsqueezy_variant_id_monthly == lemonsqueezy_variant_id) |
        (SubscriptionPlan.lemonsqueezy_variant_id_yearly == lemonsqueezy_variant_id)
    )
    result = await db.execute(stmt)
    plan = result.scalar_one_or_none()

    if not plan:
        # For LTDs, create a generic "Lifetime" plan reference or skip plan
        logger.warning(f"Plan not found for variant_id {lemonsqueezy_variant_id} - proceeding without plan")

    # Extract license key from webhook data (if present)
    license_key = None
    try:
        license_data = extract_license_key_data(webhook_data)
        license_key = license_data.get("license_key")
    except Exception as e:
        logger.warning(f"No license key in order webhook: {str(e)}")

    # Create License record
    license_record = License(
        user_id=user.id,
        lemonsqueezy_license_id=None,  # Will be updated in license_key_created event
        lemonsqueezy_order_id=lemonsqueezy_order_id,
        license_key=license_key if license_key else f"pending-{lemonsqueezy_order_id}",
        product_id=plan.id if plan else None,
        product_name=product_name or "Lifetime Deal",
        status=LicenseStatus.ACTIVE if status == "paid" else LicenseStatus.INACTIVE,
        activation_limit=-1,  # Unlimited for LTDs
        activation_usage=1,  # User account counts as 1 activation
        expires_at=None,  # Lifetime - never expires
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )

    db.add(license_record)
    await db.flush()

    logger.info(
        f"Created license {license_record.id} for LTD purchase",
        extra={
            "license_id": str(license_record.id),
            "user_id": str(user.id),
            "order_id": lemonsqueezy_order_id
        }
    )

    # Create permanent UserSubscription for LTD (no end_date = lifetime)
    if plan:
        # Check if subscription already exists
        stmt = select(UserSubscription).where(
            UserSubscription.user_id == user.id,
            UserSubscription.plan_id == plan.id,
            UserSubscription.end_date.is_(None)  # Lifetime subscription
        )
        result = await db.execute(stmt)
        existing_sub = result.scalar_one_or_none()

        if not existing_sub:
            now = datetime.utcnow()
            subscription = UserSubscription(
                user_id=user.id,
                plan_id=plan.id,
                status=SubscriptionStatus.ACTIVE,
                billing_period=BillingPeriod.LIFETIME,  # Special lifetime period
                start_date=now,
                end_date=None,  # No end date = lifetime
                trial_end_date=None,
                lemonsqueezy_subscription_id=None,  # One-time purchase, no subscription
                lemonsqueezy_customer_id=lemonsqueezy_customer_id,
                lemonsqueezy_variant_id=lemonsqueezy_variant_id,
                lemonsqueezy_order_id=lemonsqueezy_order_id,
                current_api_calls=0,
                usage_reset_date=now + timedelta(days=30),
                created_at=now,
                updated_at=now
            )

            db.add(subscription)
            await db.flush()

            logger.info(
                f"Created lifetime subscription {subscription.id} for LTD",
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
        logger.info(f"Updated user {user.id} provider_customer_id")

    # TODO: Send LTD purchase confirmation email with license key
    logger.info(
        f"LTD purchase confirmation email would be sent to {user.email}",
        extra={
            "user_id": str(user.id),
            "license_id": str(license_record.id),
            "license_key": license_key
        }
    )

    logger.info(
        "Successfully processed order_created webhook (LTD)",
        extra={
            "event_id": webhook_data.get("event_id"),
            "order_id": lemonsqueezy_order_id,
            "user_id": str(user.id)
        }
    )


async def handle_order_refunded(
    webhook_data: Dict[str, Any],
    webhook_event: WebhookEvent,
    db: AsyncSession
) -> None:
    """
    Handle order_refunded webhook event.

    This event fires when an order is refunded.
    For LTDs, this revokes the license and subscription.

    Actions:
    1. Find license by order_id
    2. Update license status to DISABLED
    3. Find and expire associated subscription
    4. Send refund confirmation email

    Args:
        webhook_data: Parsed webhook data
        webhook_event: Database record for this webhook
        db: Database session
    """
    logger.info(
        "Processing order_refunded webhook",
        extra={"event_id": webhook_data.get("event_id")}
    )

    # Extract order data
    order_data = extract_order_data(webhook_data)
    lemonsqueezy_order_id = order_data.get("order_id")
    refunded_at = order_data.get("refunded_at")
    total_amount = order_data.get("total", 0)
    user_email = order_data.get("user_email")

    # Find license by order_id
    stmt = select(License).where(
        License.lemonsqueezy_order_id == lemonsqueezy_order_id
    )
    result = await db.execute(stmt)
    license_record = result.scalar_one_or_none()

    # Find and expire associated subscription
    stmt = select(UserSubscription).where(
        UserSubscription.lemonsqueezy_order_id == lemonsqueezy_order_id
    )
    result = await db.execute(stmt)
    subscription = result.scalar_one_or_none()

    # Need at least one to process refund
    if not license_record and not subscription:
        logger.warning(f"No license or subscription found for refunded order {lemonsqueezy_order_id}")
        return  # Not an error - order might not have had a license or subscription

    user_id = license_record.user_id if license_record else subscription.user_id
    subscription_id = subscription.id if subscription else None

    # Create refund record
    refund_service = RefundService(db)
    try:
        refund = await refund_service.create_refund_record(
            user_id=user_id,
            lemonsqueezy_order_id=lemonsqueezy_order_id,
            refund_amount=total_amount,  # Full refund
            original_amount=total_amount,
            subscription_id=subscription_id,
            reason="Refund processed via LemonSqueezy webhook"
        )

        # Mark as completed since webhook already processed
        await refund_service.mark_refund_completed(refund.id)

        logger.info(
            f"Created refund record {refund.id} for order {lemonsqueezy_order_id}",
            extra={"refund_id": str(refund.id), "order_id": lemonsqueezy_order_id}
        )
    except Exception as e:
        logger.error(f"Failed to create refund record: {str(e)}")
        # Continue processing even if refund record creation fails

    # Disable license
    if license_record:
        license_record.status = LicenseStatus.DISABLED
        license_record.updated_at = datetime.utcnow()
        await db.flush()

        logger.info(
            f"Disabled license {license_record.id} due to refund",
            extra={"license_id": str(license_record.id)}
        )

    # Cancel subscription
    if subscription:
        subscription.status = SubscriptionStatus.CANCELLED
        subscription.cancelled_at = datetime.utcnow()
        subscription.end_date = datetime.utcnow()
        subscription.updated_at = datetime.utcnow()
        await db.flush()

        logger.info(
            f"Cancelled subscription {subscription.id} due to refund",
            extra={"subscription_id": str(subscription.id)}
        )

    # TODO: Send refund confirmation email
    # For now, logging that email should be sent
    logger.info(
        f"Refund processed for order {lemonsqueezy_order_id} - Email notification should be sent to {user_email}",
        extra={
            "order_id": lemonsqueezy_order_id,
            "user_email": user_email,
            "license_id": str(license_record.id) if license_record else None,
            "subscription_id": str(subscription.id) if subscription else None
        }
    )


async def handle_license_key_created(
    webhook_data: Dict[str, Any],
    webhook_event: WebhookEvent,
    db: AsyncSession
) -> None:
    """
    Handle license_key_created webhook event.

    This event fires when a license key is generated by LemonSqueezy.
    It may fire after order_created, so we need to update existing license records.

    Actions:
    1. Extract license key data
    2. Find existing license by order_id or create new one
    3. Update license with lemonsqueezy_license_id and key
    4. Update activation limits

    Args:
        webhook_data: Parsed webhook data
        webhook_event: Database record for this webhook
        db: Database session
    """
    logger.info(
        "Processing license_key_created webhook",
        extra={"event_id": webhook_data.get("event_id")}
    )

    # Extract license key data
    license_data = extract_license_key_data(webhook_data)

    lemonsqueezy_license_id = license_data.get("license_id")
    lemonsqueezy_order_id = license_data.get("order_id")
    license_key = license_data.get("license_key")
    product_id = license_data.get("product_id")
    status = license_data.get("status", "active")
    activation_limit = license_data.get("activation_limit", -1)
    activation_usage = license_data.get("activation_usage", 0)
    expires_at = license_data.get("expires_at")

    # Find existing license by order_id
    license_record = None
    if lemonsqueezy_order_id:
        stmt = select(License).where(
            License.lemonsqueezy_order_id == lemonsqueezy_order_id
        )
        result = await db.execute(stmt)
        license_record = result.scalar_one_or_none()

    # Map status
    status_map = {
        "active": LicenseStatus.ACTIVE,
        "inactive": LicenseStatus.INACTIVE,
        "expired": LicenseStatus.EXPIRED,
        "disabled": LicenseStatus.DISABLED,
    }
    internal_status = status_map.get(status.lower(), LicenseStatus.ACTIVE)

    if license_record:
        # Update existing license
        license_record.lemonsqueezy_license_id = lemonsqueezy_license_id
        license_record.license_key = license_key
        license_record.status = internal_status
        license_record.activation_limit = activation_limit
        license_record.activation_usage = activation_usage
        license_record.expires_at = datetime.fromisoformat(expires_at) if expires_at else None
        license_record.updated_at = datetime.utcnow()

        await db.flush()

        logger.info(
            f"Updated license {license_record.id} with key from LemonSqueezy",
            extra={
                "license_id": str(license_record.id),
                "lemonsqueezy_license_id": lemonsqueezy_license_id
            }
        )
    else:
        # License doesn't exist yet - this shouldn't happen normally
        # but handle gracefully by logging
        logger.warning(
            f"License key created webhook received but no license found for order {lemonsqueezy_order_id}",
            extra={"lemonsqueezy_license_id": lemonsqueezy_license_id}
        )

    logger.info(
        "Successfully processed license_key_created webhook",
        extra={
            "event_id": webhook_data.get("event_id"),
            "license_id": lemonsqueezy_license_id
        }
    )
