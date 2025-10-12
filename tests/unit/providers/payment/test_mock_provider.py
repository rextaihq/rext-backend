"""
Unit tests for MockPaymentProvider.

Tests the mock payment provider implementation to ensure it correctly
implements the PaymentProvider interface.
"""

import pytest
from datetime import datetime, timedelta

from src.providers.payment.mock_provider import MockPaymentProvider
from src.providers.payment.base_provider import CheckoutSession, SubscriptionData, CustomerData


class TestMockPaymentProviderBasics:
    """Test basic functionality of mock provider"""

    @pytest.fixture
    def provider(self):
        """Create fresh mock provider for each test"""
        return MockPaymentProvider()

    @pytest.mark.asyncio
    async def test_initialization(self, provider):
        """Test provider initializes with empty storage"""
        assert len(provider.customers) == 0
        assert len(provider.subscriptions) == 0
        assert len(provider.checkout_sessions) == 0

    @pytest.mark.asyncio
    async def test_create_customer(self, provider):
        """Test customer creation"""
        customer_id = await provider.create_customer(
            email="test@example.com",
            name="Test User",
            metadata={"user_id": "123"}
        )

        assert customer_id.startswith("cus_mock_")
        assert len(customer_id) == 21  # cus_mock_ + 12 hex chars
        assert customer_id in provider.customers
        assert provider.customers[customer_id]["email"] == "test@example.com"
        assert provider.customers[customer_id]["name"] == "Test User"
        assert provider.customers[customer_id]["metadata"]["user_id"] == "123"

    @pytest.mark.asyncio
    async def test_get_customer(self, provider):
        """Test retrieving customer details"""
        # Create customer
        customer_id = await provider.create_customer(
            email="test@example.com",
            name="Test User"
        )

        # Get customer
        customer = await provider.get_customer(customer_id)

        assert isinstance(customer, CustomerData)
        assert customer.customer_id == customer_id
        assert customer.email == "test@example.com"
        assert customer.name == "Test User"

    @pytest.mark.asyncio
    async def test_get_nonexistent_customer(self, provider):
        """Test getting customer that doesn't exist"""
        with pytest.raises(ValueError, match="Customer .* not found"):
            await provider.get_customer("cus_mock_nonexistent")


class TestMockPaymentProviderCheckout:
    """Test checkout session functionality"""

    @pytest.fixture
    def provider(self):
        return MockPaymentProvider()

    @pytest.mark.asyncio
    async def test_create_checkout_session(self, provider):
        """Test checkout session creation"""
        # Create customer first
        customer_id = await provider.create_customer(
            email="test@example.com",
            name="Test User"
        )

        # Create checkout session
        session = await provider.create_checkout_session(
            customer_id=customer_id,
            price_id="price_123",
            success_url="https://example.com/success",
            cancel_url="https://example.com/cancel",
            metadata={"plan_id": "plan_123"}
        )

        assert isinstance(session, CheckoutSession)
        assert session.session_id.startswith("cs_mock_")
        assert session.checkout_url == f"/mock-checkout/{session.session_id}"
        assert session.customer_id == customer_id
        assert session.metadata["plan_id"] == "plan_123"
        assert session.session_id in provider.checkout_sessions

    @pytest.mark.asyncio
    async def test_simulate_successful_checkout(self, provider):
        """Test simulating successful checkout"""
        # Create customer and checkout
        customer_id = await provider.create_customer(
            email="test@example.com",
            name="Test User"
        )
        session = await provider.create_checkout_session(
            customer_id=customer_id,
            price_id="price_123",
            success_url="https://example.com/success",
            cancel_url="https://example.com/cancel",
            metadata={"trial_days": 14}
        )

        # Simulate successful checkout
        subscription = provider.simulate_successful_checkout(
            session_id=session.session_id,
            plan_id="plan_123"
        )

        assert isinstance(subscription, SubscriptionData)
        assert subscription.subscription_id.startswith("sub_mock_")
        assert subscription.status == "active"
        assert subscription.customer_id == customer_id
        assert subscription.plan_id == "plan_123"
        assert subscription.trial_end is not None  # Has trial
        assert subscription.subscription_id in provider.subscriptions


