"""
Usage Tracking Service

This service tracks and manages usage metrics for users based on their subscription plan.
It calculates current usage against plan limits and provides real-time usage data.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.models.subscription_models.subscriptions import (
    FAILED_PAYMENT_STATUSES,
    SubscriptionStatus,
    UserSubscription,
    subscription_grants_access,
)
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.services.credit_grants import (
    bonus_summary,
    forfeit_grants,
    grant_balance,
    live_grants,
    period_admin_adjustment,
    split_cost,
)
from src.utils.datetime_utils import next_billing_anchor
from src.utils.logger import logger

# Default limits for free tier when no subscription plan is found
FREE_MAX_WORKSPACES = 1
FREE_MAX_API_CALLS = 100


def replenish_if_due(subscription: UserSubscription) -> bool:
    """Start the new month's credits when the reset date has passed (non-trial plans).

    Not while a renewal is unpaid: the new month's credits come with the payment
    (subscription_payment_success), not with Lemon Squeezy's retries. The caller
    holds the subscription's row lock. Returns whether the credits were reset.
    """
    if not (
        subscription.plan
        and not subscription.plan.is_trial_plan
        and subscription.credits_reset_date
        and subscription.status not in FAILED_PAYMENT_STATUSES
    ):
        return False
    reset_dt = subscription.credits_reset_date
    if reset_dt.tzinfo is None:
        reset_dt = reset_dt.replace(tzinfo=timezone.utc)
    if reset_dt >= datetime.now(timezone.utc):
        return False
    subscription.current_credits = subscription.plan.credits_per_month or 0
    subscription.credits_reset_date = next_billing_anchor(subscription.credits_reset_date)
    return True


class UsageTrackingService:
    """Service for tracking and managing user usage metrics"""

    def __init__(self, db: AsyncSession):
        """Initialize usage tracking service"""
        self.db = db

    async def get_usage_metrics(self, user_id: UUID) -> Dict[str, Any]:
        """
        Get current usage metrics for a user.

        Returns:
            Dictionary with usage metrics for each resource type:
            {
                "workspaces": {"used": 3, "limit": 10, ...},
                "api_calls": {"used": 450, "limit": 10000, ...},
                "meta": {"plan_name": "Pro", ...}
            }
        """
        # Get user's active (or cancelled-but-in-grace-period) subscription with plan eagerly loaded
        subscription_query = (
            select(UserSubscription)
            .options(selectinload(UserSubscription.plan))
            .where(and_(UserSubscription.user_id == user_id, subscription_grants_access()))
            .order_by(UserSubscription.start_date.desc())
            .limit(1)
        )
        result = await self.db.execute(subscription_query)
        subscription = result.scalar_one_or_none()

        # If no subscription, return free tier usage
        if not subscription or not subscription.plan:
            return await self._get_free_tier_usage(user_id)

        plan = subscription.plan

        # Count workspaces owned by user (excluding soft-deleted ones)
        workspace_count_query = select(func.count(WorkspaceModel.id)).where(
            WorkspaceModel.user_id == user_id, WorkspaceModel.deleted_at.is_(None)
        )
        workspace_count_result = await self.db.execute(workspace_count_query)
        workspace_count = workspace_count_result.scalar() or 0

        # Count total members across all user's active workspaces
        member_count_query = (
            select(func.count(WorkspaceMembers.id))
            .join(WorkspaceModel)
            .where(WorkspaceModel.user_id == user_id, WorkspaceModel.deleted_at.is_(None))
        )
        member_count_result = await self.db.execute(member_count_query)
        member_count = member_count_result.scalar() or 0

        # Get API calls this month
        api_calls = subscription.current_api_calls or 0

        # Helper to build metric dict
        def build_metric(used, limit):
            unlimited = limit == -1 or limit is None
            return {
                "used": used,
                "limit": limit if not unlimited else None,
                "percentage": self._calc_percentage(used, limit),
                "unlimited": unlimited,
            }

        usage_data = {
            "workspaces": build_metric(workspace_count, plan.max_workspaces),
            "members": build_metric(member_count, plan.max_members_per_workspace),
            "api_calls": {
                **build_metric(api_calls, plan.max_api_calls_per_month),
                "reset_date": subscription.usage_reset_date.isoformat()
                if subscription.usage_reset_date
                else None,
            },
            "meta": {
                "subscription_id": str(subscription.id),
                "plan_name": plan.name,
                "billing_period": subscription.billing_period.value,
                # An unexpired grant, such as the launch offer's bonus: "Launch
                # bonus: +1,000 credits until ...". None when there is none.
                "credit_bonus": bonus_summary(await live_grants(self.db, subscription.id)),
            },
        }

        return usage_data

    async def check_limit(self, user_id: UUID, limit_type: str) -> Tuple[bool, int, Optional[int]]:
        """
        Check if user has exceeded a specific limit.

        Args:
            user_id: User UUID
            limit_type: Type of limit to check
                        Valid values: "workspaces", "members", "api_calls"

        Returns:
            Tuple of (within_limit, used, limit)
            - within_limit: True if under limit, False if at or over limit
            - used: Current usage count
            - limit: Limit value (None if unlimited)
        """
        usage = await self.get_usage_metrics(user_id)

        if limit_type not in usage:
            logger.warning(f"Unknown limit type: {limit_type}")
            return True, 0, None

        metric = usage.get(limit_type, {})
        used = metric.get("used", 0) or 0
        limit = metric.get("limit")

        # No limit set (None, or -1 for unlimited)
        if limit is None or limit <= 0:
            return True, used, None

        within_limit = used < limit
        return within_limit, used, limit

    async def get_credit_balance(self, user_id: UUID) -> int:
        """Return the credits a user can spend: the monthly credits of their active (or
        cancelled-but-in-grace-period) subscription plus its unexpired grants."""
        result = await self.db.execute(
            select(UserSubscription)
            .where(and_(UserSubscription.user_id == user_id, subscription_grants_access()))
            .order_by(UserSubscription.start_date.desc())
            .limit(1)
        )
        subscription = result.scalar_one_or_none()
        if not subscription:
            return 0
        return (subscription.current_credits or 0) + await grant_balance(self.db, subscription.id)

    async def consume_credits(self, user_id: UUID, cost: int) -> bool:
        """
        Deduct credits from user's subscription.

        Returns True on success, False if insufficient credits.
        """
        result = await self.db.execute(
            select(UserSubscription)
            .options(selectinload(UserSubscription.plan))
            .where(and_(UserSubscription.user_id == user_id, subscription_grants_access()))
            .order_by(UserSubscription.start_date.desc())
            .limit(1)
            .with_for_update()
        )
        subscription = result.scalar_one_or_none()
        if not subscription:
            return False

        replenish_if_due(subscription)

        # Grants with an expiry (an offer's bonus) are spent first, soonest expiry
        # first, then the monthly credits, then grants without an expiry (credits
        # an admin added), oldest first. The row lock above serialises every
        # change to this subscription's; the grants are locked too, since what
        # an admin added is spendable from any of the user's subscription rows.
        grants = await live_grants(self.db, subscription.id, lock=True)
        expiring = [g for g in grants if g.expires_at is not None]
        lasting = [g for g in grants if g.expires_at is None]
        split = split_cost(
            cost,
            [g.remaining for g in expiring],
            subscription.current_credits or 0,
            [g.remaining for g in lasting],
        )
        if split is None:
            return False

        from_expiring, from_monthly, from_lasting = split
        for grant, taken in zip(expiring, from_expiring):
            grant.remaining -= taken
        subscription.current_credits -= from_monthly
        for grant, taken in zip(lasting, from_lasting):
            grant.remaining -= taken
        await self.db.flush()
        return True

    async def replenish_credits(self, user_id: UUID) -> None:
        """Reset credits to plan amount (monthly renewal)."""
        result = await self.db.execute(
            select(UserSubscription)
            .options(selectinload(UserSubscription.plan))
            .where(
                and_(
                    UserSubscription.user_id == user_id,
                    UserSubscription.status.in_(
                        [SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL]
                    ),
                )
            )
            .order_by(UserSubscription.start_date.desc())
            .limit(1)
        )
        subscription = result.scalar_one_or_none()
        if subscription and subscription.plan and not subscription.plan.is_trial_plan:
            subscription.current_credits = subscription.plan.credits_per_month or 0
            base_date = (
                subscription.credits_reset_date
                or subscription.renews_at
                or datetime.now(timezone.utc)
            )
            subscription.credits_reset_date = next_billing_anchor(base_date)
            await self.db.flush()

    async def allocate_credits(self, user_id: UUID, amount: int) -> None:
        """Set credit balance to a specific amount (used at trial/plan activation)."""
        result = await self.db.execute(
            select(UserSubscription)
            .where(UserSubscription.user_id == user_id)
            .order_by(UserSubscription.start_date.desc())
            .limit(1)
        )
        subscription = result.scalar_one_or_none()
        if subscription:
            subscription.current_credits = amount
            await self.db.flush()

    async def reconcile_partial_refund_credits(
        self,
        user_id: UUID,
        lemonsqueezy_order_id: str,
        refunded_total: int,
        original_amount: int,
        latest: Optional[bool] = None,
    ) -> Optional[Dict[str, Any]]:
        """Shrink the unused part of a partially refunded period's credits.

        A partial refund leaves the subscription, the license and all access
        intact; what it takes back is entitlement. The period's grant shrinks
        by the share of the money returned, and the user keeps whatever is
        left of it after what they have already spent::

            retained_grant = granted * (paid - refunded) // paid
            balance        = max(0, retained_grant - already_used)

        Credits already spent are never reversed and no generated content is
        touched: a user who has already spent more than the retained grant
        simply lands at zero for the rest of the period rather than going
        negative, which `consume_credits` and the pipeline's pre-flight gate
        both rely on.

        Only the account's newest order counts. Credits reset to the full plan
        amount at every renewal and never roll over, so a refund against an
        older order would claw back credits bought in a different period.

        Safe to call more than once for the same refund. `already_used` is
        normally derived from the balance, which stops being true the moment
        we lower it, so the reduction is recorded against the order in
        `subscription_metadata` and backed out of that reading. That makes the
        whole thing a recompute rather than a decrement: a replayed webhook
        lands on the same number, and a second partial refund composes with
        the first instead of compounding with it.

        Args:
            user_id: The refunded user.
            lemonsqueezy_order_id: Order the refund was issued against.
            refunded_total: Cumulative cents refunded on that order, not the
                amount of this one refund.
            original_amount: Cents the order was charged in full.
            latest: Whether the refunded payment is the current period's. None asks
                the orders table (the account's newest order); a renewal's invoice,
                which has no order, is judged by its caller.

        Returns:
            A summary of the adjustment for the caller to log and audit, or
            None when nothing applied.
        """
        # Full refunds revoke access instead, which drops the balance to zero
        # through `subscription_grants_access()` without touching any counter.
        if refunded_total <= 0 or original_amount <= 0 or refunded_total >= original_amount:
            return None

        from src.services.order_service import OrderService

        if latest is None:
            latest = await OrderService(self.db).is_latest_order(user_id, lemonsqueezy_order_id)
        if not latest:
            return None

        result = await self.db.execute(
            select(UserSubscription)
            .options(selectinload(UserSubscription.plan))
            .where(and_(UserSubscription.user_id == user_id, subscription_grants_access()))
            .order_by(UserSubscription.start_date.desc())
            .limit(1)
            # The same row lock as consume_credits: grants change under it only.
            .with_for_update()
        )
        subscription = result.scalar_one_or_none()
        if not subscription or not subscription.plan:
            return None

        plan = subscription.plan
        granted = plan.credits_per_month or 0
        # Trial plans were never paid for, and a null `credits_per_month` is a
        # custom/enterprise plan whose entitlement we cannot compute.
        if plan.is_trial_plan or granted <= 0:
            return None

        # The balance is stale and due to be replenished for a new period, so
        # the refunded period's entitlement is already gone.
        if subscription.credits_reset_date and subscription.credits_reset_date < datetime.now(
            timezone.utc
        ):
            return None

        meta = {**(subscription.subscription_metadata or {})}
        previous = meta.get("refund_credit_reduction") or {}
        already_cut = (
            int(previous.get("credits") or 0)
            if str(previous.get("order_id")) == str(lemonsqueezy_order_id)
            else 0
        )

        # Any refund forfeits the period's unspent promotional bonus.
        bonus_forfeited = await forfeit_grants(
            self.db, subscription.id, order_id=lemonsqueezy_order_id
        )

        balance = subscription.current_credits or 0
        # An admin's deduction or reset this period moved the balance without any
        # credit being used; it stays on top of what the refund leaves (a
        # deduction stays deducted, a reset's credits stay given).
        adjustment = period_admin_adjustment(subscription)
        used = max(0, granted - balance - already_cut + adjustment)
        retained_grant = granted * (original_amount - refunded_total) // original_amount
        target = max(0, retained_grant - used + adjustment)

        # Never hand credits back: a refund can only reduce an entitlement.
        if target >= balance:
            if not bonus_forfeited:
                return None
            target = balance
        else:
            subscription.current_credits = target
            # Reassigned rather than mutated: SQLAlchemy does not track in-place
            # changes to a plain JSONB column.
            meta["refund_credit_reduction"] = {
                "order_id": str(lemonsqueezy_order_id),
                "credits": granted - used + adjustment - target,
            }
            subscription.subscription_metadata = meta
        subscription.updated_at = datetime.now(timezone.utc)
        await self.db.flush()

        return {
            "subscription_id": str(subscription.id),
            "plan_name": plan.name,
            "granted": granted,
            "used": used,
            "retained_grant": retained_grant,
            "credits_before": balance,
            "credits_after": target,
            "refunded_total": refunded_total,
            "original_amount": original_amount,
            "bonus_forfeited": bonus_forfeited,
        }

    async def increment_api_calls(self, user_id: UUID) -> None:
        """
        Increment API call counter for user's subscription.

        Args:
            user_id: User UUID
        """
        subscription_query = (
            select(UserSubscription)
            .where(and_(UserSubscription.user_id == user_id, subscription_grants_access()))
            .order_by(UserSubscription.start_date.desc())
            .limit(1)
        )
        result = await self.db.execute(subscription_query)
        subscription = result.scalar_one_or_none()

        if subscription:
            subscription.current_api_calls = (subscription.current_api_calls or 0) + 1
            await self.db.flush()
            logger.debug(
                f"Incremented API calls for user {user_id}: {subscription.current_api_calls}"
            )

    async def reset_monthly_usage(self, user_id: UUID) -> None:
        """
        Reset monthly usage counters (called by scheduled job).

        Args:
            user_id: User UUID
        """
        subscription_query = (
            select(UserSubscription)
            .where(UserSubscription.user_id == user_id)
            .order_by(UserSubscription.start_date.desc())
            .limit(1)
        )
        result = await self.db.execute(subscription_query)
        subscription = result.scalar_one_or_none()

        if subscription:
            subscription.current_api_calls = 0
            base_date = (
                subscription.usage_reset_date
                or subscription.renews_at
                or datetime.now(timezone.utc)
            )
            subscription.usage_reset_date = next_billing_anchor(base_date)
            await self.db.flush()
            logger.info(f"Reset monthly usage for user {user_id}")

    def _calc_percentage(self, used: int, limit: Optional[int]) -> float:
        """Calculate usage percentage"""
        if limit is None or limit <= 0:
            return 0.0
        return min(round((used / limit) * 100, 1), 100.0)

    async def _get_free_tier_usage(self, user_id: UUID) -> Dict[str, Any]:
        """
        Get usage for free tier (no active subscription).
        Returns actual counts with None/0 limits to indicate free tier restrictions.
        """
        # Count workspaces (excluding soft-deleted ones)
        workspace_count_query = select(func.count(WorkspaceModel.id)).where(
            WorkspaceModel.user_id == user_id, WorkspaceModel.deleted_at.is_(None)
        )
        workspace_count_result = await self.db.execute(workspace_count_query)
        workspace_count = workspace_count_result.scalar() or 0

        # Count members
        member_count_query = (
            select(func.count(WorkspaceMembers.id))
            .join(WorkspaceModel)
            .where(WorkspaceModel.user_id == user_id, WorkspaceModel.deleted_at.is_(None))
        )
        member_count_result = await self.db.execute(member_count_query)
        member_count = member_count_result.scalar() or 0

        # Helper to build metric dict
        def build_metric(used, limit):
            unlimited = limit == -1 or limit is None
            return {
                "used": used,
                "limit": limit if not unlimited else None,
                "percentage": self._calc_percentage(used, limit),
                "unlimited": unlimited,
            }

        usage_data = {
            "workspaces": build_metric(workspace_count, FREE_MAX_WORKSPACES),
            "members": build_metric(member_count, 3),  # Default free limit if not in plan
            "api_calls": {**build_metric(0, FREE_MAX_API_CALLS), "reset_date": None},
            "meta": {"subscription_id": None, "plan_name": "Free", "billing_period": None},
        }

        return usage_data
