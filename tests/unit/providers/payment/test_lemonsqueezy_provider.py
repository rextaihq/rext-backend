"""
Unit tests for LemonSqueezy Payment Provider

Tests all provider methods with mocked API responses to ensure correct behavior
without making real API calls.
"""

import pytest
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from src.providers.payment.providers.lemonsqueezy import (
    LemonSqueezyProvider,
    LemonSqueezyError,
    LemonSqueezyAPIError,
)
from src.providers.payment.base_provider import (
    CheckoutSession,
    SubscriptionData,
    CustomerData,
)


@pytest.fixture
def provider():
    """Create LemonSqueezy provider instance for testing."""
    return LemonSqueezyProvider(
        api_key="test_api_key",
        store_id="12345",
        webhook_secret="test_secret",
        sandbox_mode=True
    )


@pytest.fixture
def mock_response():
    """Create mock HTTP response."""
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {}
    return mock


class TestLemonSqueezyProviderInit:
    """Test provider initialization."""

    def test_init_with_all_params(self):
        """Test provider initialization with all parameters."""
        provider = LemonSqueezyProvider(
            api_key="test_key",
            store_id="123",
            webhook_secret="secret",
            sandbox_mode=True
        )

        assert provider.api_key == "test_key"
        assert provider.store_id == "123"
        assert provider.webhook_secret == "secret"
        assert provider.sandbox_mode is True
        assert provider.BASE_URL == "https://api.lemonsqueezy.com/v1"

    def test_init_without_webhook_secret(self):
        """Test provider initialization without webhook secret."""
        provider = LemonSqueezyProvider(
            api_key="test_key",
            store_id="123",
            sandbox_mode=False
        )

        assert provider.webhook_secret is None
        assert provider.sandbox_mode is False


class TestCreateCustomer:
    """Test create_customer method."""

    @pytest.mark.asyncio
    async def test_create_customer_returns_temp_id(self, provider):
        """Test that create_customer returns temporary ID."""
        customer_id = await provider.create_customer(
            email="test@example.com",
            name="Test User",
            metadata={"user_id": "123"}
        )

        assert customer_id == "temp_test@example.com"

    @pytest.mark.asyncio
    async def test_create_customer_without_metadata(self, provider):
        """Test create_customer without metadata."""
        customer_id = await provider.create_customer(
            email="user@test.com",
            name="User"
        )

        assert customer_id == "temp_user@test.com"


class TestGetCustomer:
    """Test get_customer method."""

    @pytest.mark.asyncio
    async def test_get_customer_success(self, provider, mock_response):
        """Test successful customer retrieval."""
        mock_response.json.return_value = {
            "data": {
                "id": "cust_123",
                "type": "customers",
                "attributes": {
                    "email": "test@example.com",
                    "name": "Test User"
                }
            }
        }

        with patch.object(provider.client, 'request', return_value=mock_response):
            customer = await provider.get_customer("cust_123")

        assert isinstance(customer, CustomerData)
        assert customer.customer_id == "cust_123"
        assert customer.email == "test@example.com"
        assert customer.name == "Test User"

    @pytest.mark.asyncio
    async def test_get_customer_api_error(self, provider, mock_response):
        """Test get_customer with API error."""
        mock_response.status_code = 404
        mock_response.json.return_value = {
            "errors": [{"detail": "Customer not found"}]
        }

        with patch.object(provider.client, 'request', return_value=mock_response):
            with pytest.raises(LemonSqueezyAPIError) as exc_info:
                await provider.get_customer("invalid_id")

            assert exc_info.value.status_code == 404
            assert "not found" in exc_info.value.message.lower()


class TestCreateCheckoutSession:
    """Test create_checkout_session method."""

    @pytest.mark.asyncio
    async def test_create_checkout_session_success(self, provider, mock_response):
        """Test successful checkout session creation."""
        mock_response.json.return_value = {
            "data": {
                "id": "checkout_123",
                "type": "checkouts",
                "attributes": {
                    "url": "https://checkout.lemonsqueezy.com/checkout_123"
                }
            }
        }

        with patch.object(provider.client, 'request', return_value=mock_response):
            session = await provider.create_checkout_session(
                customer_id="cust_123",
                price_id="variant_456",
                success_url="https://example.com/success",
                cancel_url="https://example.com/cancel",
                metadata={"order_id": "789"}
            )

        assert isinstance(session, CheckoutSession)
        assert session.session_id == "checkout_123"
        assert "checkout.lemonsqueezy.com" in session.checkout_url
        assert session.customer_id == "cust_123"
        assert session.metadata == {"order_id": "789"}

    @pytest.mark.asyncio
    async def test_create_checkout_session_uses_sandbox_mode(self, provider, mock_response):
        """Test that checkout session uses sandbox mode flag."""
        mock_response.json.return_value = {
            "data": {
                "id": "checkout_123",
                "type": "checkouts",
                "attributes": {"url": "https://test.com"}
            }
        }

        with patch.object(provider.client, 'request', return_value=mock_response) as mock_request:
            await provider.create_checkout_session(
                customer_id="cust_123",
                price_id="variant_456",
                success_url="https://example.com/success",
                cancel_url="https://example.com/cancel"
            )

            # Verify sandbox mode is set in request data
            call_args = mock_request.call_args
            request_data = call_args.kwargs['json']
            assert request_data['data']['attributes']['test_mode'] is True
            assert request_data['data']['attributes']['preview'] is True


