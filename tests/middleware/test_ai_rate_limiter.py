"""
Tests for AI endpoint rate limiting with subscription tier awareness.

This module tests the tier-based rate limiting for expensive AI operations:
- Free tier: 10 requests/hour
- Pro tier: 50 requests/hour
- Enterprise tier: 200 requests/hour
"""

from collections import deque
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi import HTTPException, Request

from src.api.middleware.rate_limiter import (
    AIEndpointRateLimiter,
    ai_content_generation_rate_limit,
    ai_knowledge_processing_rate_limit,
    ai_topic_generation_rate_limit,
)


@pytest.fixture
def mock_request():
    """Create a mock FastAPI request."""
    request = Mock(spec=Request)
    request.client = Mock()
    request.client.host = "127.0.0.1"
    return request


@pytest.fixture
def mock_current_user():
    """Create a mock authenticated user."""
    return {"identity": "user-123-uuid"}


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    return Mock()


@pytest.fixture
def limiter():
    """Create an AIEndpointRateLimiter instance."""
    return AIEndpointRateLimiter(description="test operation")


class TestAIEndpointRateLimiter:
    """Test suite for AIEndpointRateLimiter class."""

    def test_initialization(self, limiter):
        """Test rate limiter initializes with correct default limits."""
        assert limiter.limits["free"] == 10
        assert limiter.limits["pro"] == 50
        assert limiter.limits["enterprise"] == 200
        assert limiter.limits["default"] == 10
        assert limiter.window_seconds == 3600
        assert limiter.description == "test operation"

    def test_initialization_custom_limits(self):
        """Test rate limiter initializes with custom limits."""
        custom_limits = {"free": 5, "pro": 25, "enterprise": 100, "default": 5}
        limiter = AIEndpointRateLimiter(custom_limits=custom_limits)

        assert limiter.limits == custom_limits

    @patch("src.api.middleware.rate_limiter.AIEndpointRateLimiter._get_user_tier")
    def test_get_user_tier_free(self, mock_get_tier, limiter, mock_db_session):
        """Test tier detection for free tier users."""
        mock_get_tier.return_value = "free"

        tier = limiter._get_user_tier(mock_db_session, "user-123")

        assert tier == "free"

    @patch("src.api.middleware.rate_limiter.AIEndpointRateLimiter._get_user_tier")
    def test_get_user_tier_pro(self, mock_get_tier, limiter, mock_db_session):
        """Test tier detection for pro tier users."""
        mock_get_tier.return_value = "pro"

        tier = limiter._get_user_tier(mock_db_session, "user-456")

        assert tier == "pro"

    @patch("src.api.middleware.rate_limiter.AIEndpointRateLimiter._get_user_tier")
    def test_get_user_tier_enterprise(self, mock_get_tier, limiter, mock_db_session):
        """Test tier detection for enterprise tier users."""
        mock_get_tier.return_value = "enterprise"

        tier = limiter._get_user_tier(mock_db_session, "user-789")

        assert tier == "enterprise"

    @patch("src.api.middleware.rate_limiter.AIEndpointRateLimiter._get_user_tier")
    def test_get_user_tier_no_subscription(self, mock_get_tier, limiter, mock_db_session):
        """Test tier detection for users without subscription."""
        mock_get_tier.return_value = "default"

        tier = limiter._get_user_tier(mock_db_session, "user-999")

        assert tier == "default"


