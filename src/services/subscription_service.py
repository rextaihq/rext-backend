"""
Subscription Service - Business Logic for Subscription Operations

This service encapsulates all business logic related to user subscriptions,
including plan management, usage tracking, trials, and plan changes.

Responsibilities:
- Subscription creation with trial logic
- Plan upgrades and downgrades with validation
- Subscription cancellation
- Usage calculation and limit validation
- Trial status tracking

Does NOT:
- Handle HTTP requests/responses (that's routes)
- Commit transactions (that's decorators/routes)
- Process payments (that's payment service - future)
"""

from typing import Dict, Any, Optional, List
from uuid import UUID
from datetime import datetime, timedelta, timezone
from fastapi import BackgroundTasks
from src.services.notification_helper import schedule_if_allowed
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.cache.decorators import invalidate_cache
from src.api.models.subscription_models.subscriptions import (
    UserSubscription,
    SubscriptionStatus,
    BillingPeriod,
    subscription_grants_access
)
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.knowledge_models.knowledge_model import (
    KnowledgeFiles,
    TextKnowledge,
    Website
)
from src.utils.logger import logger
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    RextValidationException,
    ResourceNotFoundException
)
from src.providers.payment.provider_factory import get_payment_provider_singleton
from src.services.audit_logger import audit_logger
from src.api.lib.sentry_config import capture_payment_exception


