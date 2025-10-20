"""
Tests for payment endpoint rate limiting.

This module tests rate limiting for sensitive payment operations:
- Checkout: 5 requests/minute per user
- Subscription updates: 10 requests/minute per user
- Cancellation: 3 requests/minute per user
- Customer portal: 10 requests/minute per user
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock
from fastapi import HTTPException, Request
from collections import deque

from src.api.middleware.rate_limiter import (
    EndpointRateLimiter,
    checkout_rate_limit,
    subscription_update_rate_limit,
    subscription_cancel_rate_limit,
    customer_portal_rate_limit
)


@pytest.fixture
def mock_request():
    """Create a mock FastAPI request with user state."""
    request = Mock(spec=Request)
    request.client = Mock()
    request.client.host = "127.0.0.1"
    request.state = Mock()
    request.state.user_id = "user-123-uuid"
    return request


@pytest.fixture
def mock_request_unauthenticated():
    """Create a mock FastAPI request without user state."""
    request = Mock(spec=Request)
    request.client = Mock()
    request.client.host = "192.168.1.100"
    request.state = Mock()
    request.state.user_id = None
    return request


class TestEndpointRateLimiterPayments:
    """Test suite for payment endpoint rate limiters."""

    def test_checkout_rate_limiter_initialization(self):
        """Test checkout rate limiter initializes with correct limits."""
        limiter = checkout_rate_limit()

        assert limiter.requests == 5
        assert limiter.window_seconds == 60  # 1 minute
        assert limiter.description == "checkout"

    def test_subscription_update_rate_limiter_initialization(self):
        """Test subscription update rate limiter initializes with correct limits."""
        limiter = subscription_update_rate_limit()

        assert limiter.requests == 10
        assert limiter.window_seconds == 60  # 1 minute
        assert limiter.description == "subscription update"

    def test_subscription_cancel_rate_limiter_initialization(self):
        """Test subscription cancel rate limiter initializes with correct limits."""
        limiter = subscription_cancel_rate_limit()

        assert limiter.requests == 3
        assert limiter.window_seconds == 60  # 1 minute
        assert limiter.description == "subscription cancellation"

    def test_customer_portal_rate_limiter_initialization(self):
        """Test customer portal rate limiter initializes with correct limits."""
        limiter = customer_portal_rate_limit()

        assert limiter.requests == 10
        assert limiter.window_seconds == 60  # 1 minute
        assert limiter.description == "customer portal"

    @pytest.mark.asyncio
    async def test_checkout_allows_within_limit(self, mock_request):
        """Test checkout endpoint allows requests within rate limit."""
        limiter = checkout_rate_limit()

        # Should allow first 5 requests
        for i in range(5):
            await limiter(mock_request)

        # Verify we can make 5 requests
        assert len(limiter.storage["user:user-123-uuid"]) == 5

    @pytest.mark.asyncio
    async def test_checkout_blocks_exceeding_limit(self, mock_request):
        """Test checkout endpoint blocks requests exceeding rate limit."""
        limiter = checkout_rate_limit()

        # Make 5 requests (at the limit)
        for i in range(5):
            await limiter(mock_request)

        # 6th request should raise HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await limiter(mock_request)

        assert exc_info.value.status_code == 429
        assert "checkout" in exc_info.value.detail.lower()
        assert "Retry-After" in exc_info.value.headers

    @pytest.mark.asyncio
    async def test_subscription_update_allows_within_limit(self, mock_request):
        """Test subscription update endpoint allows requests within rate limit."""
        limiter = subscription_update_rate_limit()

        # Should allow first 10 requests
        for i in range(10):
            await limiter(mock_request)

        assert len(limiter.storage["user:user-123-uuid"]) == 10

    @pytest.mark.asyncio
    async def test_subscription_update_blocks_exceeding_limit(self, mock_request):
        """Test subscription update endpoint blocks requests exceeding rate limit."""
        limiter = subscription_update_rate_limit()

        # Make 10 requests (at the limit)
        for i in range(10):
            await limiter(mock_request)

        # 11th request should raise HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await limiter(mock_request)

        assert exc_info.value.status_code == 429
        assert "subscription update" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_cancel_allows_within_limit(self, mock_request):
        """Test cancel endpoint allows requests within rate limit."""
        limiter = subscription_cancel_rate_limit()

        # Should allow first 3 requests
        for i in range(3):
            await limiter(mock_request)

        assert len(limiter.storage["user:user-123-uuid"]) == 3

    @pytest.mark.asyncio
    async def test_cancel_blocks_exceeding_limit(self, mock_request):
        """Test cancel endpoint blocks requests exceeding rate limit."""
        limiter = subscription_cancel_rate_limit()

        # Make 3 requests (at the limit)
        for i in range(3):
            await limiter(mock_request)

        # 4th request should raise HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await limiter(mock_request)

        assert exc_info.value.status_code == 429
        assert "subscription cancellation" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_portal_allows_within_limit(self, mock_request):
        """Test customer portal endpoint allows requests within rate limit."""
        limiter = customer_portal_rate_limit()

        # Should allow first 10 requests
        for i in range(10):
            await limiter(mock_request)

        assert len(limiter.storage["user:user-123-uuid"]) == 10

    @pytest.mark.asyncio
    async def test_portal_blocks_exceeding_limit(self, mock_request):
        """Test customer portal endpoint blocks requests exceeding rate limit."""
        limiter = customer_portal_rate_limit()

        # Make 10 requests (at the limit)
        for i in range(10):
            await limiter(mock_request)

        # 11th request should raise HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await limiter(mock_request)

        assert exc_info.value.status_code == 429
        assert "customer portal" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_rate_limit_resets_after_window(self, mock_request):
        """Test rate limit resets after time window expires."""
        limiter = checkout_rate_limit()

        # Make 5 requests (at the limit)
        for i in range(5):
            await limiter(mock_request)

        # Simulate time passing (61 seconds = outside the 60 second window)
        client_key = "user:user-123-uuid"
        old_time = datetime.utcnow() - timedelta(seconds=61)
        limiter.storage[client_key] = deque([old_time] * 5)

        # Next request should succeed (old timestamps cleaned up)
        await limiter(mock_request)

        # Should have 1 request in storage (old ones cleaned)
        assert len(limiter.storage[client_key]) == 1

    @pytest.mark.asyncio
    async def test_rate_limit_per_user(self, mock_request):
        """Test rate limits are enforced per user."""
        limiter = checkout_rate_limit()

        # User 1 makes 5 requests
        mock_request.state.user_id = "user-1"
        for i in range(5):
            await limiter(mock_request)

        # User 1 is blocked
        with pytest.raises(HTTPException):
            await limiter(mock_request)

        # User 2 should still be able to make requests
        mock_request.state.user_id = "user-2"
        await limiter(mock_request)  # Should succeed

        assert len(limiter.storage["user:user-1"]) == 5
        assert len(limiter.storage["user:user-2"]) == 1

    @pytest.mark.asyncio
    async def test_rate_limit_unauthenticated_uses_ip(self, mock_request_unauthenticated):
        """Test rate limiting uses IP address for unauthenticated requests."""
        limiter = checkout_rate_limit()

        # Make 5 requests (at the limit)
        for i in range(5):
            await limiter(mock_request_unauthenticated)

        # Should use IP-based key
        assert len(limiter.storage["ip:192.168.1.100"]) == 5

        # 6th request should be blocked
        with pytest.raises(HTTPException) as exc_info:
            await limiter(mock_request_unauthenticated)

        assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_retry_after_header_accuracy(self, mock_request):
        """Test Retry-After header contains accurate time."""
        limiter = checkout_rate_limit()

        # Record start time
        start_time = datetime.utcnow()

        # Make 5 requests to hit the limit
        for i in range(5):
            await limiter(mock_request)

        # Try to make another request
        try:
            await limiter(mock_request)
            pytest.fail("Expected HTTPException to be raised")
        except HTTPException as e:
            retry_after = int(e.headers["Retry-After"])

            # Retry-After should be approximately 60 seconds (window duration)
            # Allow some tolerance for execution time
            assert 55 <= retry_after <= 61

    @pytest.mark.asyncio
    async def test_different_endpoints_have_different_limits(self, mock_request):
        """Test different payment endpoints have independent rate limits."""
        checkout_limiter = checkout_rate_limit()
        update_limiter = subscription_update_rate_limit()
        cancel_limiter = subscription_cancel_rate_limit()

        # Checkout allows 5
        assert checkout_limiter.requests == 5

        # Update allows 10
        assert update_limiter.requests == 10

        # Cancel allows 3
        assert cancel_limiter.requests == 3

        # Each limiter has separate storage
        for i in range(3):
            await checkout_limiter(mock_request)
        for i in range(3):
            await update_limiter(mock_request)
        for i in range(3):
            await cancel_limiter(mock_request)

        # All should succeed as they're independent
        assert len(checkout_limiter.storage["user:user-123-uuid"]) == 3
        assert len(update_limiter.storage["user:user-123-uuid"]) == 3
        assert len(cancel_limiter.storage["user:user-123-uuid"]) == 3


class TestPaymentRateLimiterEdgeCases:
    """Test edge cases and error scenarios for payment rate limiters."""

    @pytest.mark.asyncio
    async def test_concurrent_requests_same_user(self, mock_request):
        """Test handling of rapid concurrent requests from same user."""
        limiter = checkout_rate_limit()

        # Simulate 10 rapid concurrent requests (should block after 5)
        exceptions_count = 0
        success_count = 0

        for i in range(10):
            try:
                await limiter(mock_request)
                success_count += 1
            except HTTPException:
                exceptions_count += 1

        # First 5 should succeed, next 5 should fail
        assert success_count == 5
        assert exceptions_count == 5

    @pytest.mark.asyncio
    async def test_partial_window_expiry(self, mock_request):
        """Test partial cleanup of expired timestamps."""
        limiter = checkout_rate_limit()
        client_key = "user:user-123-uuid"

        # Add 3 old timestamps (expired) and 2 recent ones
        now = datetime.utcnow()
        old_time = now - timedelta(seconds=61)

        limiter.storage[client_key] = deque([
            old_time,  # Expired
            old_time,  # Expired
            old_time,  # Expired
            now,       # Valid
            now        # Valid
        ])

        # Make a new request
        await limiter(mock_request)

        # Should have cleaned up old timestamps and added new one
        # Result: 3 timestamps (2 recent + 1 new)
        assert len(limiter.storage[client_key]) == 3

    @pytest.mark.asyncio
    async def test_empty_storage_cleanup(self, mock_request):
        """Test behavior when storage is empty."""
        limiter = checkout_rate_limit()

        # Make first request with empty storage
        await limiter(mock_request)

        # Should create storage entry
        assert "user:user-123-uuid" in limiter.storage
        assert len(limiter.storage["user:user-123-uuid"]) == 1