class TestGetSubscription:
    """Test get_subscription method."""

    @pytest.mark.asyncio
    async def test_get_subscription_success(self, provider, mock_response):
        """Test successful subscription retrieval."""
        mock_response.json.return_value = {
            "data": {
                "id": "sub_123",
                "type": "subscriptions",
                "attributes": {
                    "status": "active",
                    "customer_id": "cust_123",
                    "variant_id": "variant_456",
                    "renews_at": "2024-12-01T00:00:00Z",
                    "ends_at": "2024-12-31T23:59:59Z",
                    "cancelled": False,
                    "cancelled_at": None,
                    "trial_ends_at": None
                }
            }
        }

        with patch.object(provider.client, 'request', return_value=mock_response):
            subscription = await provider.get_subscription("sub_123")

        assert isinstance(subscription, SubscriptionData)
        assert subscription.subscription_id == "sub_123"
        assert subscription.status == "active"
        assert subscription.customer_id == "cust_123"
        assert subscription.plan_id == "variant_456"
        assert subscription.cancel_at_period_end is False

    @pytest.mark.asyncio
    async def test_get_subscription_status_mapping(self, provider, mock_response):
        """Test subscription status mapping from LemonSqueezy to internal."""
        test_cases = [
            ("on_trial", "trialing"),
            ("active", "active"),
            ("paused", "paused"),
            ("past_due", "past_due"),
            ("unpaid", "past_due"),
            ("cancelled", "cancelled"),
            ("expired", "expired"),
        ]

        for ls_status, expected_status in test_cases:
            mock_response.json.return_value = {
                "data": {
                    "id": "sub_123",
                    "type": "subscriptions",
                    "attributes": {
                        "status": ls_status,
                        "customer_id": "cust_123",
                        "variant_id": "variant_456",
                        "renews_at": "2024-12-01T00:00:00Z",
                        "ends_at": "2024-12-31T23:59:59Z",
                        "cancelled": False
                    }
                }
            }

            with patch.object(provider.client, 'request', return_value=mock_response):
                subscription = await provider.get_subscription("sub_123")
                assert subscription.status == expected_status


class TestCancelSubscription:
    """Test cancel_subscription method."""

    @pytest.mark.asyncio
    async def test_cancel_subscription_success(self, provider, mock_response):
        """Test successful subscription cancellation."""
        # Mock DELETE response
        delete_response = MagicMock()
        delete_response.status_code = 200
        delete_response.json.return_value = {
            "data": {
                "id": "sub_123",
                "type": "subscriptions",
                "attributes": {"cancelled": True}
            }
        }

        # Mock GET response for refresh
        get_response = MagicMock()
        get_response.status_code = 200
        get_response.json.return_value = {
            "data": {
                "id": "sub_123",
                "type": "subscriptions",
                "attributes": {
                    "status": "cancelled",
                    "customer_id": "cust_123",
                    "variant_id": "variant_456",
                    "renews_at": "2024-12-01T00:00:00Z",
                    "ends_at": "2024-12-31T23:59:59Z",
                    "cancelled": True,
                    "cancelled_at": "2024-11-01T00:00:00Z"
                }
            }
        }

        with patch.object(provider.client, 'request', side_effect=[delete_response, get_response]):
            subscription = await provider.cancel_subscription("sub_123", at_period_end=True)

        assert isinstance(subscription, SubscriptionData)
        assert subscription.subscription_id == "sub_123"


class TestUpdateSubscription:
    """Test update_subscription method."""

    @pytest.mark.asyncio
    async def test_update_subscription_success(self, provider, mock_response):
        """Test successful subscription update."""
        # Mock PATCH response
        patch_response = MagicMock()
        patch_response.status_code = 200
        patch_response.json.return_value = {"data": {"id": "sub_123"}}

        # Mock GET response for refresh
        get_response = MagicMock()
        get_response.status_code = 200
        get_response.json.return_value = {
            "data": {
                "id": "sub_123",
                "type": "subscriptions",
                "attributes": {
                    "status": "active",
                    "customer_id": "cust_123",
                    "variant_id": "variant_789",  # New variant
                    "renews_at": "2024-12-01T00:00:00Z",
                    "ends_at": "2024-12-31T23:59:59Z",
                    "cancelled": False
                }
            }
        }

        with patch.object(provider.client, 'request', side_effect=[patch_response, get_response]):
            subscription = await provider.update_subscription("sub_123", "variant_789")

        assert subscription.plan_id == "variant_789"


class TestCreatePortalSession:
    """Test create_portal_session method."""

    @pytest.mark.asyncio
    async def test_create_portal_session(self, provider):
        """Test portal session URL generation."""
        portal_url = await provider.create_portal_session(
            customer_id="cust_123",
            return_url="https://example.com/dashboard"
        )

        assert "app.lemonsqueezy.com/my-orders" in portal_url
        assert "return_url=https://example.com/dashboard" in portal_url


