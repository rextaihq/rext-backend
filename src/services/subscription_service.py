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

from typing import Dict, Any, Optional
from uuid import UUID
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import (
    UserSubscription,
    SubscriptionStatus,
    BillingPeriod
)
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.models.topic_models.topic_models import TopicsModel
from src.api.models.knowledge_models.knowledge_model import (
    KnowledgeFiles,
    TextKnowledge,
    Website
)
from src.utils.logger import logger
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    WrextValidationException,
    ResourceNotFoundException
)


class SubscriptionService:
    """Service for subscription business logic"""

    def __init__(self, db: AsyncSession):
        """
        Initialize SubscriptionService.

        Args:
            db: Async database session
        """
        self.db = db

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
            payment_method_id: Optional payment method (for Stripe integration)

        Returns:
            UserSubscription object

        Raises:
            DuplicateResourceException: If user already has active subscription
            ResourceNotFoundException: If plan not found or inactive
        """
        # Check if user already has an active subscription
        existing_subscription = await self.get_subscription_by_user(user_id)
        if existing_subscription:
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
            start_date=datetime.utcnow(),
            trial_end_date=datetime.utcnow() + timedelta(days=trial_days) if is_trial else None,
            current_api_calls=0,
            usage_reset_date=datetime.utcnow() + timedelta(days=30),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        self.db.add(new_subscription)
        await self.db.flush()
        await self.db.refresh(new_subscription)

        logger.info(
            f"User {user_id} subscribed to plan: {plan.name} ({billing_period.value})",
            extra={"user_id": str(user_id), "plan_id": str(plan_id), "is_trial": is_trial}
        )

        return new_subscription

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
            WrextValidationException: If same plan or usage exceeds limits
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
                current_subscription.updated_at = datetime.utcnow()
                await self.db.flush()
                await self.db.refresh(current_subscription)

                logger.info(
                    f"Billing period updated to {billing_period.value} for user {user_id}",
                    extra={"user_id": str(user_id)}
                )

                return current_subscription
            else:
                raise WrextValidationException(
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

        # Update subscription
        current_subscription.plan_id = new_plan_id
        if billing_period:
            current_subscription.billing_period = billing_period
        current_subscription.updated_at = datetime.utcnow()

        await self.db.flush()
        await self.db.refresh(current_subscription)

        action = "downgraded" if is_downgrade else "upgraded"
        logger.info(
            f"User {user_id} {action} from {current_plan.name} to {new_plan.name}",
            extra={"user_id": str(user_id), "old_plan": current_plan.name, "new_plan": new_plan.name}
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
            WrextValidationException: If usage exceeds new plan limits
        """
        # Downgrade uses same logic as upgrade (with validation)
        return await self.upgrade(user_id, new_plan_id, billing_period)

    async def cancel(
        self,
        user_id: UUID,
        reason: Optional[str] = None,
        cancel_immediately: bool = False
    ) -> UserSubscription:
        """
        Cancel subscription.

        Business Rules:
        - Immediate cancellation: End immediately, status set to CANCELLED
        - Deferred cancellation: End at billing period, status remains ACTIVE
        - Cancellation reason logged for analytics

        Args:
            user_id: User UUID
            reason: Optional cancellation reason
            cancel_immediately: If True, cancel now; if False, at end of period

        Returns:
            Updated UserSubscription object

        Raises:
            ResourceNotFoundException: If no active subscription
        """
        # Get current subscription
        subscription = await self.get_subscription_by_user(user_id)
        if not subscription:
            raise ResourceNotFoundException(
                resource_type="Subscription",
                resource_id=f"user:{user_id}",
                message="No active subscription found"
            )

        # Update subscription
        subscription.cancelled_at = datetime.utcnow()

        if cancel_immediately:
            subscription.status = SubscriptionStatus.CANCELLED
            subscription.end_date = datetime.utcnow()
        else:
            # Calculate end of billing period
            if subscription.billing_period == BillingPeriod.MONTHLY:
                subscription.end_date = subscription.usage_reset_date
            elif subscription.billing_period == BillingPeriod.YEARLY:
                subscription.end_date = subscription.start_date + timedelta(days=365)
            else:  # LIFETIME
                subscription.end_date = None  # No end date for lifetime

        subscription.updated_at = datetime.utcnow()

        await self.db.flush()
        await self.db.refresh(subscription)

        logger.info(
            f"User {user_id} cancelled subscription (immediately={cancel_immediately})",
            extra={"user_id": str(user_id), "reason": reason}
        )

        if reason:
            logger.info(f"Cancellation reason: {reason}")

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
                "topics": count,
                "knowledge_files": count,
                "knowledge_text": count,
                "knowledge_web": count
            }
        """
        # Count workspaces owned by user
        workspaces_result = await self.db.execute(
            select(func.count(WorkspaceModel.id)).where(WorkspaceModel.creator_id == user_id)
        )
        workspaces_count = workspaces_result.scalar() or 0

        # Count topics across all user's workspaces
        topics_result = await self.db.execute(
            select(func.count(TopicsModel.id))
            .join(WorkspaceModel)
            .where(WorkspaceModel.creator_id == user_id)
        )
        topics_count = topics_result.scalar() or 0

        # Count knowledge files
        files_result = await self.db.execute(
            select(func.count(KnowledgeFiles.id))
            .join(WorkspaceModel)
            .where(WorkspaceModel.creator_id == user_id)
        )
        knowledge_files_count = files_result.scalar() or 0

        # Count text knowledge
        text_result = await self.db.execute(
            select(func.count(TextKnowledge.id))
            .join(WorkspaceModel)
            .where(WorkspaceModel.creator_id == user_id)
        )
        knowledge_text_count = text_result.scalar() or 0

        # Count websites
        web_result = await self.db.execute(
            select(func.count(Website.id))
            .join(WorkspaceModel)
            .where(WorkspaceModel.creator_id == user_id)
        )
        knowledge_web_count = web_result.scalar() or 0

        # Total knowledge items
        total_knowledge = knowledge_files_count + knowledge_text_count + knowledge_web_count

        return {
            "workspaces": workspaces_count,
            "topics": topics_count,
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
            days_remaining = (trial_end_date - datetime.utcnow()).days
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
            WrextValidationException: If exceeds limits
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
            "topic": (plan.max_topics, current_usage["topics"]),
            "knowledge": (plan.max_knowledge_items, current_usage["knowledge_items"])
        }

        if resource_type not in limit_map:
            raise WrextValidationException(
                message=f"Invalid resource type: {resource_type}",
                field_errors={"resource_type": ["Must be workspace, topic, or knowledge"]}
            )

        max_allowed, current_count = limit_map[resource_type]

        # -1 means unlimited
        if max_allowed == -1:
            return True

        new_count = current_count + increment
        if new_count > max_allowed:
            raise WrextValidationException(
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
        Get user's active subscription.

        Args:
            user_id: User UUID

        Returns:
            UserSubscription object or None
        """
        result = await self.db.execute(
            select(UserSubscription).where(
                UserSubscription.user_id == user_id,
                UserSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL])
            )
        )
        return result.scalar_one_or_none()

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    async def _get_plan_or_404(
        self,
        plan_id: UUID,
        active_only: bool = False
    ) -> SubscriptionPlan:
        """
        Get subscription plan or raise 404.

        Args:
            plan_id: Plan UUID
            active_only: If True, only return active plans

        Returns:
            SubscriptionPlan object

        Raises:
            ResourceNotFoundException: If plan not found or not active
        """
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
        # Price-based check
        is_price_downgrade = new_plan.price_monthly < current_plan.price_monthly

        # Usage-based check
        is_usage_downgrade = (
            (new_plan.max_workspaces != -1 and new_plan.max_workspaces < current_usage["workspaces"]) or
            (new_plan.max_topics != -1 and new_plan.max_topics < current_usage["topics"]) or
            (new_plan.max_knowledge_items != -1 and new_plan.max_knowledge_items < current_usage["knowledge_items"])
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
            WrextValidationException: If usage exceeds new plan limits
        """
        # Check workspace limit
        if new_plan.max_workspaces != -1 and current_usage["workspaces"] > new_plan.max_workspaces:
            raise WrextValidationException(
                message=f"Cannot downgrade: You have {current_usage['workspaces']} workspaces, new plan allows {new_plan.max_workspaces}",
                field_errors={"new_plan_id": ["Workspace limit exceeded"]}
            )

        # Check topic limit
        if new_plan.max_topics != -1 and current_usage["topics"] > new_plan.max_topics:
            raise WrextValidationException(
                message=f"Cannot downgrade: You have {current_usage['topics']} topics, new plan allows {new_plan.max_topics}",
                field_errors={"new_plan_id": ["Topic limit exceeded"]}
            )

        # Check knowledge items limit
        if new_plan.max_knowledge_items != -1 and current_usage["knowledge_items"] > new_plan.max_knowledge_items:
            raise WrextValidationException(
                message=f"Cannot downgrade: You have {current_usage['knowledge_items']} knowledge items, new plan allows {new_plan.max_knowledge_items}",
                field_errors={"new_plan_id": ["Knowledge items limit exceeded"]}
            )