class TestMockPaymentProviderSubscriptions:
    """Test subscription management functionality"""

    @pytest.fixture
    def provider(self):
        return MockPaymentProvider()

    async def setup_subscription(self, provider):
        """Setup a test subscription"""
        # Create customer
        customer_id = await provider.create_customer(
            email="test@example.com",
            name="Test User"
        )

        # Create checkout and simulate success
        session = await provider.create_checkout_session(
            customer_id=customer_id,
            price_id="price_123",
            success_url="https://example.com/success",
            cancel_url="https://example.com/cancel"
        )

        subscription = provider.simulate_successful_checkout(
            session_id=session.session_id,
            plan_id="plan_123"
        )

        return subscription

    @pytest.mark.asyncio
    async def test_get_subscription(self, provider):
        """Test retrieving subscription"""
        subscription = await self.setup_subscription(provider)
        retrieved = await provider.get_subscription(subscription.subscription_id)

        assert retrieved.subscription_id == subscription.subscription_id
        assert retrieved.status == "active"
        assert retrieved.plan_id == "plan_123"

    @pytest.mark.asyncio
    async def test_get_nonexistent_subscription(self, provider):
        """Test getting subscription that doesn't exist"""
        with pytest.raises(ValueError, match="Subscription .* not found"):
            await provider.get_subscription("sub_mock_nonexistent")

    @pytest.mark.asyncio
    async def test_cancel_subscription_at_period_end(self, provider):
        """Test cancelling subscription at period end"""
        subscription = await self.setup_subscription(provider)

        # Cancel at period end
        cancelled = await provider.cancel_subscription(
            subscription_id=subscription.subscription_id,
            at_period_end=True
        )

        assert cancelled.cancel_at_period_end is True
        assert cancelled.cancelled_at is not None
        assert cancelled.status == "active"  # Still active until period end

    @pytest.mark.asyncio
    async def test_cancel_subscription_immediately(self, provider):
        """Test cancelling subscription immediately"""
        subscription = await self.setup_subscription(provider)

        # Cancel immediately
        cancelled = await provider.cancel_subscription(
            subscription_id=subscription.subscription_id,
            at_period_end=False
        )

        assert cancelled.cancel_at_period_end is False
        assert cancelled.cancelled_at is not None
        assert cancelled.status == "cancelled"  # Cancelled immediately

    @pytest.mark.asyncio
    async def test_update_subscription(self, provider):
        """Test updating subscription to new plan"""
        subscription = await self.setup_subscription(provider)

        # Update to new plan
        updated = await provider.update_subscription(
            subscription_id=subscription.subscription_id,
            price_id="price_456"
        )

        assert updated.plan_id == "price_456"
        assert updated.subscription_id == subscription.subscription_id

    @pytest.mark.asyncio
    async def test_simulate_subscription_renewal(self, provider):
        """Test simulating subscription renewal"""
        subscription = await self.setup_subscription(provider)

        original_period_end = subscription.current_period_end

        # Simulate renewal
        renewed = provider.simulate_subscription_renewal(subscription.subscription_id)

        assert renewed.current_period_start == original_period_end
        assert renewed.current_period_end > original_period_end


class TestMockPaymentProviderPortal:
    """Test customer portal functionality"""

    @pytest.fixture
    def provider(self):
        return MockPaymentProvider()

    @pytest.mark.asyncio
    async def test_create_portal_session(self, provider):
        """Test creating portal session"""
        customer_id = await provider.create_customer(
            email="test@example.com",
            name="Test User"
        )

        portal_url = await provider.create_portal_session(
            customer_id=customer_id,
            return_url="https://example.com/dashboard"
        )

        assert portal_url == f"/mock-portal/{customer_id}?return_url=https://example.com/dashboard"


class TestMockPaymentProviderWebhooks:
    """Test webhook handling functionality"""

    @pytest.fixture
    def provider(self):
        return MockPaymentProvider()

    @pytest.mark.asyncio
    async def test_verify_webhook_signature(self, provider):
        """Test webhook signature verification (always true for mock)"""
        is_valid = await provider.verify_webhook_signature(
            payload=b'{"event": "test"}',
            signature="mock_signature"
        )

        assert is_valid is True

    @pytest.mark.asyncio
    async def test_parse_webhook_event(self, provider):
        """Test parsing webhook event"""
        payload = b'{"event_type": "subscription.created", "data": {"id": "sub_123"}}'

        event = await provider.parse_webhook_event(payload)

        assert event["event_type"] == "subscription.created"
        assert event["data"]["id"] == "sub_123"

    @pytest.mark.asyncio
    async def test_parse_invalid_webhook_event(self, provider):
        """Test parsing invalid JSON payload"""
        payload = b'{invalid json}'

        with pytest.raises(ValueError, match="Invalid webhook payload"):
            await provider.parse_webhook_event(payload)


class TestMockPaymentProviderReset:
    """Test provider reset functionality"""

    @pytest.fixture
    def provider(self):
        return MockPaymentProvider()

    @pytest.mark.asyncio
    async def test_reset(self, provider):
        """Test resetting provider data"""
        # Create some data
        await provider.create_customer("test@example.com", "Test User")
        session = await provider.create_checkout_session(
            customer_id="cus_test",
            price_id="price_123",
            success_url="https://example.com/success",
            cancel_url="https://example.com/cancel"
        )

        assert len(provider.customers) > 0
        assert len(provider.checkout_sessions) > 0

        # Reset
        provider.reset()

        assert len(provider.customers) == 0
        assert len(provider.subscriptions) == 0
        assert len(provider.checkout_sessions) == 0