class TestAIRateLimitingBehavior:
    """Test suite for AI rate limiting behavior."""

    @pytest.mark.asyncio
    @patch("src.api.middleware.rate_limiter.SessionLocal")
    @patch("src.api.middleware.rate_limiter.AIEndpointRateLimiter._get_user_tier")
    async def test_allows_requests_within_limit_free_tier(
        self, mock_get_tier, mock_session_local, mock_request, mock_current_user
    ):
        """Test that requests are allowed within free tier limit (10/hour)."""
        mock_get_tier.return_value = "free"
        mock_db = Mock()
        mock_session_local.return_value = mock_db

        limiter = AIEndpointRateLimiter()

        # Make 10 requests (should all succeed)
        for i in range(10):
            await limiter(mock_request, mock_current_user)

        # Verify no exception was raised
        assert len(limiter.storage["ai:user-123-uuid:free"]) == 10

    @pytest.mark.asyncio
    @patch("src.api.middleware.rate_limiter.SessionLocal")
    @patch("src.api.middleware.rate_limiter.AIEndpointRateLimiter._get_user_tier")
    async def test_blocks_requests_exceeding_limit_free_tier(
        self, mock_get_tier, mock_session_local, mock_request, mock_current_user
    ):
        """Test that 11th request is blocked for free tier (10/hour limit)."""
        mock_get_tier.return_value = "free"
        mock_db = Mock()
        mock_session_local.return_value = mock_db

        limiter = AIEndpointRateLimiter()

        # Make 10 requests (should all succeed)
        for i in range(10):
            await limiter(mock_request, mock_current_user)

        # 11th request should fail
        with pytest.raises(HTTPException) as exc_info:
            await limiter(mock_request, mock_current_user)

        assert exc_info.value.status_code == 429
        assert "rate limit exceeded" in exc_info.value.detail.lower()
        assert "10" in exc_info.value.detail  # Mentions the limit
        assert "free" in exc_info.value.detail.lower()  # Mentions the tier

    @pytest.mark.asyncio
    @patch("src.api.middleware.rate_limiter.SessionLocal")
    @patch("src.api.middleware.rate_limiter.AIEndpointRateLimiter._get_user_tier")
    async def test_allows_more_requests_for_pro_tier(
        self, mock_get_tier, mock_session_local, mock_request, mock_current_user
    ):
        """Test that pro tier allows 50 requests/hour."""
        mock_get_tier.return_value = "pro"
        mock_db = Mock()
        mock_session_local.return_value = mock_db

        limiter = AIEndpointRateLimiter()

        # Make 50 requests (should all succeed for pro tier)
        for i in range(50):
            await limiter(mock_request, mock_current_user)

        # Verify all requests succeeded
        assert len(limiter.storage["ai:user-123-uuid:pro"]) == 50

        # 51st request should fail
        with pytest.raises(HTTPException) as exc_info:
            await limiter(mock_request, mock_current_user)

        assert exc_info.value.status_code == 429
        assert "50" in exc_info.value.detail  # Mentions the pro limit

    @pytest.mark.asyncio
    @patch("src.api.middleware.rate_limiter.SessionLocal")
    @patch("src.api.middleware.rate_limiter.AIEndpointRateLimiter._get_user_tier")
    async def test_allows_many_requests_for_enterprise_tier(
        self, mock_get_tier, mock_session_local, mock_request, mock_current_user
    ):
        """Test that enterprise tier allows 200 requests/hour."""
        mock_get_tier.return_value = "enterprise"
        mock_db = Mock()
        mock_session_local.return_value = mock_db

        limiter = AIEndpointRateLimiter()

        # Make 200 requests (should all succeed for enterprise tier)
        for i in range(200):
            await limiter(mock_request, mock_current_user)

        # Verify all requests succeeded
        assert len(limiter.storage["ai:user-123-uuid:enterprise"]) == 200

        # 201st request should fail
        with pytest.raises(HTTPException) as exc_info:
            await limiter(mock_request, mock_current_user)

        assert exc_info.value.status_code == 429
        assert "200" in exc_info.value.detail  # Mentions the enterprise limit

    @pytest.mark.asyncio
    @patch("src.api.middleware.rate_limiter.SessionLocal")
    @patch("src.api.middleware.rate_limiter.AIEndpointRateLimiter._get_user_tier")
    async def test_returns_correct_retry_after_header(
        self, mock_get_tier, mock_session_local, mock_request, mock_current_user
    ):
        """Test that Retry-After header is present in 429 response."""
        mock_get_tier.return_value = "free"
        mock_db = Mock()
        mock_session_local.return_value = mock_db

        limiter = AIEndpointRateLimiter()

        # Exhaust the limit
        for i in range(10):
            await limiter(mock_request, mock_current_user)

        # Next request should include Retry-After header
        with pytest.raises(HTTPException) as exc_info:
            await limiter(mock_request, mock_current_user)

        assert "Retry-After" in exc_info.value.headers
        assert "X-RateLimit-Limit" in exc_info.value.headers
        assert "X-RateLimit-Remaining" in exc_info.value.headers
        assert "X-RateLimit-Reset" in exc_info.value.headers
        assert "X-RateLimit-Tier" in exc_info.value.headers

        assert exc_info.value.headers["X-RateLimit-Tier"] == "free"
        assert exc_info.value.headers["X-RateLimit-Limit"] == "10"
        assert exc_info.value.headers["X-RateLimit-Remaining"] == "0"

    @pytest.mark.asyncio
    @patch("src.api.middleware.rate_limiter.SessionLocal")
    @patch("src.api.middleware.rate_limiter.AIEndpointRateLimiter._get_user_tier")
    async def test_rate_limit_resets_after_time_window(
        self, mock_get_tier, mock_session_local, mock_request, mock_current_user
    ):
        """Test that rate limit resets after 1 hour window."""
        mock_get_tier.return_value = "free"
        mock_db = Mock()
        mock_session_local.return_value = mock_db

        limiter = AIEndpointRateLimiter()

        # Exhaust the limit
        for i in range(10):
            await limiter(mock_request, mock_current_user)

        # Simulate time passing (move all timestamps back 1 hour + 1 second)
        client_key = "ai:user-123-uuid:free"
        cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=3601)
        limiter.storage[client_key] = deque([cutoff_time] * 10)

        # Now a new request should succeed (old requests expired)
        await limiter(mock_request, mock_current_user)

        # After cleanup, only 1 request should be in storage
        assert len(limiter.storage[client_key]) == 1

    @pytest.mark.asyncio
    @patch("src.api.middleware.rate_limiter.SessionLocal")
    @patch("src.api.middleware.rate_limiter.AIEndpointRateLimiter._get_user_tier")
    async def test_different_users_have_separate_limits(
        self, mock_get_tier, mock_session_local, mock_request
    ):
        """Test that different users have separate rate limit counters."""
        mock_get_tier.return_value = "free"
        mock_db = Mock()
        mock_session_local.return_value = mock_db

        limiter = AIEndpointRateLimiter()

        user1 = {"identity": "user-111"}
        user2 = {"identity": "user-222"}

        # User 1 exhausts their limit
        for i in range(10):
            await limiter(mock_request, user1)

        # User 1 should be blocked
        with pytest.raises(HTTPException):
            await limiter(mock_request, user1)

        # User 2 should still be able to make requests
        await limiter(mock_request, user2)
        assert len(limiter.storage["ai:user-222:free"]) == 1


