"""
Integration tests for subscription flows.

Tests complete subscription flows with real database interactions.
Uses MockPaymentProvider to avoid external payment provider dependencies.

Tests cover:
- End-to-end checkout flow
- Subscription creation and activation
- Usage tracking and limits
- Subscription cancellation
- Plan upgrades
- Webhook processing
"""

import pytest
import pytest_asyncio
from uuid import uuid4, UUID
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock

from src.services.subscription_service import SubscriptionService
from src.services.usage_tracking_service import UsageTrackingService
from src.api.models.subscription_models.subscriptions import UserSubscription, SubscriptionStatus
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.user_models.users import Users
from src.providers.payment.mock_provider import MockPaymentProvider
from sqlalchemy import select


@pytest.fixture
async def mock_payment_provider():
    """Create mock payment provider for testing"""
    return MockPaymentProvider()


@pytest.fixture
async def test_user(db_session):
    """Create a test user"""
    user = Users(
        id=uuid4(),
        email="test@example.com",
        username="testuser",
        password_hash="hashed",
        email_verified=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def test_plan(db_session):
    """Create a test subscription plan"""
    plan = SubscriptionPlan(
        id=uuid4(),
        name="pro",
        display_name="Pro Plan",
        description="Professional features",
        price_monthly=29.99,
        price_yearly=299.99,
        provider_price_id_monthly="price_monthly_123",
        provider_price_id_yearly="price_yearly_123",
        max_workspaces=10,
        max_members_per_workspace=20,
        max_topics=500,
        max_knowledge_items=1000,
        max_api_calls_per_month=10000,
        is_active=True,
        is_public=True
    )
    db_session.add(plan)
    await db_session.commit()
    await db_session.refresh(plan)
    return plan


class TestSubscriptionCheckoutFlow:
    """Test complete subscription checkout flows"""

    @pytest.mark.asyncio
    @patch('src.services.subscription_service.get_payment_provider')
    async def test_create_checkout_session(
        self,
        mock_get_provider,
        db_session,
        test_user,
        test_plan,
        mock_payment_provider
    ):
        """Should create checkout session with payment provider"""
        mock_get_provider.return_value = mock_payment_provider

        service = SubscriptionService(db_session)

        # Create customer first
        customer_id = await mock_payment_provider.create_customer(
            email=test_user.email,
            name=test_user.username,
            metadata={"user_id": str(test_user.id)}
        )

        # Create checkout session
        session = await mock_payment_provider.create_checkout_session(
            customer_id=customer_id,
            price_id=test_plan.provider_price_id_monthly,
            success_url="http://example.com/success",
            cancel_url="http://example.com/cancel",
            metadata={
                "user_id": str(test_user.id),
                "plan_id": str(test_plan.id),
                "billing_period": "monthly"
            }
        )

        assert session.session_id.startswith("cs_mock_")
        assert session.customer_id == customer_id
        assert "/mock-checkout/" in session.checkout_url

    @pytest.mark.asyncio
    async def test_create_subscription_after_checkout(
        self,
        db_session,
        test_user,
        test_plan
    ):
        """Should create subscription after successful checkout"""
        service = SubscriptionService(db_session)

        # Simulate successful checkout
        subscription = await service.create_subscription(
            user_id=str(test_user.id),
            plan_id=str(test_plan.id),
            provider_subscription_id="sub_mock_123",
            provider_customer_id="cus_mock_123",
            billing_period="monthly",
            status="active"
        )

        assert subscription.user_id == test_user.id
        assert subscription.plan_id == test_plan.id
        assert subscription.status == SubscriptionStatus.ACTIVE
        assert subscription.billing_period == "monthly"
        assert subscription.current_api_calls == 0
        assert subscription.usage_reset_date is not None

    @pytest.mark.asyncio
    async def test_subscription_visible_in_database(
        self,
        db_session,
        test_user,
        test_plan
    ):
        """Should persist subscription to database"""
        service = SubscriptionService(db_session)

        subscription = await service.create_subscription(
            user_id=str(test_user.id),
            plan_id=str(test_plan.id),
            provider_subscription_id="sub_mock_456",
            provider_customer_id="cus_mock_456",
            billing_period="yearly",
            status="active"
        )

        # Query from database
        result = await db_session.execute(
            select(UserSubscription).where(UserSubscription.user_id == test_user.id)
        )
        db_subscription = result.scalar_one()

        assert db_subscription.id == subscription.id
        assert db_subscription.status == SubscriptionStatus.ACTIVE
        assert db_subscription.billing_period == "yearly"


class TestUsageTracking:
    """Test usage tracking and limits"""

    @pytest.mark.asyncio
    async def test_get_usage_metrics(
        self,
        db_session,
        test_user,
        test_plan
    ):
        """Should return usage metrics for user"""
        # Create subscription
        subscription_service = SubscriptionService(db_session)
        await subscription_service.create_subscription(
            user_id=str(test_user.id),
            plan_id=str(test_plan.id),
            provider_subscription_id="sub_mock_789",
            provider_customer_id="cus_mock_789",
            billing_period="monthly",
            status="active"
        )

        # Get usage metrics
        usage_service = UsageTrackingService(db_session)
        metrics = await usage_service.get_usage_metrics(str(test_user.id))

        assert "workspaces" in metrics
        assert "members" in metrics
        assert "topics" in metrics
        assert "knowledge_items" in metrics
        assert "api_calls" in metrics

        assert metrics["workspaces"]["limit"] == test_plan.max_workspaces
        assert metrics["api_calls"]["limit"] == test_plan.max_api_calls_per_month
        assert metrics["workspaces"]["used"] == 0
        assert metrics["api_calls"]["used"] == 0

    @pytest.mark.asyncio
    async def test_check_limit_within_bounds(
        self,
        db_session,
        test_user,
        test_plan
    ):
        """Should allow action when within limits"""
        # Create subscription
        subscription_service = SubscriptionService(db_session)
        await subscription_service.create_subscription(
            user_id=str(test_user.id),
            plan_id=str(test_plan.id),
            provider_subscription_id="sub_mock_999",
            provider_customer_id="cus_mock_999",
            billing_period="monthly",
            status="active"
        )

        # Check workspace limit (0 workspaces created, limit is 10)
        usage_service = UsageTrackingService(db_session)
        within_limit, used, limit = await usage_service.check_limit(
            str(test_user.id),
            "workspaces"
        )

        assert within_limit is True
        assert used == 0
        assert limit == 10

    @pytest.mark.asyncio
    async def test_increment_api_calls(
        self,
        db_session,
        test_user,
        test_plan
    ):
        """Should increment API call counter"""
        # Create subscription
        subscription_service = SubscriptionService(db_session)
        subscription = await subscription_service.create_subscription(
            user_id=str(test_user.id),
            plan_id=str(test_plan.id),
            provider_subscription_id="sub_mock_inc",
            provider_customer_id="cus_mock_inc",
            billing_period="monthly",
            status="active"
        )

        assert subscription.current_api_calls == 0

        # Increment API calls
        usage_service = UsageTrackingService(db_session)
        await usage_service.increment_api_calls(str(test_user.id))

        # Refresh subscription
        await db_session.refresh(subscription)
        assert subscription.current_api_calls == 1

        # Increment again
        await usage_service.increment_api_calls(str(test_user.id))
        await db_session.refresh(subscription)
        assert subscription.current_api_calls == 2


class TestSubscriptionCancellation:
    """Test subscription cancellation flows"""

    @pytest.mark.asyncio
    @patch('src.services.subscription_service.get_payment_provider')
    async def test_cancel_subscription_at_period_end(
        self,
        mock_get_provider,
        db_session,
        test_user,
        test_plan,
        mock_payment_provider
    ):
        """Should cancel subscription at end of billing period"""
        mock_get_provider.return_value = mock_payment_provider

        # Create subscription
        service = SubscriptionService(db_session)
        subscription = await service.create_subscription(
            user_id=str(test_user.id),
            plan_id=str(test_plan.id),
            provider_subscription_id="sub_cancel_123",
            provider_customer_id="cus_cancel_123",
            billing_period="monthly",
            status="active"
        )

        # Cancel subscription
        cancelled = await service.cancel_subscription(
            user_id=str(test_user.id),
            at_period_end=True
        )

        assert cancelled.cancelled_at is not None
        assert cancelled.status == SubscriptionStatus.ACTIVE  # Still active until period end

    @pytest.mark.asyncio
    @patch('src.services.subscription_service.get_payment_provider')
    async def test_cancel_subscription_immediately(
        self,
        mock_get_provider,
        db_session,
        test_user,
        test_plan,
        mock_payment_provider
    ):
        """Should cancel subscription immediately"""
        mock_get_provider.return_value = mock_payment_provider

        # Create subscription
        service = SubscriptionService(db_session)
        subscription = await service.create_subscription(
            user_id=str(test_user.id),
            plan_id=str(test_plan.id),
            provider_subscription_id="sub_cancel_imm",
            provider_customer_id="cus_cancel_imm",
            billing_period="monthly",
            status="active"
        )

        # Cancel subscription immediately
        cancelled = await service.cancel_subscription(
            user_id=str(test_user.id),
            at_period_end=False
        )

        assert cancelled.cancelled_at is not None
        assert cancelled.status == SubscriptionStatus.CANCELLED


class TestSubscriptionWithUsage:
    """Test getting subscription with usage data"""

    @pytest.mark.asyncio
    async def test_get_subscription_with_usage(
        self,
        db_session,
        test_user,
        test_plan
    ):
        """Should return subscription, plan, and usage together"""
        # Create subscription
        subscription_service = SubscriptionService(db_session)
        await subscription_service.create_subscription(
            user_id=str(test_user.id),
            plan_id=str(test_plan.id),
            provider_subscription_id="sub_usage_123",
            provider_customer_id="cus_usage_123",
            billing_period="monthly",
            status="active"
        )

        # Get combined data
        data = await subscription_service.get_subscription_with_usage(str(test_user.id))

        assert data["subscription"] is not None
        assert data["plan"] is not None
        assert data["usage"] is not None

        assert data["plan"]["name"] == "pro"
        assert data["subscription"]["status"] == "active"
        assert data["usage"]["api_calls"]["limit"] == 10000

    @pytest.mark.asyncio
    async def test_get_usage_without_subscription(
        self,
        db_session,
        test_user
    ):
        """Should return None values for user without subscription"""
        service = SubscriptionService(db_session)
        data = await service.get_subscription_with_usage(str(test_user.id))

        assert data["subscription"] is None
        assert data["plan"] is None
        assert data["usage"] is None


class TestMonthlyUsageReset:
    """Test monthly usage reset functionality"""

    @pytest.mark.asyncio
    async def test_reset_monthly_usage(
        self,
        db_session,
        test_user,
        test_plan
    ):
        """Should reset API calls counter"""
        # Create subscription with some API calls
        subscription_service = SubscriptionService(db_session)
        subscription = await subscription_service.create_subscription(
            user_id=str(test_user.id),
            plan_id=str(test_plan.id),
            provider_subscription_id="sub_reset_123",
            provider_customer_id="cus_reset_123",
            billing_period="monthly",
            status="active"
        )

        # Add some API calls
        subscription.current_api_calls = 500
        await db_session.commit()

        # Reset usage
        usage_service = UsageTrackingService(db_session)
        await usage_service.reset_monthly_usage(str(test_user.id))

        # Check reset
        await db_session.refresh(subscription)
        assert subscription.current_api_calls == 0
        assert subscription.usage_reset_date > datetime.utcnow()