class SubscriptionService:
    """Service for subscription business logic"""

    def __init__(self, db: AsyncSession):
        """
        Initialize SubscriptionService.

        Args:
            db: Async database session
        """
        self.db = db
        self.payment_provider = get_payment_provider_singleton()

    async def subscribe(
        self,
        user_id: UUID,
        plan_id: UUID,
        billing_period: BillingPeriod,
        payment_method_id: Optional[str] = None
    ) -> UserSubscription:
        """
        Create new subscription with plan validation.

        Business Rules:
        - User cannot have duplicate active subscriptions
        - Plan must exist and be active
        - Free plans: Activated immediately
        - Paid plans: Start with 14-day trial
        - Usage reset date set to 30 days from start

        Args:
            user_id: User UUID
            plan_id: Subscription plan UUID
            billing_period: monthly, yearly, or lifetime
            payment_method_id: Optional payment method (for payment provider integration)

        Returns:
            UserSubscription object

        Raises:
            DuplicateResourceException: If user already has active subscription
            ResourceNotFoundException: If plan not found or inactive
        """
        # Check if user already has an active subscription. get_subscription_by_user()
        # also returns a cancelled subscription still in its paid-through grace period
        # (so credit/plan-limit checks keep working) - that must NOT block a fresh
        # subscribe here, otherwise a cancelled user could never resubscribe until
        # their old grace period fully expired.
        existing_subscription = await self.get_subscription_by_user(user_id)
        if existing_subscription and existing_subscription.status != SubscriptionStatus.CANCELLED:
            raise DuplicateResourceException(
                message="User already has an active subscription. Use upgrade endpoint to change plans.",
                resource_type="subscription",
                conflicting_field="user_id",
                conflicting_value=str(user_id)
            )

        # Get the plan and validate it's active
        plan = await self._get_plan_or_404(plan_id, active_only=True)

        # Determine if this is a trial (paid plans get 14 days trial)
        is_trial = plan.price_monthly > 0 or plan.price_yearly > 0
        trial_days = 14 if is_trial else 0

        # Create subscription
        new_subscription = UserSubscription(
            user_id=user_id,
            plan_id=plan_id,
            status=SubscriptionStatus.TRIAL if is_trial else SubscriptionStatus.ACTIVE,
            billing_period=billing_period,
            start_date=datetime.now(timezone.utc),
            trial_end_date=datetime.now(timezone.utc) + timedelta(days=trial_days) if is_trial else None,
            current_api_calls=0,
            usage_reset_date=datetime.now(timezone.utc) + timedelta(days=30),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )

        self.db.add(new_subscription)
        await self.db.flush()
        await self.db.refresh(new_subscription)

        # Invalidate subscription tier cache
        await invalidate_cache(f"user:subscription_tier:{user_id}:*")

        logger.info(
            f"User {user_id} subscribed to plan: {plan.name} ({billing_period.value})",
            extra={"user_id": str(user_id), "plan_id": str(plan_id), "is_trial": is_trial}
        )

        # Audit log
        if is_trial:
            audit_logger.log_trial_started(
                user_id=user_id,
                subscription_id=new_subscription.id,
                plan_name=plan.name,
                trial_days=trial_days,
                trial_end_date=new_subscription.trial_end_date,
            )
        else:
            audit_logger.log_subscription_created(
                user_id=user_id,
                subscription_id=new_subscription.id,
                plan_id=plan_id,
                plan_name=plan.name,
                billing_period=billing_period.value,
                is_trial=False,
            )

        return new_subscription

    async def create_checkout(
        self,
        user_id: UUID,
        plan_id: UUID,
        billing_period: BillingPeriod,
        success_url: str,
        cancel_url: str,
        discount_code: Optional[str] = None,
        affiliate_code: Optional[str] = None,
        skip_subscription_check: bool = False
    ) -> Dict[str, str]:
        """
        Create checkout session with LemonSqueezy.

        Business Rules:
        - User cannot have existing active subscription (they should upgrade instead)
        - Plan must exist and be active
        - Gets or creates LemonSqueezy customer for user
        - Creates checkout session with appropriate variant
        - Subscription is created later via webhook after successful payment

        Args:
            user_id: User UUID
            plan_id: Subscription plan UUID
            billing_period: monthly or yearly
            success_url: URL to redirect after successful checkout
            cancel_url: URL to redirect if checkout is cancelled
            discount_code: Optional discount/promo code to apply
            affiliate_code: Optional affiliate/referral code for tracking

        Returns:
            Dict with checkout_url and session_id

        Raises:
            DuplicateResourceException: If user already has active subscription
            ResourceNotFoundException: If plan not found or inactive
            RextValidationException: If variant ID not configured for plan
        """
        # Check if user already has an active subscription
        # Allow checkout if user is on free or trial plan (they can upgrade via checkout),
        # or if their existing subscription is already cancelled (still shows up here
        # because get_subscription_by_user() keeps it visible through its paid-through
        # grace period for credit/limit purposes) - a cancelled user must be able to
        # resubscribe right away, not wait out their old grace period.
        existing_subscription = await self.get_subscription_by_user(user_id)
        if existing_subscription and not skip_subscription_check and existing_subscription.status != SubscriptionStatus.CANCELLED:
            logger.info(f"🔍 DEBUG: User has existing subscription on plan: {existing_subscription.plan.name}")
            # Users on free/trial plans can checkout to paid plans
            # Users on paid plans must use upgrade endpoint
            allowed_plans_for_checkout = ["free", "trial"]
            if existing_subscription.plan.name.lower() not in allowed_plans_for_checkout:
                logger.info(f"🔍 DEBUG: Plan is not free/trial ({existing_subscription.plan.name}), blocking checkout")
                raise DuplicateResourceException(
                    message="User already has an active subscription. Use upgrade endpoint to change plans.",
                    resource_type="subscription",
                    conflicting_field="user_id",
                    conflicting_value=str(user_id)
                )
            logger.info(f"🔍 DEBUG: Plan is {existing_subscription.plan.name}, allowing checkout to proceed")

        # Get and validate plan
        plan = await self._get_plan_or_404(plan_id, active_only=True)

        # Get variant ID based on billing period
        variant_id = None
        if billing_period == BillingPeriod.MONTHLY:
            variant_id = plan.lemonsqueezy_variant_id_monthly
        elif billing_period == BillingPeriod.YEARLY:
            variant_id = plan.lemonsqueezy_variant_id_yearly

        if not variant_id:
            raise RextValidationException(
                message=f"Plan {plan.name} does not have a {billing_period.value} variant configured",
                field_errors={"billing_period": [f"{billing_period.value} variant not available"]}
            )

        logger.info(f"🔍 DEBUG: Variant ID is {variant_id}")
        # Get user to retrieve/store customer ID
        result = await self.db.execute(
            select(Users).where(Users.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise ResourceNotFoundException(
                resource_type="User",
                resource_id=str(user_id),
                message="User not found"
            )

        # Get or create customer ID
        customer_id = user.provider_customer_id

        if not customer_id:
            # Create customer in payment provider
            customer_name = user.full_name or user.display_name or user.email
            customer_id = await self.payment_provider.create_customer(
                email=user.email,
                name=customer_name,
                metadata={
                    "user_id": str(user_id),
                    "full_name": user.full_name
                }
            )

            # Store customer ID in database
            user.provider_customer_id = customer_id
            await self.db.flush()

            logger.info(
                f"Created payment provider customer {customer_id} for user {user_id}",
                extra={"user_id": str(user_id), "customer_id": customer_id}
            )

        logger.info(f"🔍 DEBUG: Customer ID is {customer_id}")
        # Create checkout session
        try:
            checkout_session = await self.payment_provider.create_checkout_session(
                customer_id=customer_id,
                price_id=variant_id,
                success_url=success_url,
                cancel_url=cancel_url,
                discount_code=discount_code,
                metadata={
                    "user_id": str(user_id),
                    "plan_id": str(plan_id),
                    "billing_period": billing_period.value,
                    "discount_code": discount_code if discount_code else None,
                    "affiliate_code": affiliate_code if affiliate_code else None
                }
            )
        except Exception as e:
            logger.error(
                f"Payment provider error during checkout: {str(e)}",
                extra={"user_id": str(user_id), "plan_id": str(plan_id)}
            )
            raise RextValidationException(
                message="Failed to create checkout session. Please try again or contact support.",
                field_errors={"checkout": [str(e)]}
            )

        logger.info(
            f"Created checkout session {checkout_session.session_id} for user {user_id}",
            extra={
                "user_id": str(user_id),
                "plan_id": str(plan_id),
                "billing_period": billing_period.value,
                "session_id": checkout_session.session_id,
                "discount_code": discount_code if discount_code else None,
                "affiliate_code": affiliate_code if affiliate_code else None
            }
        )

        # Audit log
        audit_logger.log_checkout_created(
            user_id=user_id,
            plan_id=plan_id,
            plan_name=plan.name,  
            billing_period=billing_period.value,
            checkout_url=checkout_session.checkout_url,
            discount_code=discount_code,
            metadata={
                "session_id": checkout_session.session_id,
                "affiliate_code": affiliate_code,
            }
        )
        logger.info(f"Checkout session created for user {user_id}, checkout_url: {checkout_session.checkout_url}, session_id: {checkout_session.session_id}")
        return {
            "checkout_url": checkout_session.checkout_url,
            "session_id": checkout_session.session_id
        }

    async def upgrade(
        self,
        user_id: UUID,
        new_plan_id: UUID,
        billing_period: Optional[BillingPeriod] = None
    ) -> UserSubscription:
        """
        Upgrade subscription to higher tier.

        Business Rules:
        - User must have active subscription
        - New plan must be different from current plan
        - Current usage must not exceed new plan limits (for downgrades)
        - Billing period can be changed optionally
        - Updates are immediate

        Args:
            user_id: User UUID
            new_plan_id: New plan UUID
            billing_period: Optional new billing period

        Returns:
            Updated UserSubscription object

        Raises:
            ResourceNotFoundException: If no active subscription or plan not found
            RextValidationException: If same plan or usage exceeds limits
        """
        # Get current subscription
        current_subscription = await self.get_subscription_by_user(user_id)
        if not current_subscription:
            raise ResourceNotFoundException(
                resource_type="Subscription",
                resource_id=f"user:{user_id}",
                message="No active subscription found. Please subscribe first."
            )

        # Get current and new plans
        current_plan = await self._get_plan_or_404(current_subscription.plan_id)
        new_plan = await self._get_plan_or_404(new_plan_id, active_only=True)

        # Check if it's the same plan
        if current_subscription.plan_id == new_plan_id:
            # Only billing period change
            if billing_period and billing_period != current_subscription.billing_period:
                current_subscription.billing_period = billing_period
                current_subscription.updated_at = datetime.now(timezone.utc)
                await self.db.flush()
                await self.db.refresh(current_subscription)

                logger.info(
                    f"Billing period updated to {billing_period.value} for user {user_id}",
                    extra={"user_id": str(user_id)}
                )

                return current_subscription
            else:
                raise RextValidationException(
                    message="Already subscribed to this plan",
                    field_errors={"new_plan_id": ["Same as current plan"]}
                )

        # Calculate current usage
        current_usage = await self.calculate_usage(user_id)

        # Validate downgrade (check if current usage exceeds new plan limits)
        is_downgrade = self._is_downgrade(current_plan, new_plan, current_usage)

        if is_downgrade:
            # Check specific limits
            self._validate_downgrade_limits(new_plan, current_usage)

        # Get new variant ID based on billing period
        new_billing_period = billing_period or current_subscription.billing_period
        new_variant_id = None
        if new_billing_period == BillingPeriod.MONTHLY:
            new_variant_id = new_plan.lemonsqueezy_variant_id_monthly
        elif new_billing_period == BillingPeriod.YEARLY:
            new_variant_id = new_plan.lemonsqueezy_variant_id_yearly

        # Update subscription with payment provider if provider subscription exists
        if current_subscription.provider_subscription_id or current_subscription.lemonsqueezy_subscription_id:
            if new_variant_id:
                try:
                    provider_sub_id = current_subscription.lemonsqueezy_subscription_id or current_subscription.provider_subscription_id

                    # Update subscription with payment provider
                    await self.payment_provider.update_subscription(
                        subscription_id=provider_sub_id,
                        price_id=new_variant_id
                    )

                    logger.info(
                        f"Updated subscription {provider_sub_id} with payment provider to variant {new_variant_id}",
                        extra={
                            "user_id": str(user_id),
                            "subscription_id": provider_sub_id,
                            "new_variant_id": new_variant_id,
                            "old_plan": current_plan.name,
                            "new_plan": new_plan.name
                        }
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to update subscription with payment provider: {str(e)}",
                        extra={"user_id": str(user_id), "error": str(e)}
                    )

                    # Capture to Sentry (Phase 4, Task 4.2.1)
                    capture_payment_exception(
                        e,
                        operation="update_subscription",
                        user_id=str(user_id),
                        subscription_id=provider_sub_id,
                        plan_id=str(new_plan_id),
                        context={
                            "old_plan": current_plan.name,
                            "new_plan": new_plan.name,
                            "new_variant_id": new_variant_id,
                        }
                    )

                    raise RextValidationException(
                        message="Failed to update subscription with payment provider. Please try again.",
                        field_errors={"payment_provider": [str(e)]}
                    )
            else:
                logger.warning(
                    f"No variant ID found for plan {new_plan.name} with billing period {new_billing_period.value}",
                    extra={"plan_id": str(new_plan_id), "billing_period": new_billing_period.value}
                )

        # Update local subscription
        current_subscription.plan_id = new_plan_id
        if billing_period:
            current_subscription.billing_period = billing_period

        # Update variant ID if available
        if new_variant_id:
            current_subscription.lemonsqueezy_variant_id = new_variant_id

        if new_plan.credits_per_month is not None:
            current_subscription.current_credits = new_plan.credits_per_month
            current_subscription.credits_reset_date = datetime.now(timezone.utc) + timedelta(days=30)

        current_subscription.updated_at = datetime.now(timezone.utc)

        await self.db.flush()
        await self.db.refresh(current_subscription)

        # Invalidate subscription tier cache
        await invalidate_cache(f"user:subscription_tier:{user_id}:*")

        action = "downgraded" if is_downgrade else "upgraded"
        logger.info(
            f"User {user_id} {action} from {current_plan.name} to {new_plan.name}",
            extra={"user_id": str(user_id), "old_plan": current_plan.name, "new_plan": new_plan.name}
        )

        # Audit log
        if is_downgrade:
            audit_logger.log_subscription_downgraded(
                user_id=user_id,
                subscription_id=current_subscription.id,
                old_plan_name=current_plan.name,
                new_plan_name=new_plan.name,
                old_billing_period=current_subscription.billing_period.value,
                new_billing_period=new_billing_period.value,
            )
        else:
            audit_logger.log_subscription_upgraded(
                user_id=user_id,
                subscription_id=current_subscription.id,
                old_plan_name=current_plan.name,
                new_plan_name=new_plan.name,
                old_billing_period=current_subscription.billing_period.value,
                new_billing_period=new_billing_period.value,
            )

        return current_subscription

    async def downgrade(
        self,
        user_id: UUID,
        new_plan_id: UUID,
        billing_period: Optional[BillingPeriod] = None
    ) -> UserSubscription:
        """
        Downgrade subscription to lower tier.

        Business Rules:
        - Same as upgrade but explicitly for downgrades
        - Validates usage doesn't exceed new limits
        - Scheduled for next billing cycle (future enhancement)

        Args:
            user_id: User UUID
            new_plan_id: New plan UUID
            billing_period: Optional new billing period

        Returns:
            Updated UserSubscription object

        Raises:
            ResourceNotFoundException: If no active subscription
            RextValidationException: If usage exceeds new plan limits
        """
        # Downgrade uses same logic as upgrade (with validation)
        return await self.upgrade(user_id, new_plan_id, billing_period)

    async def cancel(
        self,
        user_id: UUID,
        reason: Optional[str] = None,
        cancel_immediately: bool = False,
        background_tasks: Optional[BackgroundTasks] = None,
        fail_on_provider_error: bool = False
    ) -> UserSubscription:
        """
        Cancel subscription.

        Business Rules:
        - Cancels subscription via payment provider (LemonSqueezy)
        - Status is set to CANCELLED immediately either way, so the UI reflects
          the cancellation right away and a repeat cancel attempt correctly
          finds no active subscription.
        - Credits/usage limits are left untouched and keep working until
          `end_date` (the paid-through period end) - see `get_subscription_by_user`
          / `subscription_grants_access`.
        - Cancellation reason logged for analytics

        Args:
            user_id: User UUID
            reason: Optional cancellation reason
            cancel_immediately: If True, cancel now; if False, at end of period
            background_tasks: Optional background tasks for notifications
            fail_on_provider_error: If True, raise exception if payment provider call fails

        Returns:
            Updated UserSubscription object

        Raises:
            ResourceNotFoundException: If no active subscription
            RextValidationException: If payment provider cancellation fails and fail_on_provider_error is True
        """
        # Get current subscription
        subscription = await self.get_subscription_by_user(user_id)
        if not subscription or subscription.status == SubscriptionStatus.CANCELLED:
            # get_subscription_by_user() also returns cancelled-but-in-grace-period
            # subscriptions (so callers can keep showing plan/credits); but for
            # cancelling itself, an already-cancelled subscription must not be
            # cancellable again.
            raise ResourceNotFoundException(
                resource_type="Subscription",
                resource_id=f"user:{user_id}",
                message="No active subscription found"
            )

        # Cancel subscription with payment provider if provider subscription exists
        if subscription.provider_subscription_id or subscription.lemonsqueezy_subscription_id:
            try:
                provider_sub_id = subscription.lemonsqueezy_subscription_id or subscription.provider_subscription_id

                # Cancel with payment provider
                await self.payment_provider.cancel_subscription(
                    subscription_id=provider_sub_id,
                    at_period_end=not cancel_immediately
                )

                logger.info(
                    f"Cancelled subscription {provider_sub_id} with payment provider",
                    extra={
                        "user_id": str(user_id),
                        "subscription_id": provider_sub_id,
                        "at_period_end": not cancel_immediately
                    }
                )
            except Exception as e:
                logger.error(
                    f"Failed to cancel subscription with payment provider: {str(e)}",
                    extra={"user_id": str(user_id), "error": str(e)}
                )

                # Capture to Sentry (Phase 4, Task 4.2.1)
                capture_payment_exception(
                    e,
                    operation="cancel_subscription",
                    user_id=str(user_id),
                    subscription_id=provider_sub_id,
                    context={
                        "cancel_immediately": cancel_immediately,
                        "at_period_end": not cancel_immediately,
                    }
                )

                if fail_on_provider_error:
                    raise RextValidationException(
                        message="Payment provider cancellation failed; local cancellation aborted",
                        context={"user_id": str(user_id), "provider_error": str(e)}
                    )

                # Continue with local cancellation even if provider cancellation fails for non-admin paths
                # This ensures we don't leave the user stuck

        # Update local subscription
        subscription.cancelled_at = datetime.now(timezone.utc)

        # Store cancellation reason
        if reason:
            subscription.cancellation_reason = reason
            logger.info(f"Cancellation reason stored for subscription {subscription.id}")
        subscription.cancel_at_period_end = not cancel_immediately

        # Status flips to CANCELLED immediately in both cases - the UI shows the
        # cancellation right away and a second cancel attempt correctly sees no
        # active subscription. Credits/usage limits are unaffected by this: they
        # key off `subscription_grants_access()` (status ACTIVE/TRIAL, OR
        # CANCELLED with `end_date` still in the future), not off this status
        # flip, so the user keeps their credits until `end_date` below.
        subscription.status = SubscriptionStatus.CANCELLED

        if cancel_immediately:
            # Immediate cancellation cuts off access/credits right now - end_date
            # must be "now", not a future billing-period boundary, since
            # subscription_grants_access() treats any future end_date as a live
            # grace period.
            subscription.end_date = datetime.now(timezone.utc)
        else:
            # Deferred cancellation: record when the paid-through period ends so
            # the UI/email can show it and credits/limits keep working until then.
            if subscription.renews_at:
                subscription.end_date = subscription.renews_at
            elif subscription.billing_period == BillingPeriod.MONTHLY:
                subscription.end_date = subscription.usage_reset_date
            elif subscription.billing_period == BillingPeriod.YEARLY:
                subscription.end_date = subscription.start_date + timedelta(days=365)
            else:  # LIFETIME
                subscription.end_date = None

        subscription.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(subscription)

        # Invalidate subscription tier cache
        await invalidate_cache(f"user:subscription_tier:{user_id}:*")

        logger.info(
            f"User {user_id} cancelled subscription (immediately={cancel_immediately})",
            extra={"user_id": str(user_id), "reason": reason}
        )

        if reason:
            logger.info(f"Cancellation reason: {reason}")

        # Audit log
        audit_logger.log_subscription_cancelled(
            user_id=user_id,
            subscription_id=subscription.id,
            plan_name=subscription.plan.name if subscription.plan else "Unknown",
            reason=reason,
            cancel_immediately=cancel_immediately,
        )

        # Send in-app notification
        if background_tasks:
            await schedule_if_allowed(
                db=self.db,
                user_id=str(user_id),
                background_tasks=background_tasks,
                pref_flag="billing_subscription_cancelled",
                message="Your subscription has been cancelled.",
                payload={
                    "subscription_id": str(subscription.id),
                    "plan_name": subscription.plan.name if subscription.plan else "Unknown",
                    "end_date": subscription.end_date.isoformat() if subscription.end_date else None,
                    "cancel_immediately": cancel_immediately
                }
            )

        return subscription

    async def calculate_usage(self, user_id: UUID) -> Dict[str, int]:
        """
        Calculate current usage across all resources.

        Args:
            user_id: User UUID

        Returns:
            Dict with usage counts:
            {
                "workspaces": count,
                "members": count,
                "topics": count,
                "knowledge_files": count,
                "knowledge_text": count,
                "knowledge_web": count,
                "knowledge_items": count
            }
        """
        # Count workspaces owned by user (excluding soft-deleted ones)
        workspaces_result = await self.db.execute(
            select(func.count(WorkspaceModel.id)).where(
                WorkspaceModel.user_id == user_id,
                WorkspaceModel.deleted_at.is_(None)
            )
        )
        workspaces_count = workspaces_result.scalar() or 0

        # Count workspace members across all user's active workspaces
        members_result = await self.db.execute(
            select(func.count(WorkspaceMembers.id))
            .join(WorkspaceModel, WorkspaceMembers.workspace_id == WorkspaceModel.id)
            .where(
                and_(
                    WorkspaceModel.user_id == user_id,
                    WorkspaceModel.deleted_at.is_(None),
                    WorkspaceMembers.status == "active"  # Only count active members
                )
            )
        )
        members_count = members_result.scalar() or 0

        # Count knowledge files
        files_result = await self.db.execute(
            select(func.count(KnowledgeFiles.id))
            .join(WorkspaceModel)
            .where(
                WorkspaceModel.user_id == user_id,
                WorkspaceModel.deleted_at.is_(None)
            )
        )
        knowledge_files_count = files_result.scalar() or 0

        # Count text knowledge
        text_result = await self.db.execute(
            select(func.count(TextKnowledge.id))
            .join(WorkspaceModel)
            .where(
                WorkspaceModel.user_id == user_id,
                WorkspaceModel.deleted_at.is_(None)
            )
        )
        knowledge_text_count = text_result.scalar() or 0

        # Count websites
        web_result = await self.db.execute(
            select(func.count(Website.id))
            .join(WorkspaceModel)
            .where(
                WorkspaceModel.user_id == user_id,
                WorkspaceModel.deleted_at.is_(None)
            )
        )
        knowledge_web_count = web_result.scalar() or 0

        # Total knowledge items
        total_knowledge = knowledge_files_count + knowledge_text_count + knowledge_web_count

        return {
            "workspaces": workspaces_count,
            "members": members_count,
            "knowledge_files": knowledge_files_count,
            "knowledge_text": knowledge_text_count,
            "knowledge_web": knowledge_web_count,
            "knowledge_items": total_knowledge  # For backward compatibility
        }

    async def check_trial_status(self, user_id: UUID) -> Dict[str, Any]:
        """
        Check trial status and expiration.

        Args:
            user_id: User UUID

        Returns:
            Dict with:
            {
                "is_trial": bool,
                "trial_end_date": datetime or None,
                "days_remaining": int or None,
                "trial_expired": bool
            }
        """
        subscription = await self.get_subscription_by_user(user_id)

        if not subscription:
            return {
                "is_trial": False,
                "trial_end_date": None,
                "days_remaining": None,
                "trial_expired": False
            }

        is_trial = subscription.status == SubscriptionStatus.TRIAL
        trial_end_date = subscription.trial_end_date
        days_remaining = None
        trial_expired = False

        if is_trial and trial_end_date:
            days_remaining = (trial_end_date - datetime.now(timezone.utc)).days
            trial_expired = days_remaining < 0

        return {
            "is_trial": is_trial,
            "trial_end_date": trial_end_date,
            "days_remaining": max(0, days_remaining) if days_remaining is not None else None,
            "trial_expired": trial_expired
        }

    async def validate_plan_limits(
        self,
        user_id: UUID,
        resource_type: str,
        increment: int = 1
    ) -> bool:
        """
        Validate if user can add resources within plan limits.

        Args:
            user_id: User UUID
            resource_type: 'workspace', 'topic', or 'knowledge'
            increment: Number of resources to add (default: 1)

        Returns:
            True if within limits

        Raises:
            ResourceNotFoundException: If no active subscription
            RextValidationException: If exceeds limits
        """
        subscription = await self.get_subscription_by_user(user_id)
        if not subscription:
            raise ResourceNotFoundException(
                resource_type="Subscription",
                resource_id=f"user:{user_id}",
                message="No active subscription found"
            )

        plan = await self._get_plan_or_404(subscription.plan_id)
        current_usage = await self.calculate_usage(user_id)

        # Map resource type to plan limit
        limit_map = {
            "workspace": (plan.max_workspaces, current_usage["workspaces"]),
            "knowledge": (plan.max_knowledge_items, current_usage["knowledge_items"])
        }

        if resource_type not in limit_map:
            raise RextValidationException(
                message=f"Invalid resource type: {resource_type}",
                field_errors={"resource_type": ["Must be workspace or knowledge"]}
            )

        max_allowed, current_count = limit_map[resource_type]

        # -1 means unlimited
        if max_allowed == -1:
            return True

        new_count = current_count + increment
        if new_count > max_allowed:
            raise RextValidationException(
                message=f"Plan limit exceeded: {resource_type}",
                field_errors={
                    resource_type: [
                        f"Current: {current_count}, Limit: {max_allowed}, Requested: {increment}"
                    ]
                }
            )

        return True

    async def get_subscription_by_user(self, user_id: UUID) -> Optional[UserSubscription]:
        """
        Get user's active subscription with plan eagerly loaded.

        Also returns a subscription the user has already cancelled if its
        `end_date` hasn't passed yet, so plan/credit info keeps showing (and
        credit/usage limiters keep granting access) through the paid-through
        grace period. Callers that need to know whether the subscription is
        cancellable again should check `subscription.status` explicitly.

        Args:
            user_id: User UUID

        Returns:
            UserSubscription object or None
        """
        # Use CASE statement to prioritize ACTIVE (1) over everything else (0)
        from sqlalchemy import case
        priority = case(
            (UserSubscription.status == SubscriptionStatus.ACTIVE, 1),
            else_=0
        )

        result = await self.db.execute(
            select(UserSubscription).options(
                selectinload(UserSubscription.plan)
            ).where(
                UserSubscription.user_id == user_id,
                subscription_grants_access()
            ).order_by(
                # Prioritize ACTIVE (1) over TRIAL/grace-period-cancelled (0), then most recent
                priority.desc(),
                UserSubscription.created_at.desc()
            ).limit(1)
        )
        return result.scalar_one_or_none()

    async def get_plan_by_id(self, plan_id: UUID) -> SubscriptionPlan:
        """
        Get subscription plan by ID.

        Args:
            plan_id: Plan UUID

        Returns:
            SubscriptionPlan object

        Raises:
            ResourceNotFoundException: If plan not found
        """
        return await self._get_plan_or_404(plan_id, active_only=False)

    async def get_subscription_history(
        self,
        user_id: UUID,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get subscription history for user with plan details.

        Args:
            user_id: User UUID
            limit: Maximum number of records

        Returns:
            List of subscriptions with plan details
        """
        subscriptions_result = await self.db.execute(
            select(UserSubscription).where(
                UserSubscription.user_id == user_id
            ).order_by(UserSubscription.created_at.desc()).limit(limit)
        )
        subscriptions = subscriptions_result.scalars().all()

        subscriptions_data = []
        for sub in subscriptions:
            sub_data = sub.to_dict()
            # Add plan name
            try:
                plan = await self.get_plan_by_id(sub.plan_id)
                sub_data["plan_name"] = plan.name
                sub_data["plan_display_name"] = plan.display_name
            except ResourceNotFoundException:
                sub_data["plan_name"] = "Unknown"
                sub_data["plan_display_name"] = "Unknown"
            subscriptions_data.append(sub_data)

        return subscriptions_data

    async def get_customer_portal_url(
        self,
        user_id: UUID,
        return_url: str
    ) -> Optional[str]:
        """
        Get customer portal URL for subscription management.

        Generates a LemonSqueezy customer portal URL where users can:
        - Update payment methods
        - View invoices
        - Cancel subscription
        - Update billing information

        Args:
            user_id: User UUID
            return_url: URL to return to after portal session

        Returns:
            Customer portal URL if subscription exists with provider, None otherwise
        """
        # Get user to retrieve customer ID
        result = await self.db.execute(
            select(Users).where(Users.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user or not user.provider_customer_id:
            logger.warning(
                f"Cannot generate portal URL: User {user_id} has no provider_customer_id",
                extra={"user_id": str(user_id)}
            )
            return None

        try:
            # Generate portal session URL
            portal_url = await self.payment_provider.create_portal_session(
                customer_id=user.provider_customer_id,
                return_url=return_url
            )

            logger.info(
                f"Generated customer portal URL for user {user_id}",
                extra={"user_id": str(user_id)}
            )

            return portal_url

        except Exception as e:
            logger.error(
                f"Failed to create customer portal session: {str(e)}",
                extra={"user_id": str(user_id), "error": str(e)}
            )

            # Capture to Sentry (Phase 4, Task 4.2.1)
            capture_payment_exception(
                e,
                operation="customer_portal",
                user_id=str(user_id),
                customer_id=user.provider_customer_id,
                context={
                    "return_url": return_url,
                }
            )

            return None

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    async def _get_plan_or_404(
        self,
        plan_id: UUID,
        active_only: bool = False
    ) -> SubscriptionPlan:
        """
        Get subscription plan or raise 404 (cached).

        Plans are cached for 15 minutes since they rarely change.

        Args:
            plan_id: Plan UUID
            active_only: If True, only return active plans

        Returns:
            SubscriptionPlan object

        Raises:
            ResourceNotFoundException: If plan not found or not active
        """
        # Try cache first
        from src.api.cache.redis_client import cache
        cache_key = f"subscription:plan:{plan_id}:active={active_only}"

        if cache.is_enabled:
            cached_plan = await cache.get(cache_key)
            if cached_plan is not None:
                # Reconstruct the SubscriptionPlan object
                plan = SubscriptionPlan(**cached_plan)
                return plan

        # Cache miss - query database
        query = select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id)

        if active_only:
            query = query.where(SubscriptionPlan.is_active == True)

        result = await self.db.execute(query)
        plan = result.scalar_one_or_none()

        if not plan:
            raise ResourceNotFoundException(
                resource_type="SubscriptionPlan",
                resource_id=str(plan_id),
                message="Subscription plan not found" + (" or is inactive" if active_only else "")
            )

        # Cache the result for 15 minutes (plans rarely change)
        if cache.is_enabled:
            plan_dict = {
                "id": plan.id,
                "name": plan.name,
                "display_name": plan.display_name,
                "price_monthly": float(plan.price_monthly) if plan.price_monthly is not None else 0.0,
                "price_yearly": float(plan.price_yearly) if plan.price_yearly is not None else 0.0,
                "max_workspaces": plan.max_workspaces,
                "max_members_per_workspace": plan.max_members_per_workspace,
                "max_topics": plan.max_topics,
                "max_knowledge_items": plan.max_knowledge_items,
                "max_api_calls_per_month": plan.max_api_calls_per_month,
                "lemonsqueezy_variant_id_monthly": plan.lemonsqueezy_variant_id_monthly,
                "lemonsqueezy_variant_id_yearly": plan.lemonsqueezy_variant_id_yearly,
                "is_active": plan.is_active,
                "created_at": plan.created_at,
                "updated_at": plan.updated_at
            }
            await cache.set(cache_key, plan_dict, ttl=900)  # 15 minutes

        return plan

    def _is_downgrade(
        self,
        current_plan: SubscriptionPlan,
        new_plan: SubscriptionPlan,
        current_usage: Dict[str, int]
    ) -> bool:
        """
        Determine if plan change is a downgrade.

        A downgrade is when:
        - New plan price is lower than current plan
        - OR new plan limits are lower than current usage

        Args:
            current_plan: Current SubscriptionPlan
            new_plan: New SubscriptionPlan
            current_usage: Current usage dict

        Returns:
            True if downgrade, False otherwise
        """
        # Price-based check (guard against None)
        current_price = float(current_plan.price_monthly or 0)
        new_price = float(new_plan.price_monthly or 0)
        is_price_downgrade = new_price < current_price

        # Usage-based check (guard against None)
        is_usage_downgrade = (
            (new_plan.max_workspaces is not None and new_plan.max_workspaces != -1 and new_plan.max_workspaces < current_usage["workspaces"]) or
            (new_plan.max_knowledge_items is not None and new_plan.max_knowledge_items != -1 and new_plan.max_knowledge_items < current_usage["knowledge_items"])
        )

        return is_price_downgrade or is_usage_downgrade

    def _validate_downgrade_limits(
        self,
        new_plan: SubscriptionPlan,
        current_usage: Dict[str, int]
    ) -> None:
        """
        Validate downgrade doesn't exceed new plan limits.

        Args:
            new_plan: New SubscriptionPlan
            current_usage: Current usage dict

        Raises:
            RextValidationException: If usage exceeds new plan limits
        """
        # Check workspace limit
        if new_plan.max_workspaces is not None and new_plan.max_workspaces != -1 and current_usage["workspaces"] > new_plan.max_workspaces:
            raise RextValidationException(
                message=f"Cannot downgrade: You have {current_usage['workspaces']} workspaces, new plan allows {new_plan.max_workspaces}",
                field_errors={"new_plan_id": ["Workspace limit exceeded"]}
            )

        # Check knowledge items limit
        if new_plan.max_knowledge_items is not None and new_plan.max_knowledge_items != -1 and current_usage["knowledge_items"] > new_plan.max_knowledge_items:
            raise RextValidationException(
                message=f"Cannot downgrade: You have {current_usage['knowledge_items']} knowledge items, new plan allows {new_plan.max_knowledge_items}",
                field_errors={"new_plan_id": ["Knowledge items limit exceeded"]}
            )
