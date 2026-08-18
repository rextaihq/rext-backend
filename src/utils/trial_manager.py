"""
Trial period management utilities.

This module provides functions for managing subscription trial periods,
including checking expirations, converting trials, and notifying users.
"""

from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from src.api.models.subscription_models.subscriptions import (
    UserSubscription,
    SubscriptionStatus,
)
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.user_models.users import Users
from src.utils.logger import logger


def check_trial_expiration(
    subscription: UserSubscription,
    plan: SubscriptionPlan
) -> dict:
    """
    Check if a trial subscription has expired.

    Args:
        subscription: UserSubscription instance
        plan: SubscriptionPlan instance

    Returns:
        Dict with trial status information
    """
    if subscription.status != SubscriptionStatus.TRIAL:
        return {
            "is_trial": False,
            "expired": False,
            "days_remaining": None,
            "action_required": False
        }

    if not subscription.trial_end_date:
        logger.warning(f"Trial subscription {subscription.id} missing trial_end_date")
        return {
            "is_trial": True,
            "expired": True,
            "days_remaining": 0,
            "action_required": True
        }

    now = datetime.now(timezone.utc)
    days_remaining = (subscription.trial_end_date - now).days

    return {
        "is_trial": True,
        "expired": days_remaining < 0,
        "days_remaining": max(0, days_remaining),
        "action_required": days_remaining <= 3,  # Show warning when 3 days or less
        "trial_end_date": subscription.trial_end_date.isoformat()
    }


async def expire_trial_subscriptions(db: AsyncSession) -> Dict[str, int]:
    """
    Find and expire all trial subscriptions that have passed their trial_end_date.

    This function should be run as a daily cron job.

    Args:
        db: Database session

    Returns:
        Dict with counts of expired, converted, and downgraded subscriptions
    """
    now = datetime.now(timezone.utc)

    # Find all expired trials
    stmt = select(UserSubscription).where(
        UserSubscription.status == SubscriptionStatus.TRIAL,
        UserSubscription.trial_end_date < now
    )
    result = await db.execute(stmt)
    expired_trials = result.scalars().all()

    expired_count = 0
    converted_count = 0
    downgraded_count = 0

    for subscription in expired_trials:
        try:
            # Check if payment method exists (LemonSqueezy integration)
            has_payment = subscription.lemonsqueezy_subscription_id is not None

            if has_payment:
                # Convert trial to active subscription
                subscription.status = SubscriptionStatus.ACTIVE
                converted_count += 1
                logger.info(f"Converted trial subscription {subscription.id} to active")
            else:
                # No payment method - expire trial and downgrade to free plan
                stmt_plan = select(SubscriptionPlan).where(
                    SubscriptionPlan.name == "free",
                    SubscriptionPlan.is_active == True
                )
                result_plan = await db.execute(stmt_plan)
                free_plan = result_plan.scalar_one_or_none()

                if free_plan:
                    subscription.plan_id = free_plan.id
                    subscription.status = SubscriptionStatus.ACTIVE
                    subscription.end_date = None  # Free plan has no end date
                    downgraded_count += 1
                    logger.info(f"Downgraded expired trial subscription {subscription.id} to free plan")
                else:
                    # No free plan found - expire the subscription
                    subscription.status = SubscriptionStatus.EXPIRED
                    subscription.end_date = now
                    expired_count += 1
                    logger.warning(f"Expired trial subscription {subscription.id} (no free plan found)")

            subscription.updated_at = now
            await db.commit()

        except Exception as e:
            logger.error(f"Error processing expired trial {subscription.id}: {e}")
            await db.rollback()
            continue

    total_processed = converted_count + downgraded_count + expired_count
    logger.info(f"Processed {total_processed} expired trials: {converted_count} converted, {downgraded_count} downgraded, {expired_count} expired")

    return {
        "total_processed": total_processed,
        "converted_to_active": converted_count,
        "downgraded_to_free": downgraded_count,
        "expired": expired_count
    }


async def get_trials_expiring_soon(
    db: AsyncSession,
    days_threshold: int = 3
) -> List[Dict]:

    """
    Get a list of trial subscriptions that will expire within the threshold.

    Useful for sending reminder emails to users.

    Args:
        db: Database session
        days_threshold: Number of days to look ahead (default: 3)

    Returns:
        List of dicts with subscription and user information
    """
    now = datetime.now(timezone.utc)
    threshold_date = now + timedelta(days=days_threshold)

    result = await db.execute(
        select(UserSubscription, Users, SubscriptionPlan)
        .join(Users, UserSubscription.user_id == Users.id)
        .join(SubscriptionPlan, UserSubscription.plan_id == SubscriptionPlan.id)
        .where(
            UserSubscription.status == SubscriptionStatus.TRIAL,
            UserSubscription.trial_end_date.between(now, threshold_date)
        )
    )

    expiring_trials = result.all()

    results = []
    for subscription, user, plan in expiring_trials:
        days_remaining = (subscription.trial_end_date - now).days
        results.append({
            "subscription_id": str(subscription.id),
            "user_id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "plan_name": plan.display_name,
            "trial_end_date": subscription.trial_end_date.isoformat(),
            "days_remaining": max(0, days_remaining),
            "has_payment_method": subscription.lemonsqueezy_subscription_id is not None
        })

    return results