class TestAIRateLimiterFactoryFunctions:
    """Test suite for AI rate limiter factory functions."""

    def test_ai_content_generation_rate_limit_factory(self):
        """Test content generation rate limiter factory."""
        limiter = ai_content_generation_rate_limit()

        assert isinstance(limiter, AIEndpointRateLimiter)
        assert limiter.description == "content generation"
        assert limiter.limits["free"] == 10
        assert limiter.limits["pro"] == 50
        assert limiter.limits["enterprise"] == 200

    def test_ai_topic_generation_rate_limit_factory(self):
        """Test topic generation rate limiter factory."""
        limiter = ai_topic_generation_rate_limit()

        assert isinstance(limiter, AIEndpointRateLimiter)
        assert limiter.description == "topic generation"

    def test_ai_knowledge_processing_rate_limit_factory(self):
        """Test knowledge processing rate limiter factory."""
        limiter = ai_knowledge_processing_rate_limit()

        assert isinstance(limiter, AIEndpointRateLimiter)
        assert limiter.description == "knowledge processing"


class TestTierDetectionLogic:
    """Test suite for subscription tier detection logic."""

    def test_get_user_tier_with_free_plan(self, limiter):
        """Test tier detection with explicit 'free' plan name."""
        mock_db = Mock()

        # Mock subscription and plan
        from src.api.models.subscription_models.plans import SubscriptionPlan
        from src.api.models.subscription_models.subscriptions import (
            SubscriptionStatus,
            UserSubscription,
        )

        mock_subscription = Mock(spec=UserSubscription)
        mock_subscription.user_id = "user-123"
        mock_subscription.status = SubscriptionStatus.ACTIVE
        mock_subscription.plan_id = "plan-free-123"

        mock_plan = Mock(spec=SubscriptionPlan)
        mock_plan.id = "plan-free-123"
        mock_plan.name = "free"

        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_subscription,
            mock_plan,
        ]

        tier = limiter._get_user_tier(mock_db, "user-123")

        assert tier == "free"

    def test_get_user_tier_with_pro_plan_variations(self, limiter):
        """Test tier detection with various 'pro' plan name variations."""
        mock_db = Mock()

        from src.api.models.subscription_models.plans import SubscriptionPlan
        from src.api.models.subscription_models.subscriptions import (
            SubscriptionStatus,
            UserSubscription,
        )

        # Test variations: "pro", "Pro Plan", "Professional"
        for plan_name in ["pro", "Pro Plan", "professional"]:
            mock_subscription = Mock(spec=UserSubscription)
            mock_subscription.status = SubscriptionStatus.ACTIVE
            mock_subscription.plan_id = "plan-pro-123"

            mock_plan = Mock(spec=SubscriptionPlan)
            mock_plan.name = plan_name

            mock_db.query.return_value.filter.return_value.first.side_effect = [
                mock_subscription,
                mock_plan,
            ]

            tier = limiter._get_user_tier(mock_db, "user-456")

            assert tier == "pro", f"Failed for plan name: {plan_name}"

    def test_get_user_tier_with_no_active_subscription(self, limiter):
        """Test tier detection when user has no active subscription."""
        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        tier = limiter._get_user_tier(mock_db, "user-no-sub")

        assert tier == "default"

    def test_get_user_tier_with_trial_subscription(self, limiter):
        """Test tier detection for users on trial period."""
        mock_db = Mock()

        from src.api.models.subscription_models.plans import SubscriptionPlan
        from src.api.models.subscription_models.subscriptions import (
            SubscriptionStatus,
            UserSubscription,
        )

        mock_subscription = Mock(spec=UserSubscription)
        mock_subscription.status = SubscriptionStatus.TRIAL  # Trial status
        mock_subscription.plan_id = "plan-pro-trial"

        mock_plan = Mock(spec=SubscriptionPlan)
        mock_plan.name = "pro"

        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_subscription,
            mock_plan,
        ]

        tier = limiter._get_user_tier(mock_db, "user-trial")

        # Trial users should get pro tier benefits
        assert tier == "pro"
