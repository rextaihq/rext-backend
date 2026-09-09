"""
Billing Email Service

Handles sending billing-related emails for subscriptions and payments.
Uses EmailService for consistent logging, retry, and fallback behavior.
"""

from typing import Dict, Any, Optional, List
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.api.config import get_settings
from src.api.models.user_models.users import Users
from src.api.models.user_models.notification_preferences import NotificationPreferences
from src.api.database.async_database import AsyncSessionLocal
from src.services.email_service import EmailService
from src.services.email_preferences_service import EmailPreferencesService
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
    render_refund_requested_admin_email,
    render_refund_issued_email,
    render_refund_approved_email,
    render_refund_rejected_email,
    render_refund_request_received_email,
)


async def send_billing_email_in_background(method: str, **kwargs) -> None:
    """Run one BillingEmailService method on a session of its own.

    Background tasks outlive the request that queued them: since FastAPI 0.106
    a `yield` dependency is torn down *before* background tasks run, so an
    email queued with the request's `db` would reach a closed session and fail
    silently. Opening a fresh session here is what makes queued mail actually
    send.

    Never raises: the refund it describes has already happened, so a mail
    failure must not surface as an error on an action that succeeded.

    Args:
        method: Name of the BillingEmailService coroutine to call.
        **kwargs: Passed straight to it.
    """
    try:
        async with AsyncSessionLocal() as db:
            await getattr(BillingEmailService(db), method)(**kwargs)
            await db.commit()
    except Exception:
        logger.warning(f"Failed to send {method} email", exc_info=True)


