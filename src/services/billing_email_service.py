"""
Billing Email Service

Handles sending billing-related emails for subscriptions and payments.
"""

from typing import Dict, Any, Optional, List
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import BackgroundTasks

from src.api.models.user_models.users import Users
from src.api.models.user_models.notification_preferences import NotificationPreferences
from src.providers.email.factory import get_email_provider
from src.utils.logger import logger

from emails.templates.billing import (
    render_subscription_created_email,
    render_payment_succeeded_email,
    render_payment_failed_email,
    render_subscription_cancelled_email,
    render_trial_ending_email,
    render_subscription_renewed_email,
    render_payment_dunning_1_day_email,
    render_payment_dunning_3_days_email,
    render_payment_dunning_6_days_email,
    render_subscription_suspended_email,
    render_payment_recovered_email,
)


class BillingEmailService:
    """Service for sending billing-related emails"""

    def __init__(self, db: AsyncSession):
        """Initialize billing email service"""
        self.db = db
        self.email_provider = get_email_provider()

    async def send_subscription_created_email(
        self,
        user_id: UUID,
        plan_name: str,
        plan_price: str,
        billing_period: str,
        features: List[str],
        background_tasks: Optional[BackgroundTasks] = None
    ) -> bool:
        """
        Send subscription created email.

        Args:
            user_id: User UUID
            plan_name: Name of subscribed plan
            plan_price: Formatted price (e.g., "$29.99")
            billing_period: "monthly" or "yearly"
            features: List of plan features
            background_tasks: Optional background tasks

        Returns:
            bool: True if email sent/queued successfully
        """
        user = await self._get_user(user_id)
        if not user:
            return False

        if not await self._check_preferences(user_id, 'billing_notifications'):
            logger.info(f"User {user.email} has billing notifications disabled")
            return False

        html_content = render_subscription_created_email(
            user_name=user.full_name or user.display_name or user.email,
            plan_name=plan_name,
            plan_price=plan_price,
            billing_period=billing_period,
            features=features
        )

        return await self._send_email(
            to_email=user.email,
            subject=f"Welcome to {plan_name}!",
            html_content=html_content,
            background_tasks=background_tasks
        )

    async def send_payment_succeeded_email(
        self,
        user_id: UUID,
        plan_name: str,
        amount: str,
        payment_date: str,
        next_billing_date: str,
        invoice_url: Optional[str] = None,
        background_tasks: Optional[BackgroundTasks] = None
    ) -> bool:
        """Send payment succeeded email (receipt)."""
        user = await self._get_user(user_id)
        if not user:
            return False

        if not await self._check_preferences(user_id, 'billing_notifications'):
            return False

        html_content = render_payment_succeeded_email(
            user_name=user.full_name or user.display_name or user.email,
            plan_name=plan_name,
            amount=amount,
            payment_date=payment_date,
            next_billing_date=next_billing_date,
            invoice_url=invoice_url
        )

        return await self._send_email(
            to_email=user.email,
            subject="Payment Received - REXT",
            html_content=html_content,
            background_tasks=background_tasks
        )

    async def send_payment_failed_email(
        self,
        user_id: UUID,
        plan_name: str,
        amount: str,
        retry_date: str,
        background_tasks: Optional[BackgroundTasks] = None
    ) -> bool:
        """Send payment failed email."""
        user = await self._get_user(user_id)
        if not user:
            return False

        if not await self._check_preferences(user_id, 'billing_notifications'):
            return False

        html_content = render_payment_failed_email(
            user_name=user.full_name or user.display_name or user.email,
            plan_name=plan_name,
            amount=amount,
            retry_date=retry_date
        )

        return await self._send_email(
            to_email=user.email,
            subject="Payment Failed - Action Required",
            html_content=html_content,
            background_tasks=background_tasks
        )

    async def send_subscription_cancelled_email(
        self,
        user_id: UUID,
        plan_name: str,
        end_date: str,
        background_tasks: Optional[BackgroundTasks] = None
    ) -> bool:
        """Send subscription cancelled email."""
        user = await self._get_user(user_id)
        if not user:
            return False

        if not await self._check_preferences(user_id, 'billing_notifications'):
            return False

        html_content = render_subscription_cancelled_email(
            user_name=user.full_name or user.display_name or user.email,
            plan_name=plan_name,
            end_date=end_date
        )

        return await self._send_email(
            to_email=user.email,
            subject="Subscription Cancelled - REXT",
            html_content=html_content,
            background_tasks=background_tasks
        )

    async def send_trial_ending_email(
        self,
        user_id: UUID,
        plan_name: str,
        trial_end_date: str,
        days_remaining: int,
        background_tasks: Optional[BackgroundTasks] = None,
        user: Optional[Users] = None,
        preferences: Optional[NotificationPreferences] = None
    ) -> bool:
        """Send trial ending reminder email."""
        if not user:
            user = await self._get_user(user_id)
        if not user:
            return False

        if not await self._check_preferences(user_id, 'billing_notifications', preferences):
            return False

        html_content = render_trial_ending_email(
            user_name=user.full_name or user.display_name or user.email,
            plan_name=plan_name,
            trial_end_date=trial_end_date,
            days_remaining=days_remaining
        )

        return await self._send_email(
            to_email=user.email,
            subject=f"Your Trial Ends in {days_remaining} Days",
            html_content=html_content,
            background_tasks=background_tasks
        )

    async def send_trial_expired_email(
        self,
        user_id: UUID,
        plan_name: str,
        background_tasks: Optional[BackgroundTasks] = None,
        user: Optional[Users] = None,
        preferences: Optional[NotificationPreferences] = None
    ) -> bool:
        """Send trial expired email (trial has ended)."""
        if not user:
            user = await self._get_user(user_id)
        if not user:
            return False

        if not await self._check_preferences(user_id, 'billing_notifications', preferences):
            return False

        from emails.templates.billing.subscription_expiring_soon import render_subscription_expiring_soon_email

        html_content = render_subscription_expiring_soon_email(
            user_name=user.full_name or user.display_name or user.email,
            plan_name=plan_name,
            expiry_date=datetime.now(timezone.utc).strftime("%B %d, %Y"),
            days_remaining=0
        )

        return await self._send_email(
            to_email=user.email,
            subject="Your Trial Has Ended - REXT",
            html_content=html_content,
            background_tasks=background_tasks
        )

    async def send_subscription_renewed_email(
        self,
        user_id: UUID,
        plan_name: str,
        amount: str,
        renewal_date: str,
        next_billing_date: str,
        background_tasks: Optional[BackgroundTasks] = None
    ) -> bool:
        """Send subscription renewed email."""
        user = await self._get_user(user_id)
        if not user:
            return False

        if not await self._check_preferences(user_id, 'billing_notifications'):
            return False

        html_content = render_subscription_renewed_email(
            user_name=user.full_name or user.display_name or user.email,
            plan_name=plan_name,
            amount=amount,
            renewal_date=renewal_date,
            next_billing_date=next_billing_date
        )

        return await self._send_email(
            to_email=user.email,
            subject="Subscription Renewed - REXT",
            html_content=html_content,
            background_tasks=background_tasks
        )

    async def send_payment_recovered_email(
        self,
        user_id: UUID,
        plan_name: str,
        amount: str,
        recovery_date: str,
        next_billing_date: str,
        customer_portal_url: Optional[str] = None,
        background_tasks: Optional[BackgroundTasks] = None
    ) -> bool:
        """Send payment recovered email (welcome back)."""
        user = await self._get_user(user_id)
        if not user:
            return False

        if not await self._check_preferences(user_id, 'billing_notifications'):
            return False

        html_content = render_payment_recovered_email(
            user_name=user.full_name or user.display_name or user.email,
            plan_name=plan_name,
            amount=amount,
            recovery_date=recovery_date,
            next_billing_date=next_billing_date,
            customer_portal_url=customer_portal_url
        )

        return await self._send_email(
            to_email=user.email,
            subject=f"Payment Successful - {plan_name} Reactivated!",
            html_content=html_content,
            background_tasks=background_tasks
        )

    async def send_subscription_suspended_email(
        self,
        user_id: UUID,
        plan_name: str,
        amount: str,
        suspension_date: str,
        customer_portal_url: Optional[str] = None,
        background_tasks: Optional[BackgroundTasks] = None,
        **kwargs
    ) -> bool:
        """Send subscription suspended email."""
        user = await self._get_user(user_id)
        if not user:
            return False

        if not await self._check_preferences(user_id, 'billing_notifications'):
            return False

        html_content = render_subscription_suspended_email(
            user_name=user.full_name or user.display_name or user.email,
            plan_name=plan_name,
            amount=amount,
            suspension_date=suspension_date,
            customer_portal_url=customer_portal_url,
            **kwargs
        )

        return await self._send_email(
            to_email=user.email,
            subject="Subscription Suspended - REXT",
            html_content=html_content,
            background_tasks=background_tasks
        )

    async def send_payment_dunning_email(
        self,
        user_id: UUID,
        plan_name: str,
        amount: str,
        days_overdue: int,
        customer_portal_url: Optional[str] = None,
        background_tasks: Optional[BackgroundTasks] = None,
        **kwargs
    ) -> bool:
        """Send payment dunning reminder (1, 3, or 6 days)."""
        user = await self._get_user(user_id)
        if not user:
            return False

        if not await self._check_preferences(user_id, 'billing_notifications'):
            return False

        render_funcs = {
            1: render_payment_dunning_1_day_email,
            3: render_payment_dunning_3_days_email,
            6: render_payment_dunning_6_days_email,
        }

        render_func = render_funcs.get(days_overdue)
        if not render_func:
            logger.error(f"Invalid dunning day specified: {days_overdue}")
            return False

        html_content = render_func(
            user_name=user.full_name or user.display_name or user.email,
            plan_name=plan_name,
            amount=amount,
            customer_portal_url=customer_portal_url,
            **kwargs
        )

        return await self._send_email(
            to_email=user.email,
            subject=f"Payment Reminder: Your {plan_name} Subscription",
            html_content=html_content,
            background_tasks=background_tasks
        )

    async def _get_user(self, user_id: UUID) -> Optional[Users]:
        """Get user by ID."""
        query = select(Users).where(Users.id == user_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _check_preferences(self, user_id: UUID, preference_key: str, prefs: Optional[NotificationPreferences] = None) -> bool:
        """Check if user has billing notifications enabled."""
        if not prefs:
            query = select(NotificationPreferences).where(
                NotificationPreferences.user_id == user_id
            )
            result = await self.db.execute(query)
            prefs = result.scalar_one_or_none()

        if not prefs:
            return True  # Default to enabled if no preferences set

        # Check master email toggle first
        if not prefs.email_notifications:
            return False

        # Map billing preference keys to NotificationPreferences columns
        billing_pref_mapping = {
            "billing_notifications": "email_billing_updates",
            "payment_succeeded": "billing_payment_success",
            "payment_failed": "billing_payment_failed",
            "subscription_cancelled": "billing_subscription_cancelled",
            "trial_ending": "billing_trial_ending",
        }
        mapped_key = billing_pref_mapping.get(preference_key, preference_key)
        return getattr(prefs, mapped_key, True)
    
    
    async def _send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        background_tasks: Optional[BackgroundTasks] = None
    ) -> bool:
        """Send email via email provider."""
        try:
            if background_tasks:
                background_tasks.add_task(
                    self.email_provider.send_email,
                    to_email=to_email,
                    subject=subject,
                    html_content=html_content
                )
                logger.info(f"Billing email queued: {subject} to {to_email}")
            else:
                await self.email_provider.send_email(
                    to_email=to_email,
                    subject=subject,
                    html_content=html_content
                )
                logger.info(f"Billing email sent: {subject} to {to_email}")

            return True

        except Exception as e:
            logger.error(f"Failed to send billing email to {to_email}: {str(e)}")
            return False
