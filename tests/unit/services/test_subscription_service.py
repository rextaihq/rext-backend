"""
Unit tests for SubscriptionService.

Tests cover:
- upgrade: Plan upgrades with validation
- downgrade: Plan downgrades with usage validation
- cancel: Subscription cancellation (immediate and deferred)
- calculate_usage: Usage calculation across resources
- check_trial_status: Trial status and expiration
- validate_plan_limits: Resource limit validation
- get_subscription_by_user: Active subscription retrieval
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from src.api.middleware.exceptions import (
    DuplicateResourceException,
    ResourceNotFoundException,
    RextValidationException,
)
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import (
    BillingPeriod,
    SubscriptionStatus,
    UserSubscription,
)
from src.api.models.subscription_models.trial_conversions import TrialConversion
from src.config.plan_rules import TRIAL_DURATION_DAYS
from src.services.subscription_service import SubscriptionService


async def _subscribe(db, user_id, plan):
    """The subscription the tests start from, as the removed subscribe() made it.

    A paid plan starts in the trial (TRIAL_DURATION_DAYS), a free one active. (Subscriptions are
    created by Lemon Squeezy's webhooks and the sign-up trial, not by the service.)
    """
    now = datetime.now(timezone.utc)
    paid = (plan.price_monthly or 0) > 0 or (plan.price_yearly or 0) > 0
    subscription = UserSubscription(
        user_id=user_id,
        plan_id=plan.id,
        status=SubscriptionStatus.TRIAL if paid else SubscriptionStatus.ACTIVE,
        billing_period=BillingPeriod.MONTHLY,
        start_date=now,
        trial_end_date=now + timedelta(days=TRIAL_DURATION_DAYS) if paid else None,
        usage_reset_date=now + timedelta(days=30),
    )
    db.add(subscription)
    await db.flush()
    await db.refresh(subscription)
    return subscription


@pytest.mark.unit
class TestSubscriptionServiceUpgrade:
    """Test upgrade method"""

    async def test_upgrade_to_higher_tier(self, db_session, setup_factories):
        """Should upgrade to higher tier plan"""
        # Arrange
        user = await setup_factories["user"].create()

        # Create plans
        basic_plan = SubscriptionPlan(
            id=uuid4(),
            name="Basic",
            display_name="Basic",
            price_monthly=9.99,
            max_workspaces=1,
            is_active=True,
        )
        pro_plan = SubscriptionPlan(
            id=uuid4(),
            name="Pro",
            display_name="Pro",
            price_monthly=29.99,
            max_workspaces=10,
            is_active=True,
        )
        db_session.add(basic_plan)
        db_session.add(pro_plan)
        await db_session.flush()

        service = SubscriptionService(db_session)

        # Subscribe to basic plan
        await _subscribe(db_session, user.id, basic_plan)

        # Act
        upgraded_subscription = await service.upgrade(user.id, pro_plan.id)

        # Assert
        assert upgraded_subscription.plan_id == pro_plan.id
        assert upgraded_subscription.user_id == user.id

    async def test_upgrade_from_trial_tracks_conversion(self, db_session, setup_factories):
        """Should transition trial subscription to ACTIVE, clear trial_end_date, and record TrialConversion"""
        # Arrange
        user = await setup_factories["user"].create()

        trial_plan = SubscriptionPlan(
            id=uuid4(),
            name="Trial",
            display_name="Trial",
            price_monthly=0,
            price_yearly=0,
            max_workspaces=1,
            is_active=True,
        )
        pro_plan = SubscriptionPlan(
            id=uuid4(),
            name="Pro",
            display_name="Pro",
            price_monthly=29.99,
            price_yearly=299.99,
            max_workspaces=10,
            is_active=True,
        )
        db_session.add(trial_plan)
        db_session.add(pro_plan)
        await db_session.flush()

        # Create active trial subscription
        trial_sub = UserSubscription(
            user_id=user.id,
            plan_id=trial_plan.id,
            status=SubscriptionStatus.TRIAL,
            billing_period=BillingPeriod.MONTHLY,
            start_date=datetime.now(timezone.utc),
            trial_end_date=datetime.now(timezone.utc) + timedelta(days=14),
        )
        db_session.add(trial_sub)
        await db_session.flush()

        service = SubscriptionService(db_session)

        # Act
        upgraded = await service.upgrade(user.id, pro_plan.id)

        # Assert
        assert upgraded.status == SubscriptionStatus.ACTIVE
        assert upgraded.plan_id == pro_plan.id
        assert upgraded.trial_end_date is None

        conversions = (
            (
                await db_session.execute(
                    select(TrialConversion).where(TrialConversion.subscription_id == trial_sub.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(conversions) == 1
        assert conversions[0].conversion_plan_id == pro_plan.id
        assert conversions[0].user_id == user.id

    async def test_upgrade_change_billing_period(self, db_session, setup_factories):
        """Should change billing period on same plan"""
        # Arrange
        user = await setup_factories["user"].create()

        plan = SubscriptionPlan(
            id=uuid4(),
            name="Pro",
            display_name="Pro",
            price_monthly=29.99,
            price_yearly=299.99,
            max_workspaces=10,
            is_active=True,
        )
        db_session.add(plan)
        await db_session.flush()

        service = SubscriptionService(db_session)

        # Subscribe monthly
        await _subscribe(db_session, user.id, plan)

        # Act - change to yearly
        updated_subscription = await service.upgrade(
            user.id, plan.id, billing_period=BillingPeriod.YEARLY
        )

        # Assert
        assert updated_subscription.plan_id == plan.id
        assert updated_subscription.billing_period == BillingPeriod.YEARLY

    async def test_upgrade_same_plan_same_billing_period(self, db_session, setup_factories):
        """Should raise RextValidationException when upgrading to same plan with same billing period"""
        # Arrange
        user = await setup_factories["user"].create()

        plan = SubscriptionPlan(
            id=uuid4(),
            name="Pro",
            display_name="Pro",
            price_monthly=29.99,
            max_workspaces=10,
            is_active=True,
        )
        db_session.add(plan)
        await db_session.flush()

        service = SubscriptionService(db_session)
        await _subscribe(db_session, user.id, plan)

        # Act & Assert
        with pytest.raises(RextValidationException) as exc_info:
            await service.upgrade(user.id, plan.id)

        assert "already subscribed" in exc_info.value.message.lower()

    async def test_upgrade_no_active_subscription(self, db_session, setup_factories):
        """Should raise ResourceNotFoundException when no active subscription"""
        # Arrange
        user = await setup_factories["user"].create()

        plan = SubscriptionPlan(
            id=uuid4(),
            name="Pro",
            display_name="Pro",
            price_monthly=29.99,
            max_workspaces=10,
            is_active=True,
        )
        db_session.add(plan)
        await db_session.flush()

        service = SubscriptionService(db_session)

        # Act & Assert
        with pytest.raises(ResourceNotFoundException) as exc_info:
            await service.upgrade(user.id, plan.id)

        assert "no active subscription" in exc_info.value.message.lower()


@pytest.mark.unit
class TestSubscriptionServiceDowngrade:
    """Test downgrade method"""

    async def test_downgrade_with_usage_validation(self, db_session, setup_factories):
        """Should validate usage doesn't exceed new plan limits on downgrade"""
        # Arrange
        user = await setup_factories["user"].create()
        await setup_factories["workspace"].create(user_id=user.id)

        # Create plans
        pro_plan = SubscriptionPlan(
            id=uuid4(),
            name="Pro",
            display_name="Pro",
            price_monthly=29.99,
            max_workspaces=10,
            is_active=True,
        )
        basic_plan = SubscriptionPlan(
            id=uuid4(),
            name="Basic",
            display_name="Basic",
            price_monthly=9.99,
            max_workspaces=1,  # User already has 1 workspace
            is_active=True,
        )
        db_session.add(pro_plan)
        db_session.add(basic_plan)
        await db_session.flush()

        service = SubscriptionService(db_session)
        await _subscribe(db_session, user.id, pro_plan)

        # Act - downgrade should succeed (usage fits)
        downgraded = await service.downgrade(user.id, basic_plan.id)

        # Assert
        assert downgraded.plan_id == basic_plan.id

    async def test_downgrade_exceeds_workspace_limit(self, db_session, setup_factories):
        """Should raise RextValidationException when workspace count exceeds new plan limit"""
        # Arrange
        user = await setup_factories["user"].create()

        # Create 2 workspaces
        await setup_factories["workspace"].create(user_id=user.id)
        await setup_factories["workspace"].create(user_id=user.id)

        # Create plans
        pro_plan = SubscriptionPlan(
            id=uuid4(),
            name="Pro",
            display_name="Pro",
            price_monthly=29.99,
            max_workspaces=10,
            is_active=True,
        )
        basic_plan = SubscriptionPlan(
            id=uuid4(),
            name="Basic",
            display_name="Basic",
            price_monthly=9.99,
            max_workspaces=1,  # User has 2 workspaces!
            is_active=True,
        )
        db_session.add(pro_plan)
        db_session.add(basic_plan)
        await db_session.flush()

        service = SubscriptionService(db_session)
        await _subscribe(db_session, user.id, pro_plan)

        # Act & Assert
        with pytest.raises(RextValidationException) as exc_info:
            await service.downgrade(user.id, basic_plan.id)

        assert "cannot downgrade" in exc_info.value.message.lower()
        assert "workspace" in exc_info.value.message.lower()


@pytest.mark.unit
class TestSubscriptionServiceCancel:
    """Test cancel method"""

    async def test_cancel_immediately(self, db_session, setup_factories):
        """Should cancel subscription immediately"""
        # Arrange
        user = await setup_factories["user"].create()

        plan = SubscriptionPlan(
            id=uuid4(),
            name="Pro",
            display_name="Pro",
            price_monthly=29.99,
            max_workspaces=10,
            is_active=True,
        )
        db_session.add(plan)
        await db_session.flush()

        service = SubscriptionService(db_session)
        await _subscribe(db_session, user.id, plan)

        # Act
        cancelled = await service.cancel(
            user.id, reason="Test cancellation", cancel_immediately=True
        )

        # Assert
        assert cancelled.status == SubscriptionStatus.CANCELLED
        assert cancelled.cancelled_at is not None
        assert cancelled.end_date is not None

    async def test_cancel_at_end_of_period(self, db_session, setup_factories):
        """Should schedule cancellation for end of billing period"""
        # Arrange
        user = await setup_factories["user"].create()

        plan = SubscriptionPlan(
            id=uuid4(),
            name="Pro",
            display_name="Pro",
            price_monthly=29.99,
            max_workspaces=10,
            is_active=True,
        )
        db_session.add(plan)
        await db_session.flush()

        service = SubscriptionService(db_session)
        subscription = await _subscribe(db_session, user.id, plan)

        # Act
        cancelled = await service.cancel(user.id, cancel_immediately=False)

        # Assert
        assert cancelled.cancelled_at is not None
        assert cancelled.end_date == subscription.usage_reset_date  # Monthly billing
        # Status flips to CANCELLED immediately (so the UI reflects it and a
        # repeat cancel finds no active subscription); credits/usage limits
        # keep working until end_date via subscription_grants_access().
        assert cancelled.status == SubscriptionStatus.CANCELLED
        assert cancelled.cancel_at_period_end is True

    async def test_cancel_no_subscription(self, db_session, setup_factories):
        """Should raise ResourceNotFoundException when no active subscription"""
        # Arrange
        user = await setup_factories["user"].create()
        service = SubscriptionService(db_session)

        # Act & Assert
        with pytest.raises(ResourceNotFoundException):
            await service.cancel(user.id)


@pytest.mark.unit
class TestSubscriptionServiceCalculateUsage:
    """Test calculate_usage method"""

    async def test_calculate_usage_empty(self, db_session, setup_factories):
        """Should return zero usage when no resources"""
        # Arrange
        user = await setup_factories["user"].create()
        service = SubscriptionService(db_session)

        # Act
        usage = await service.calculate_usage(user.id)

        # Assert
        assert usage["workspaces"] == 0
        assert usage["members"] == 0

    async def test_calculate_usage_with_resources(self, db_session, setup_factories):
        """Should count all resources correctly"""
        # Arrange
        user = await setup_factories["user"].create()
        await setup_factories["workspace"].create(user_id=user.id)

        service = SubscriptionService(db_session)

        # Act
        usage = await service.calculate_usage(user.id)

        # Assert
        assert usage["workspaces"] == 1


@pytest.mark.unit
class TestSubscriptionServiceCheckTrialStatus:
    """Test check_trial_status method"""

    async def test_check_trial_status_active_trial(self, db_session, setup_factories):
        """Should return trial status for active trial"""
        # Arrange
        user = await setup_factories["user"].create()

        # Create paid plan
        plan = SubscriptionPlan(
            id=uuid4(),
            name="Pro",
            display_name="Pro",
            price_monthly=29.99,
            max_workspaces=10,
            is_active=True,
        )
        db_session.add(plan)
        await db_session.flush()

        service = SubscriptionService(db_session)
        await _subscribe(db_session, user.id, plan)

        # Act
        trial_status = await service.check_trial_status(user.id)

        # Assert
        assert trial_status["is_trial"] is True
        assert trial_status["trial_end_date"] is not None
        assert trial_status["days_remaining"] is not None
        assert trial_status["days_remaining"] >= 0
        assert trial_status["trial_expired"] is False

    async def test_check_trial_status_no_subscription(self, db_session, setup_factories):
        """Should return no trial when no subscription"""
        # Arrange
        user = await setup_factories["user"].create()
        service = SubscriptionService(db_session)

        # Act
        trial_status = await service.check_trial_status(user.id)

        # Assert
        assert trial_status["is_trial"] is False
        assert trial_status["trial_end_date"] is None
        assert trial_status["days_remaining"] is None
        assert trial_status["trial_expired"] is False

    async def test_check_trial_status_free_plan(self, db_session, setup_factories):
        """Should return no trial for free plan"""
        # Arrange
        user = await setup_factories["user"].create()

        # Create free plan
        free_plan = SubscriptionPlan(
            id=uuid4(),
            name="Free",
            display_name="Free",
            price_monthly=0,
            max_workspaces=1,
            is_active=True,
        )
        db_session.add(free_plan)
        await db_session.flush()

        service = SubscriptionService(db_session)
        await _subscribe(db_session, user.id, free_plan)

        # Act
        trial_status = await service.check_trial_status(user.id)

        # Assert
        assert trial_status["is_trial"] is False


@pytest.mark.unit
class TestSubscriptionServiceValidatePlanLimits:
    """Test validate_plan_limits method"""

    async def test_validate_plan_limits_within_limits(self, db_session, setup_factories):
        """Should return True when within plan limits"""
        # Arrange
        user = await setup_factories["user"].create()

        plan = SubscriptionPlan(
            id=uuid4(),
            name="Basic",
            display_name="Basic",
            price_monthly=9.99,
            max_workspaces=5,
            is_active=True,
        )
        db_session.add(plan)
        await db_session.flush()

        service = SubscriptionService(db_session)
        await _subscribe(db_session, user.id, plan)

        # Act
        result = await service.validate_plan_limits(user.id, "workspace", increment=1)

        # Assert
        assert result is True

    async def test_validate_plan_limits_exceeds_workspace_limit(self, db_session, setup_factories):
        """Should raise RextValidationException when exceeding workspace limit"""
        # Arrange
        user = await setup_factories["user"].create()

        # Create 2 workspaces
        await setup_factories["workspace"].create(user_id=user.id)
        await setup_factories["workspace"].create(user_id=user.id)

        plan = SubscriptionPlan(
            id=uuid4(),
            name="Basic",
            display_name="Basic",
            price_monthly=9.99,
            max_workspaces=2,  # Already at limit
            is_active=True,
        )
        db_session.add(plan)
        await db_session.flush()

        service = SubscriptionService(db_session)
        await _subscribe(db_session, user.id, plan)

        # Act & Assert
        with pytest.raises(RextValidationException) as exc_info:
            await service.validate_plan_limits(user.id, "workspace", increment=1)

        assert "plan limit exceeded" in exc_info.value.message.lower()

    async def test_validate_plan_limits_unlimited(self, db_session, setup_factories):
        """Should always return True for unlimited plans (-1)"""
        # Arrange
        user = await setup_factories["user"].create()

        # Create 10 workspaces
        for _ in range(10):
            await setup_factories["workspace"].create(user_id=user.id)

        plan = SubscriptionPlan(
            id=uuid4(),
            name="Enterprise",
            display_name="Enterprise",
            price_monthly=99.99,
            max_workspaces=-1,  # Unlimited
            is_active=True,
        )
        db_session.add(plan)
        await db_session.flush()

        service = SubscriptionService(db_session)
        await _subscribe(db_session, user.id, plan)

        # Act
        result = await service.validate_plan_limits(user.id, "workspace", increment=100)

        # Assert
        assert result is True

    async def test_validate_plan_limits_invalid_resource_type(self, db_session, setup_factories):
        """Should raise RextValidationException for invalid resource type"""
        # Arrange
        user = await setup_factories["user"].create()

        plan = SubscriptionPlan(
            id=uuid4(),
            name="Basic",
            display_name="Basic",
            price_monthly=9.99,
            max_workspaces=5,
            is_active=True,
        )
        db_session.add(plan)
        await db_session.flush()

        service = SubscriptionService(db_session)
        await _subscribe(db_session, user.id, plan)

        # Act & Assert
        with pytest.raises(RextValidationException) as exc_info:
            await service.validate_plan_limits(user.id, "invalid_resource", increment=1)

        assert "invalid resource type" in exc_info.value.message.lower()


@pytest.mark.unit
class TestSubscriptionServiceGetSubscriptionByUser:
    """Test get_subscription_by_user method"""

    async def test_get_subscription_by_user_found(self, db_session, setup_factories):
        """Should return active subscription"""
        # Arrange
        user = await setup_factories["user"].create()

        plan = SubscriptionPlan(
            id=uuid4(),
            name="Pro",
            display_name="Pro",
            price_monthly=29.99,
            max_workspaces=10,
            is_active=True,
        )
        db_session.add(plan)
        await db_session.flush()

        service = SubscriptionService(db_session)
        created_subscription = await _subscribe(db_session, user.id, plan)

        # Act
        subscription = await service.get_subscription_by_user(user.id)

        # Assert
        assert subscription is not None
        assert subscription.id == created_subscription.id
        assert subscription.user_id == user.id

    async def test_get_subscription_by_user_not_found(self, db_session, setup_factories):
        """Should return None when no active subscription"""
        # Arrange
        user = await setup_factories["user"].create()
        service = SubscriptionService(db_session)

        # Act
        subscription = await service.get_subscription_by_user(user.id)

        # Assert
        assert subscription is None