class BillingEmailService:
    """Service for sending billing-related emails via EmailService."""

    def __init__(self, db: AsyncSession):
        """Initialize billing email service with EmailService for consistent behavior."""
        self.db = db
        self.email_service = EmailService(db)
        self.preferences_service = EmailPreferencesService(db)
        # Real deployment URL — templates must never fall back to their
        # hardcoded https://app.rext.com defaults
        self.frontend_url = get_settings().FRONTEND_URL.rstrip("/")

    async def send_subscription_created_email(
        self,
        user_id: UUID,
        plan_name: str,
        plan_price: str,
        billing_period: str,
        features: List[str]
    ) -> bool:
        """
        Send subscription created email.

        Args:
            user_id: User UUID
            plan_name: Name of subscribed plan
            plan_price: Formatted price (e.g., "$29.99")
            billing_period: "monthly" or "yearly"
            features: List of plan features

        Returns:
            bool: True if email sent/queued successfully
        """
        user = await self._get_user(user_id)
        if not user:
            return False

        if not await self._check_preferences(user_id, "subscription_created"):
            logger.info(f"User {user.email} has subscription_created notifications disabled")
            return False

        html_content = render_subscription_created_email(
            user_name=user.full_name or user.display_name or user.email,
            plan_name=plan_name,
            plan_price=plan_price,
            billing_period=billing_period,
            features=features,
            dashboard_url=f"{self.frontend_url}/w/create",
            frontend_url=self.frontend_url
        )

        return await self._send_email(
            to_email=user.email,
            subject=f"Welcome to {plan_name}!",
            html_content=html_content,
            user_id=user_id,
            template_type="subscription_created",
        )

    async def send_payment_succeeded_email(
        self,
        user_id: UUID,
        plan_name: str,
        amount: str,
        payment_date: str,
        next_billing_date: str,
        invoice_url: Optional[str] = None
    ) -> bool:
        """Send payment succeeded email (receipt)."""
        user = await self._get_user(user_id)
        if not user:
            return False

        if not await self._check_preferences(user_id, "payment_succeeded"):
            return False

        html_content = render_payment_succeeded_email(
            user_name=user.full_name or user.display_name or user.email,
            plan_name=plan_name,
            amount=amount,
            payment_date=payment_date,
            next_billing_date=next_billing_date,
            invoice_url=invoice_url,
            dashboard_url=f"{self.frontend_url}/settings/subscription",
            frontend_url=self.frontend_url
        )

        return await self._send_email(
            to_email=user.email,
            subject="Payment Received - Rext AI",
            html_content=html_content,
            user_id=user_id,
            template_type="payment_succeeded",
        )

    async def send_payment_failed_email(
        self,
        user_id: UUID,
        plan_name: str,
        amount: str,
        retry_date: str
    ) -> bool:
        """Send payment failed email."""
        user = await self._get_user(user_id)
        if not user:
            return False

        if not await self._check_preferences(user_id, "payment_failed"):
            return False

        html_content = render_payment_failed_email(
            user_name=user.full_name or user.display_name or user.email,
            plan_name=plan_name,
            amount=amount,
            retry_date=retry_date,
            update_payment_url=f"{self.frontend_url}/settings/subscription",
            frontend_url=self.frontend_url
        )

        return await self._send_email(
            to_email=user.email,
            subject="Payment Failed - Action Required",
            html_content=html_content,
            user_id=user_id,
            template_type="payment_failed",
        )

    async def send_subscription_cancelled_email(
        self,
        user_id: UUID,
        plan_name: str,
        end_date: str
    ) -> bool:
        """Send subscription cancelled email."""
        user = await self._get_user(user_id)
        if not user:
            return False

        if not await self._check_preferences(user_id, "subscription_cancelled"):
            return False

        html_content = render_subscription_cancelled_email(
            user_name=user.full_name or user.display_name or user.email,
            plan_name=plan_name,
            end_date=end_date,
            # App root - it auto-selects/redirects the user into their workspace
            # (there is no standalone "/dashboard" route).
            workspace_url=self.frontend_url,
            reactivate_url=f"{self.frontend_url}/pricing",
            feedback_url=self.frontend_url,
            frontend_url=self.frontend_url
        )

        return await self._send_email(
            to_email=user.email,
            subject="Subscription Cancelled - Rext AI",
            html_content=html_content,
            user_id=user_id,
            template_type="subscription_cancelled",
        )

    async def send_trial_ending_email(
        self,
        user_id: UUID,
        plan_name: str,
        trial_end_date: str,
        days_remaining: int
    ) -> bool:
        """Send trial ending reminder email."""
        user = await self._get_user(user_id)
        if not user:
            return False

        if not await self._check_preferences(user_id, "trial_ending_soon"):
            return False

        html_content = render_trial_ending_email(
            user_name=user.full_name or user.display_name or user.email,
            plan_name=plan_name,
            trial_end_date=trial_end_date,
            days_remaining=days_remaining,
            upgrade_url=f"{self.frontend_url}/pricing",
            frontend_url=self.frontend_url
        )

        return await self._send_email(
            to_email=user.email,
            subject=f"Your Trial Ends in {days_remaining} Days",
            html_content=html_content,
            user_id=user_id,
            template_type="trial_ending_soon",
        )

    async def send_trial_expired_email(
        self,
        user_id: UUID,
        plan_name: str
    ) -> bool:
        """Send trial expired email (trial has ended)."""
        user = await self._get_user(user_id)
        if not user:
            return False

        # Use subscription_expiring_soon mapping as a proxy for trial expired if not specific
        if not await self._check_preferences(user_id, "subscription_expiring_soon"):
            return False

        from emails.templates.billing.subscription_expiring_soon import render_subscription_expiring_soon_email

        html_content = render_subscription_expiring_soon_email(
            user_name=user.full_name or user.display_name or user.email,
            plan_name=plan_name,
            expiry_date=datetime.now(timezone.utc).strftime("%B %d, %Y"),
            days_remaining=0,
            renew_url=f"{self.frontend_url}/settings/subscription",
            pricing_url=f"{self.frontend_url}/pricing",
            frontend_url=self.frontend_url
        )

        return await self._send_email(
            to_email=user.email,
            subject="Your Trial Has Ended - Rext AI",
            html_content=html_content,
            user_id=user_id,
            template_type="trial_expired",
        )

    async def send_subscription_renewed_email(
        self,
        user_id: UUID,
        plan_name: str,
        amount: str,
        renewal_date: str,
        next_billing_date: str
    ) -> bool:
        """Send subscription renewed email."""
        user = await self._get_user(user_id)
        if not user:
            return False

        # This doesn't have a direct mapping in EMAIL_TYPE_TO_COLUMN, 
        # using billing_payment_success column as proxy
        if not await self._check_preferences(user_id, "payment_succeeded"):
            return False

        html_content = render_subscription_renewed_email(
            user_name=user.full_name or user.display_name or user.email,
            plan_name=plan_name,
            amount=amount,
            renewal_date=renewal_date,
            next_billing_date=next_billing_date,
            dashboard_url=f"{self.frontend_url}/settings/subscription",
            frontend_url=self.frontend_url
        )

        return await self._send_email(
            to_email=user.email,
            subject="Subscription Renewed - Rext AI",
            html_content=html_content,
            user_id=user_id,
            template_type="subscription_renewed",
        )

    async def send_payment_recovered_email(
        self,
        user_id: UUID,
        plan_name: str,
        amount: str,
        recovery_date: str,
        next_billing_date: str,
        customer_portal_url: Optional[str] = None
    ) -> bool:
        """Send payment recovered email (welcome back)."""
        user = await self._get_user(user_id)
        if not user:
            return False

        if not await self._check_preferences(user_id, "payment_succeeded"):
            return False

        html_content = render_payment_recovered_email(
            user_name=user.full_name or user.display_name or user.email,
            plan_name=plan_name,
            amount=amount,
            recovery_date=recovery_date,
            next_billing_date=next_billing_date,
            customer_portal_url=customer_portal_url,
            manage_subscription_url=f"{self.frontend_url}/settings/subscription",
            frontend_url=self.frontend_url
        )

        return await self._send_email(
            to_email=user.email,
            subject=f"Payment Successful - {plan_name} Reactivated!",
            html_content=html_content,
            user_id=user_id,
            template_type="payment_recovered",
        )

    async def send_subscription_suspended_email(
        self,
        user_id: UUID,
        plan_name: str,
        amount: str,
        suspension_date: str,
        customer_portal_url: Optional[str] = None,
        **kwargs
    ) -> bool:
        """Send subscription suspended email."""
        user = await self._get_user(user_id)
        if not user:
            return False

        # Using payment_failed column as proxy for suspension notifications
        if not await self._check_preferences(user_id, "payment_failed"):
            return False

        kwargs.setdefault("update_payment_url", f"{self.frontend_url}/settings/subscription")
        kwargs.setdefault("reactivate_url", f"{self.frontend_url}/settings/subscription")
        kwargs.setdefault("frontend_url", self.frontend_url)

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
            subject="Subscription Suspended - Rext AI",
            html_content=html_content,
            user_id=user_id,
            template_type="subscription_suspended",
        )

    async def send_payment_dunning_email(
        self,
        user_id: UUID,
        plan_name: str,
        amount: str,
        days_overdue: int,
        customer_portal_url: Optional[str] = None,
        **kwargs
    ) -> bool:
        """Send payment dunning reminder (1, 3, or 6 days)."""
        user = await self._get_user(user_id)
        if not user:
            return False

        if not await self._check_preferences(user_id, "payment_failed"):
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

        kwargs.setdefault("update_payment_url", f"{self.frontend_url}/settings/subscription")
        kwargs.setdefault("frontend_url", self.frontend_url)

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
            user_id=user_id,
            template_type=f"payment_dunning_{days_overdue}_day",
        )

    async def send_refund_requested_admin_email(
        self,
        admin_user_id: UUID,
        customer_email: str,
        product_name: str,
        refund_amount: str,
        order_id: str,
        reason: str,
        requested_date: str,
    ) -> bool:
        """Alert a super admin that a customer has requested a refund.

        Deliberately not gated on billing notification preferences: those are
        the customer's marketing/billing choices, and this is operational mail
        to staff about work waiting for them.
        """
        admin = await self._get_user(admin_user_id)
        if not admin:
            return False

        html_content = render_refund_requested_admin_email(
            admin_name=admin.full_name or admin.display_name or admin.email,
            customer_email=customer_email,
            product_name=product_name,
            refund_amount=refund_amount,
            order_id=order_id,
            reason=reason,
            requested_date=requested_date,
            review_url=f"{self.frontend_url}/admin/refunds",
            frontend_url=self.frontend_url,
        )

        return await self._send_email(
            to_email=admin.email,
            subject=f"Refund requested: {refund_amount} by {customer_email}",
            html_content=html_content,
            user_id=admin_user_id,
            template_type="refund_requested_admin",
        )

    async def _send_refund_email(
        self,
        *,
        user_id: UUID,
        email_type: str,
        subject: str,
        render,
        **render_kwargs,
    ) -> bool:
        """Send one refund lifecycle email, honouring the user's preferences.

        The four refund emails differ only in template, subject and preference
        key, so the lookup, the preference check and the send live here once.

        Returns False when there is no such user or they have opted out of this
        kind of mail — a refund still happens either way; only the telling of
        it is optional.
        """
        user = await self._get_user(user_id)
        if not user:
            logger.warning(
                f"No user {user_id} to send {email_type} email to",
                extra={"user_id": str(user_id), "email_type": email_type},
            )
            return False

        if not await self._check_preferences(user_id, email_type):
            logger.info(
                f"Skipping {email_type} email: user has it turned off",
                extra={"user_id": str(user_id), "email_type": email_type},
            )
            return False

        html_content = render(
            user_name=user.full_name or user.display_name or user.email,
            frontend_url=self.frontend_url,
            **render_kwargs,
        )

        return await self._send_email(
            to_email=user.email,
            subject=subject,
            html_content=html_content,
            user_id=user_id,
            template_type=email_type,
        )

    async def send_refund_request_received_email(
        self,
        user_id: UUID,
        product_name: str,
        refund_amount: str,
        order_id: str,
        requested_date: str,
    ) -> bool:
        """Acknowledge a refund request the customer just raised."""
        return await self._send_refund_email(
            user_id=user_id,
            email_type="refund_requested",
            subject=f"We've received your refund request for {refund_amount}",
            render=render_refund_request_received_email,
            product_name=product_name,
            refund_amount=refund_amount,
            order_id=order_id,
            requested_date=requested_date,
        )

    async def send_refund_approved_email(
        self,
        user_id: UUID,
        product_name: str,
        refund_amount: str,
        order_id: str,
        requested_date: str,
        admin_note: Optional[str] = None,
    ) -> bool:
        """Tell the customer an admin approved their request.

        Sent when the decision is made, which is before any money moves — the
        payout has its own email.
        """
        return await self._send_refund_email(
            user_id=user_id,
            email_type="refund_approved",
            subject=f"Your refund of {refund_amount} has been approved",
            render=render_refund_approved_email,
            product_name=product_name,
            refund_amount=refund_amount,
            order_id=order_id,
            requested_date=requested_date,
            admin_note=admin_note,
        )

    async def send_refund_rejected_email(
        self,
        user_id: UUID,
        product_name: str,
        refund_amount: str,
        order_id: str,
        requested_date: str,
        admin_note: Optional[str] = None,
    ) -> bool:
        """Tell the customer their request was declined, with the reason."""
        return await self._send_refund_email(
            user_id=user_id,
            email_type="refund_rejected",
            subject="An update on your refund request",
            render=render_refund_rejected_email,
            product_name=product_name,
            refund_amount=refund_amount,
            order_id=order_id,
            requested_date=requested_date,
            admin_note=admin_note,
        )

    async def send_refund_issued_email(
        self,
        user_id: UUID,
        order_id: str,
        refund_amount: str,
        refund_date: str,
        original_plan_name: Optional[str] = None,
    ) -> bool:
        """Tell the customer the money has actually been sent back.

        Sent when a refund is recorded against the order — whether an admin
        processed it here or issued it from the LemonSqueezy dashboard.
        """
        return await self._send_refund_email(
            user_id=user_id,
            email_type="refund_issued",
            subject=f"Your refund of {refund_amount} is on its way",
            render=render_refund_issued_email,
            order_id=order_id,
            refund_amount=refund_amount,
            refund_date=refund_date,
            original_plan_name=original_plan_name,
        )

    async def _get_user(self, user_id: UUID) -> Optional[Users]:
        """Get user by ID."""
        query = select(Users).where(Users.id == user_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _check_preferences(self, user_id: UUID, email_type: str) -> bool:
        """Check if user has billing notifications enabled using centralized preferences service."""
        return await self.preferences_service.check_can_send(user_id, email_type)

    async def _send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        user_id: Optional[UUID] = None,
        template_type: Optional[str] = None
    ) -> bool:
        """Send email via EmailService for consistent logging and retry."""
        try:
            email_log = await self.email_service.send_email(
                to=to_email,
                subject=subject,
                html=html_content,
                user_id=user_id,
                template_type=template_type or "billing",
                tags={"category": "billing"},
            )
            return email_log.status in ("sent", "queued")
        except Exception as e:
            logger.error(
                f"Failed to send billing email to {to_email}",
                extra={
                    "error": str(e),
                    "subject": subject,
                    "template_type": template_type,
                }
            )
            return False