async def extend_trial(
    db: AsyncSession,
    subscription_id: str,
    extend_days: int,
    reason: Optional[str] = None
) -> UserSubscription:

    result = await db.execute(
        select(UserSubscription).where(UserSubscription.id == subscription_id)
    )
    subscription = result.scalar_one_or_none()

    if not subscription:
        raise ValueError("Subscription not found")

    if subscription.status != SubscriptionStatus.TRIAL:
        raise ValueError("Subscription not in trial")

    # old_end_date = subscription.trial_end_date
    subscription.trial_end_date += timedelta(days=extend_days)
    subscription.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(subscription)

    return subscription

async def convert_trial_to_active(
    db: AsyncSession,
    subscription_id: str,
    lemonsqueezy_subscription_id: Optional[str] = None
) -> UserSubscription:
    """
    Manually convert a trial subscription to active (typically after payment confirmation).

    Args:
        db: Database async session
        subscription_id: UUID of the subscription
        lemonsqueezy_subscription_id: Optional LemonSqueezy subscription ID to associate

    Returns:
        Updated UserSubscription

    Raises:
        ValueError: If subscription not found or not in trial status
    """
    result = await db.execute(
        select(UserSubscription).where(UserSubscription.id == subscription_id)
    )
    subscription = result.scalar_one_or_none()

    if not subscription:
        raise ValueError("Subscription not found")

    subscription.status = SubscriptionStatus.ACTIVE
    subscription.trial_end_date = None

    if lemonsqueezy_subscription_id:
        subscription.lemonsqueezy_subscription_id = lemonsqueezy_subscription_id
    subscription.updated_at = datetime.now(timezone.utc)

    subscription.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(subscription)

    return subscription

async def get_trial_statistics(db: AsyncSession) -> Dict:
    now = datetime.now(timezone.utc)

    active_trials = await db.scalar(
        select(func.count()).where(UserSubscription.status == SubscriptionStatus.TRIAL)
    )

    expiring_soon = await db.scalar(
        select(func.count()).where(
            UserSubscription.status == SubscriptionStatus.TRIAL,
            UserSubscription.trial_end_date.between(now, now + timedelta(days=7))
        )
    )

    trials_with_payment = await db.scalar(
        select(func.count()).where(
            UserSubscription.status == SubscriptionStatus.TRIAL,
            UserSubscription.lemonsqueezy_subscription_id.isnot(None)
        )
    )

    trials_without_payment = await db.scalar(
        select(func.count()).where(
            UserSubscription.status == SubscriptionStatus.TRIAL,
            UserSubscription.lemonsqueezy_subscription_id.is_(None)
        )
    )

    return {
        "active_trials": active_trials or 0,
        "expiring_within_7_days": expiring_soon or 0,
        "trials_with_payment_method": trials_with_payment or 0,
        "trials_without_payment_method": trials_without_payment or 0,
    }


# ============================================================================
# EMAIL NOTIFICATION HELPERS
# ============================================================================

async def send_trial_expiring_notification_async(
    user_email: str,
    user_id: str,
    days_remaining: int,
    plan_name: str
) -> bool:
    """
    Send email notification that trial is expiring soon (async version).

    Args:
        user_email: User's email address
        user_id: User ID for tracking
        days_remaining: Number of days until trial expires
        plan_name: Name of the subscription plan

    Returns:
        True if email sent successfully, False otherwise
    """
    from src.services.email_service import EmailService
    from src.api.database.async_database import get_async_db_context
    from uuid import UUID

    try:
        async with get_async_db_context() as db:
            email_service = EmailService(db)

            # Build HTML content
            html_content = f"""
                <h2>Your {plan_name} Trial is Expiring Soon</h2>
                <p>Hello,</p>
                <p>Your {plan_name} trial will expire in <strong>{days_remaining} day(s)</strong>.</p>
                <p>To continue enjoying premium features, please add a payment method to convert your trial to an active subscription.</p>
                <p>If you don't add a payment method, you'll be automatically downgraded to our free plan when your trial expires.</p>
                <h3>What happens next?</h3>
                <ul>
                    <li><strong>Add Payment:</strong> Convert to paid subscription and keep all premium features</li>
                    <li><strong>Do Nothing:</strong> Automatically downgrade to free plan with limited features</li>
                </ul>
                <p><a href="https://app.rext.com/settings/subscription" style="background-color: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Manage Subscription</a></p>
                <p>Thank you for trying Rext AI!</p>
            """

            await email_service.send_email(
                to=user_email,
                subject=f"Your {plan_name} trial expires in {days_remaining} day(s)",
                html=html_content,
                user_id=UUID(user_id),
                template_type="trial_expiring",
                tags={"type": "subscription", "action": "trial_expiring", "days_remaining": str(days_remaining)}
            )

            logger.info(f"Trial expiring notification sent to {user_email}")
            return True

    except Exception as e:
        logger.error(f"Failed to send trial expiring notification to {user_email}: {str(e)}", exc_info=True)
        return False