class TestVerifyWebhookSignature:
    """Test verify_webhook_signature method."""

    @pytest.mark.asyncio
    async def test_verify_webhook_signature_valid(self, provider):
        """Test webhook signature verification with valid signature."""
        import hmac
        import hashlib

        payload = b'{"test": "data"}'
        expected_signature = hmac.new(
            provider.webhook_secret.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()

        is_valid = await provider.verify_webhook_signature(
            payload=payload,
            signature=expected_signature
        )

        assert is_valid is True

    @pytest.mark.asyncio
    async def test_verify_webhook_signature_invalid(self, provider):
        """Test webhook signature verification with invalid signature."""
        is_valid = await provider.verify_webhook_signature(
            payload=b'{"test": "data"}',
            signature="invalid_signature"
        )

        assert is_valid is False

    @pytest.mark.asyncio
    async def test_verify_webhook_signature_no_secret(self):
        """Test webhook signature verification without secret."""
        provider = LemonSqueezyProvider(
            api_key="test_key",
            store_id="123",
            webhook_secret=None,
            sandbox_mode=True
        )

        is_valid = await provider.verify_webhook_signature(
            payload=b'{"test": "data"}',
            signature="signature"
        )

        assert is_valid is False


class TestParseWebhookEvent:
    """Test parse_webhook_event method."""

    @pytest.mark.asyncio
    async def test_parse_webhook_event_complete(self, provider):
        """Test webhook event parsing with complete data."""
        payload = json.dumps({
            "meta": {
                "event_name": "subscription_created",
                "webhook_id": "webhook_123",
                "created_at": "2024-01-01T00:00:00Z"
            },
            "data": {
                "id": "sub_123",
                "type": "subscriptions",
                "attributes": {"status": "active"}
            }
        }).encode('utf-8')

        event = await provider.parse_webhook_event(payload)

        assert event["event_type"] == "subscription_created"
        assert event["event_id"] == "webhook_123"
        assert event["data"]["id"] == "sub_123"
        assert isinstance(event["timestamp"], datetime)

    @pytest.mark.asyncio
    async def test_parse_webhook_event_missing_fields(self, provider):
        """Test webhook event parsing with missing fields."""
        payload = json.dumps({
            "meta": {},
            "data": {}
        }).encode('utf-8')

        event = await provider.parse_webhook_event(payload)

        assert event["event_type"] == "unknown"
        assert event["event_id"] == ""
        assert isinstance(event["timestamp"], datetime)


class TestParseJsonApiData:
    """Test _parse_jsonapi_data helper method."""

    def test_parse_single_resource(self, provider):
        """Test parsing single JSON:API resource."""
        response = {
            "data": {
                "id": "123",
                "type": "test",
                "attributes": {
                    "name": "Test",
                    "value": 456
                }
            }
        }

        result = provider._parse_jsonapi_data(response)

        assert result["id"] == "123"
        assert result["type"] == "test"
        assert result["name"] == "Test"
        assert result["value"] == 456

    def test_parse_collection(self, provider):
        """Test parsing JSON:API collection."""
        response = {
            "data": [
                {
                    "id": "1",
                    "type": "test",
                    "attributes": {"name": "Item 1"}
                },
                {
                    "id": "2",
                    "type": "test",
                    "attributes": {"name": "Item 2"}
                }
            ]
        }

        result = provider._parse_jsonapi_data(response)

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["id"] == "1"
        assert result[1]["name"] == "Item 2"

    def test_parse_empty_response(self, provider):
        """Test parsing empty JSON:API response."""
        result = provider._parse_jsonapi_data({})
        assert result == {}


class TestMakeRequest:
    """Test _make_request helper method."""

    @pytest.mark.asyncio
    async def test_make_request_success(self, provider, mock_response):
        """Test successful API request."""
        mock_response.json.return_value = {"test": "data"}

        with patch.object(provider.client, 'request', return_value=mock_response):
            result = await provider._make_request("GET", "/test")

        assert result == {"test": "data"}

    @pytest.mark.asyncio
    async def test_make_request_api_error(self, provider, mock_response):
        """Test API request with error response."""
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "errors": [{"detail": "Bad request"}]
        }

        with patch.object(provider.client, 'request', return_value=mock_response):
            with pytest.raises(LemonSqueezyAPIError) as exc_info:
                await provider._make_request("POST", "/test")

            assert exc_info.value.status_code == 400
            assert "Bad request" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_make_request_http_error(self, provider):
        """Test API request with HTTP error."""
        with patch.object(provider.client, 'request', side_effect=httpx.HTTPError("Connection failed")):
            with pytest.raises(LemonSqueezyError) as exc_info:
                await provider._make_request("GET", "/test")

            assert "HTTP request failed" in str(exc_info.value)


class TestClose:
    """Test close method."""

    @pytest.mark.asyncio
    async def test_close(self, provider):
        """Test closing provider connection."""
        with patch.object(provider.client, 'aclose', new_callable=AsyncMock) as mock_close:
            await provider.close()
            mock_close.assert_called_once()