async def send_trial_expired_notification_async(
    user_email: str,
    user_id: str,
    downgraded_to_free: bool,
    plan_name: str
) -> bool:
    """
    Send email notification that trial has expired (async version).

    Args:
        user_email: User's email address
        user_id: User ID for tracking
        downgraded_to_free: Whether user was downgraded to free plan
        plan_name: Name of the subscription plan that expired

    Returns:
        True if email sent successfully, False otherwise
    """
    from src.services.email_service import EmailService
    from src.api.database.async_database import get_async_db_context
    from uuid import UUID

    try:
        async with get_async_db_context() as db:
            email_service = EmailService(db)

            if downgraded_to_free:
                html_content = f"""
                    <h2>Your {plan_name} Trial Has Ended</h2>
                    <p>Hello,</p>
                    <p>Your {plan_name} trial has expired and you've been moved to our <strong>Free Plan</strong>.</p>
                    <p>You can still use Rext AI with our free plan features, but some premium features are now unavailable.</p>
                    <h3>Want to upgrade?</h3>
                    <p>Unlock all premium features by subscribing to a paid plan:</p>
                    <ul>
                        <li>Unlimited workspaces</li>
                        <li>Advanced analytics</li>
                        <li>Priority support</li>
                        <li>And much more!</li>
                    </ul>
                    <p><a href="https://app.rext.com/settings/subscription" style="background-color: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Upgrade Now</a></p>
                    <p>Thank you for using Rext AI!</p>
                """
            else:
                html_content = f"""
                    <h2>Your {plan_name} Trial Has Ended</h2>
                    <p>Hello,</p>
                    <p>Your {plan_name} trial has expired.</p>
                    <p>Your subscription is now active with the payment method on file. You'll continue to enjoy all premium features!</p>
                    <p>Thank you for choosing Rext AI!</p>
                    <p><a href="https://app.rext.com/settings/subscription" style="color: #4CAF50;">View Subscription Details</a></p>
                """

            await email_service.send_email(
                to=user_email,
                subject=f"Your {plan_name} trial has ended",
                html=html_content,
                user_id=UUID(user_id),
                template_type="trial_expired",
                tags={"type": "subscription", "action": "trial_expired", "downgraded": str(downgraded_to_free)}
            )

            logger.info(f"Trial expired notification sent to {user_email} (downgraded: {downgraded_to_free})")
            return True

    except Exception as e:
        logger.error(f"Failed to send trial expired notification to {user_email}: {str(e)}", exc_info=True)
        return False


# Legacy sync wrappers for backwards compatibility
def send_trial_expiring_notification(user_email: str, days_remaining: int, plan_name: str, user_id: Optional[str] = None) -> bool:
    """
    Send email notification that trial is expiring soon (sync wrapper).

    Note: This is a synchronous wrapper for backwards compatibility.
    For new code, use send_trial_expiring_notification_async directly.
    """
    import asyncio
    if not user_id:
        logger.warning(f"user_id not provided for trial expiring notification to {user_email}")
        return False
    return asyncio.run(send_trial_expiring_notification_async(user_email, user_id, days_remaining, plan_name))


def send_trial_expired_notification(user_email: str, downgraded_to_free: bool, plan_name: str = "Premium", user_id: Optional[str] = None) -> bool:
    """
    Send email notification that trial has expired (sync wrapper).

    Note: This is a synchronous wrapper for backwards compatibility.
    For new code, use send_trial_expired_notification_async directly.
    """
    import asyncio
    if not user_id:
        logger.warning(f"user_id not provided for trial expired notification to {user_email}")
        return False
    return asyncio.run(send_trial_expired_notification_async(user_email, user_id, downgraded_to_free, plan_name))
