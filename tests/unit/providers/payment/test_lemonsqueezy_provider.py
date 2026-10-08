"""
Unit tests for LemonSqueezy Payment Provider

Tests all provider methods with mocked API responses to ensure correct behavior
without making real API calls.
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.providers.payment.base_provider import (
    CheckoutSession,
    CustomerData,
    SubscriptionData,
)
from src.providers.payment.providers.lemonsqueezy import (
    LemonSqueezyAPIError,
    LemonSqueezyError,
    LemonSqueezyProvider,
    LemonSqueezyTransientError,
)


@pytest.fixture
def provider():
    """Create LemonSqueezy provider instance for testing."""
    return LemonSqueezyProvider(
        api_key="test_api_key", store_id="12345", webhook_secret="test_secret", sandbox_mode=True
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
            api_key="test_key", store_id="123", webhook_secret="secret", sandbox_mode=True
        )

        assert provider.api_key == "test_key"
        assert provider.store_id == "123"
        assert provider.webhook_secret == "secret"
        assert provider.sandbox_mode is True
        assert provider.BASE_URL == "https://api.lemonsqueezy.com/v1"

    def test_init_without_webhook_secret(self):
        """Test provider initialization without webhook secret."""
        provider = LemonSqueezyProvider(api_key="test_key", store_id="123", sandbox_mode=False)

        assert provider.webhook_secret is None
        assert provider.sandbox_mode is False


class TestCreateCustomer:
    """Test create_customer method."""

    @pytest.mark.asyncio
    async def test_create_customer_returns_temp_id(self, provider):
        """Test that create_customer returns temporary ID."""
        customer_id = await provider.create_customer(
            email="test@example.com", name="Test User", metadata={"user_id": "123"}
        )

        assert customer_id == "temp_test@example.com"

    @pytest.mark.asyncio
    async def test_create_customer_without_metadata(self, provider):
        """Test create_customer without metadata."""
        customer_id = await provider.create_customer(email="user@test.com", name="User")

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
                "attributes": {"email": "test@example.com", "name": "Test User"},
            }
        }

        with patch.object(provider.client, "request", return_value=mock_response):
            customer = await provider.get_customer("cust_123")

        assert isinstance(customer, CustomerData)
        assert customer.customer_id == "cust_123"
        assert customer.email == "test@example.com"
        assert customer.name == "Test User"

    @pytest.mark.asyncio
    async def test_get_customer_api_error(self, provider, mock_response):
        """Test get_customer with API error."""
        mock_response.status_code = 404
        mock_response.json.return_value = {"errors": [{"detail": "Customer not found"}]}

        with patch.object(provider.client, "request", return_value=mock_response):
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
                "attributes": {"url": "https://checkout.lemonsqueezy.com/checkout_123"},
            }
        }

        with patch.object(provider.client, "request", return_value=mock_response):
            session = await provider.create_checkout_session(
                customer_id="cust_123",
                price_id="variant_456",
                success_url="https://example.com/success",
                cancel_url="https://example.com/cancel",
                metadata={"order_id": "789"},
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
                "attributes": {"url": "https://test.com"},
            }
        }

        with patch.object(provider.client, "request", return_value=mock_response) as mock_request:
            await provider.create_checkout_session(
                customer_id="cust_123",
                price_id="variant_456",
                success_url="https://example.com/success",
                cancel_url="https://example.com/cancel",
            )

            # Verify sandbox mode is set in request data
            call_args = mock_request.call_args
            request_data = call_args.kwargs["json"]
            assert request_data["data"]["attributes"]["test_mode"] is True
            assert request_data["data"]["attributes"]["preview"] is True


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
                    "trial_ends_at": None,
                },
            }
        }

        with patch.object(provider.client, "request", return_value=mock_response):
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
                        "cancelled": False,
                    },
                }
            }

            with patch.object(provider.client, "request", return_value=mock_response):
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
            "data": {"id": "sub_123", "type": "subscriptions", "attributes": {"cancelled": True}}
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
                    "cancelled_at": "2024-11-01T00:00:00Z",
                },
            }
        }

        with patch.object(provider.client, "request", side_effect=[delete_response, get_response]):
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
                    "cancelled": False,
                },
            }
        }

        with patch.object(
            provider.client, "request", side_effect=[patch_response, get_response]
        ) as request:
            subscription = await provider.update_subscription("sub_123", "variant_789")

        assert subscription.plan_id == "variant_789"
        # A customer's own change: the prorated difference is invoiced at once.
        sent = str(request.call_args_list[0])
        assert "'invoice_immediately': True" in sent and "disable_prorations" not in sent

    @pytest.mark.asyncio
    async def test_update_subscription_without_proration(self, provider):
        """An admin's change by default: nothing charged now, the new price from the renewal."""
        responses = []
        for _ in range(2):
            response = MagicMock()
            response.status_code = 200
            response.json.return_value = {
                "data": {
                    "id": "sub_123",
                    "type": "subscriptions",
                    "attributes": {
                        "status": "active",
                        "customer_id": "cust_123",
                        "variant_id": "variant_789",
                        "renews_at": "2024-12-01T00:00:00Z",
                        "ends_at": None,
                        "cancelled": False,
                    },
                }
            }
            responses.append(response)

        with patch.object(provider.client, "request", side_effect=responses) as request:
            await provider.update_subscription("sub_123", "variant_789", prorate=False)

        sent = str(request.call_args_list[0])
        assert "'disable_prorations': True" in sent and "invoice_immediately" not in sent

    @pytest.mark.asyncio
    async def test_a_change_that_went_through_is_not_a_failed_one(self, provider):
        """The PATCH is accepted and reading the subscription back fails: the change stands
        at Lemon Squeezy, so the error says so and a caller can't take it for a refusal."""
        from src.providers.payment.base_provider import PaymentChangeUnconfirmed

        accepted = MagicMock()
        accepted.status_code = 200
        accepted.json.return_value = {"data": {"id": "sub_123"}}

        async def read_back_fails(_subscription_id):
            raise TimeoutError("no answer")

        with (
            patch.object(provider.client, "request", side_effect=[accepted]),
            patch.object(provider, "get_subscription", side_effect=read_back_fails),
            pytest.raises(PaymentChangeUnconfirmed),
        ):
            await provider.update_subscription("sub_123", "variant_789")

    @pytest.mark.asyncio
    async def test_an_update_that_got_no_answer_is_neither_done_nor_refused(self, provider):
        """A timeout, a dropped connection or a server error on the PATCH: Lemon Squeezy may
        have applied it. The error says the outcome isn't known, so a caller can't tell an
        admin that nothing changed."""
        from src.providers.payment.base_provider import PaymentChangeUnknown
        from src.providers.payment.providers.lemonsqueezy import LemonSqueezyTransientError

        async def no_answer(**_request):
            raise LemonSqueezyTransientError("timed out")

        with (
            patch.object(provider, "_make_request", side_effect=no_answer),
            pytest.raises(PaymentChangeUnknown) as unknown,
        ):
            await provider.update_subscription("sub_123", "variant_789")

        # Nothing of Lemon Squeezy's, and no id, in what a caller may show.
        assert "sub_123" not in str(unknown.value)

    @pytest.mark.asyncio
    async def test_an_update_lemon_squeezy_refuses_is_still_a_refusal(self, provider):
        from src.providers.payment.providers.lemonsqueezy import LemonSqueezyAPIError

        async def refused(**_request):
            raise LemonSqueezyAPIError(422, "variant not in the store")

        with (
            patch.object(provider, "_make_request", side_effect=refused),
            pytest.raises(LemonSqueezyAPIError),
        ):
            await provider.update_subscription("sub_123", "variant_789")


class TestCreatePortalSession:
    """Test create_portal_session method."""

    @pytest.mark.asyncio
    async def test_create_portal_session(self, provider):
        """Test portal session URL generation."""
        portal_url = await provider.create_portal_session(
            customer_id="cust_123", return_url="https://example.com/dashboard"
        )

        assert "app.lemonsqueezy.com/my-orders" in portal_url
        assert "return_url=https://example.com/dashboard" in portal_url


class TestVerifyWebhookSignature:
    """Test verify_webhook_signature method."""

    @pytest.mark.asyncio
    async def test_verify_webhook_signature_valid(self, provider):
        """Test webhook signature verification with valid signature."""
        import hashlib
        import hmac

        payload = b'{"test": "data"}'
        expected_signature = hmac.new(
            provider.webhook_secret.encode("utf-8"), payload, hashlib.sha256
        ).hexdigest()

        is_valid = await provider.verify_webhook_signature(
            payload=payload, signature=expected_signature
        )

        assert is_valid is True

    @pytest.mark.asyncio
    async def test_verify_webhook_signature_invalid(self, provider):
        """Test webhook signature verification with invalid signature."""
        is_valid = await provider.verify_webhook_signature(
            payload=b'{"test": "data"}', signature="invalid_signature"
        )

        assert is_valid is False

    @pytest.mark.asyncio
    async def test_verify_webhook_signature_no_secret(self):
        """Test webhook signature verification without secret."""
        provider = LemonSqueezyProvider(
            api_key="test_key", store_id="123", webhook_secret=None, sandbox_mode=True
        )

        is_valid = await provider.verify_webhook_signature(
            payload=b'{"test": "data"}', signature="signature"
        )

        assert is_valid is False


class TestParseWebhookEvent:
    """Test parse_webhook_event method."""

    @pytest.mark.asyncio
    async def test_parse_webhook_event_complete(self, provider):
        """Test webhook event parsing with complete data."""
        payload = json.dumps(
            {
                "meta": {
                    "event_name": "subscription_created",
                    "webhook_id": "webhook_123",
                    "created_at": "2024-01-01T00:00:00Z",
                },
                "data": {
                    "id": "sub_123",
                    "type": "subscriptions",
                    "attributes": {"status": "active"},
                },
            }
        ).encode("utf-8")

        event = await provider.parse_webhook_event(payload)

        assert event["event_type"] == "subscription_created"
        assert event["event_id"] == "webhook_123"
        assert event["data"]["id"] == "sub_123"
        assert isinstance(event["timestamp"], datetime)

    @pytest.mark.asyncio
    async def test_parse_webhook_event_missing_fields(self, provider):
        """Test webhook event parsing with missing fields."""
        payload = json.dumps({"meta": {}, "data": {}}).encode("utf-8")

        event = await provider.parse_webhook_event(payload)

        assert event["event_type"] == "unknown"
        assert event["event_id"] == ""
        assert isinstance(event["timestamp"], datetime)


class TestParseJsonApiData:
    """Test _parse_jsonapi_data helper method."""

    def test_parse_single_resource(self, provider):
        """Test parsing single JSON:API resource."""
        response = {
            "data": {"id": "123", "type": "test", "attributes": {"name": "Test", "value": 456}}
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
                {"id": "1", "type": "test", "attributes": {"name": "Item 1"}},
                {"id": "2", "type": "test", "attributes": {"name": "Item 2"}},
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

        with patch.object(provider.client, "request", return_value=mock_response):
            result = await provider._make_request("GET", "/test")

        assert result == {"test": "data"}

    @pytest.mark.asyncio
    async def test_make_request_api_error(self, provider, mock_response):
        """Test API request with error response."""
        mock_response.status_code = 400
        mock_response.json.return_value = {"errors": [{"detail": "Bad request"}]}

        with patch.object(provider.client, "request", return_value=mock_response):
            with pytest.raises(LemonSqueezyAPIError) as exc_info:
                await provider._make_request("POST", "/test")

            assert exc_info.value.status_code == 400
            assert "Bad request" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_make_request_http_error(self, provider):
        """Test API request with HTTP error."""
        with patch.object(
            provider.client, "request", side_effect=httpx.HTTPError("Connection failed")
        ):
            with pytest.raises(LemonSqueezyError) as exc_info:
                await provider._make_request("GET", "/test")

            assert "HTTP request failed" in str(exc_info.value)


class TestRetryLogic:
    """Test retry logic for transient errors."""

    @pytest.mark.asyncio
    async def test_retry_on_timeout(self, provider, mock_response):
        """Verify that httpx.TimeoutException triggers retry and eventually succeeds."""
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"id": "1"}}

        call_count = 0

        async def mock_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise httpx.TimeoutException("Simulated timeout")
            return mock_response

        with patch.object(provider.client, "request", side_effect=mock_request):
            result = await provider._make_request("GET", "/test")

        assert call_count == 3  # 2 failures + 1 success
        assert result == {"data": {"id": "1"}}

    @pytest.mark.asyncio
    async def test_retry_on_network_error(self, provider, mock_response):
        """Verify that httpx.NetworkError triggers retry."""
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True}

        call_count = 0

        async def mock_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise httpx.NetworkError("Network unreachable")
            return mock_response

        with patch.object(provider.client, "request", side_effect=mock_request):
            result = await provider._make_request("GET", "/test")

        assert call_count == 2  # 1 failure + 1 success
        assert result == {"success": True}

    @pytest.mark.asyncio
    async def test_retry_on_500_error(self, provider):
        """Verify that 500 server error triggers retry."""
        error_response = MagicMock()
        error_response.status_code = 500
        error_response.json.return_value = {"errors": [{"detail": "Internal server error"}]}
        error_response.headers.get.return_value = None

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {"data": "success"}

        call_count = 0

        async def mock_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                return error_response
            return success_response

        with patch.object(provider.client, "request", side_effect=mock_request):
            result = await provider._make_request("GET", "/test")

        assert call_count == 2  # 1 failure + 1 success
        assert result == {"data": "success"}

    @pytest.mark.asyncio
    async def test_retry_on_429_rate_limit(self, provider):
        """Verify that 429 rate limit triggers retry."""
        rate_limit_response = MagicMock()
        rate_limit_response.status_code = 429
        rate_limit_response.json.return_value = {"errors": [{"detail": "Rate limit exceeded"}]}
        rate_limit_response.headers.get.return_value = "5"

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {"data": "success"}

        call_count = 0

        async def mock_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                return rate_limit_response
            return success_response

        with patch.object(provider.client, "request", side_effect=mock_request):
            result = await provider._make_request("GET", "/test")

        assert call_count == 2  # 1 rate limit + 1 success
        assert result == {"data": "success"}

    @pytest.mark.asyncio
    async def test_no_retry_on_400_error(self, provider):
        """Verify that 4xx client errors do NOT retry."""
        error_response = MagicMock()
        error_response.status_code = 400
        error_response.json.return_value = {"errors": [{"detail": "Bad request"}]}

        call_count = 0

        async def mock_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return error_response

        with patch.object(provider.client, "request", side_effect=mock_request):
            with pytest.raises(LemonSqueezyAPIError) as exc_info:
                await provider._make_request("POST", "/test")

        assert call_count == 1  # No retry for 4xx
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_no_retry_on_404_error(self, provider):
        """Verify that 404 not found does NOT retry."""
        error_response = MagicMock()
        error_response.status_code = 404
        error_response.json.return_value = {"errors": [{"detail": "Not found"}]}

        call_count = 0

        async def mock_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return error_response

        with patch.object(provider.client, "request", side_effect=mock_request):
            with pytest.raises(LemonSqueezyAPIError) as exc_info:
                await provider._make_request("GET", "/test")

        assert call_count == 1  # No retry for 404
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_retry_exhaustion(self, provider):
        """Verify that after 3 failed attempts, the last exception is raised."""
        call_count = 0

        async def mock_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise httpx.TimeoutException("Persistent timeout")

        with patch.object(provider.client, "request", side_effect=mock_request):
            with pytest.raises(LemonSqueezyTransientError) as exc_info:
                await provider._make_request("GET", "/test")

        assert call_count == 3  # 3 attempts before giving up
        assert "timeout" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_retry_exhaustion_on_500(self, provider):
        """Verify that persistent 5xx errors exhaust retries."""
        error_response = MagicMock()
        error_response.status_code = 503
        error_response.json.return_value = {"errors": [{"detail": "Service unavailable"}]}
        error_response.headers.get.return_value = None

        call_count = 0

        async def mock_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return error_response

        with patch.object(provider.client, "request", side_effect=mock_request):
            with pytest.raises(LemonSqueezyTransientError) as exc_info:
                await provider._make_request("GET", "/test")

        assert call_count == 3  # 3 attempts before giving up
        assert exc_info.value.status_code == 503


class TestGetInvoices:
    """Test get_invoices method (orders + subscription-invoices)."""

    @staticmethod
    def _order(order_id, number, created_at, total=39900, status="paid", refunded=False):
        return {
            "id": order_id,
            "type": "orders",
            "attributes": {
                "order_number": number,
                "status": status,
                "refunded": refunded,
                "total": total,
                "subtotal": total,
                "tax": 0,
                "currency": "USD",
                "user_email": "user@example.com",
                "user_name": "Test User",
                "urls": {"receipt": f"https://ls/receipt/{order_id}"},
                "created_at": created_at,
                "updated_at": created_at,
            },
        }

    @staticmethod
    def _sub_invoice(inv_id, created_at, total=39900, status="paid", reason="renewal"):
        return {
            "id": inv_id,
            "type": "subscription-invoices",
            "attributes": {
                "billing_reason": reason,
                "status": status,
                "refunded": False,
                "total": total,
                "subtotal": total,
                "tax": 0,
                "currency": "USD",
                "card_brand": "visa",
                "card_last_four": "4242",
                "user_email": "user@example.com",
                "user_name": "Test User",
                "urls": {"invoice_url": f"https://ls/invoice/{inv_id}"},
                "created_at": created_at,
                "updated_at": created_at,
            },
        }

    @pytest.mark.asyncio
    async def test_merges_orders_and_subscription_invoices_sorted_desc(self, provider):
        async def fake_make_request(method, endpoint, params=None, **kwargs):
            if endpoint == "/orders":
                return {
                    "data": [self._order("9358138", 230544158, "2026-09-01T13:32:14.000000Z")],
                    "meta": {"page": {"currentPage": 1, "lastPage": 1}},
                }
            if endpoint == "/subscription-invoices":
                return {
                    "data": [self._sub_invoice("555", "2026-10-01T13:32:14.000000Z")],
                    "meta": {"page": {"currentPage": 1, "lastPage": 1}},
                }
            return {"data": []}

        with patch.object(provider, "_make_request", side_effect=fake_make_request):
            result = await provider.get_invoices(
                user_email="user@example.com", limit=10, subscription_ids=["2492404"]
            )

        assert [inv["source"] for inv in result] == ["subscription_invoice", "order"]
        # invoice_number is always a string (LS order_number is an int)
        assert result[1]["invoice_number"] == "230544158"
        assert isinstance(result[1]["invoice_number"], str)
        assert result[0]["invoice_url"] == "https://ls/invoice/555"
        assert result[0]["amount"] == 399.0

    @pytest.mark.asyncio
    async def test_initial_order_deduped_against_initial_subscription_invoice(self, provider):
        async def fake_make_request(method, endpoint, params=None, **kwargs):
            if endpoint == "/orders":
                return {
                    "data": [self._order("9358138", 230544158, "2026-09-01T13:32:14.000000Z")],
                    "meta": {"page": {"currentPage": 1, "lastPage": 1}},
                }
            if endpoint == "/subscription-invoices":
                return {
                    "data": [
                        self._sub_invoice(
                            "8341199", "2026-09-01T13:32:42.000000Z", reason="initial"
                        )
                    ],
                    "meta": {"page": {"currentPage": 1, "lastPage": 1}},
                }
            return {"data": []}

        with patch.object(provider, "_make_request", side_effect=fake_make_request):
            result = await provider.get_invoices(
                user_email="user@example.com", limit=10, subscription_ids=["2492404"]
            )

        assert len(result) == 1
        assert result[0]["source"] == "subscription_invoice"

    @pytest.mark.asyncio
    async def test_no_subscription_ids_falls_back_to_orders_only(self, provider):
        async def fake_make_request(method, endpoint, params=None, **kwargs):
            assert endpoint == "/orders"
            return {
                "data": [self._order("1", 1001, "2026-01-01T00:00:00.000000Z")],
                "meta": {"page": {"currentPage": 1, "lastPage": 1}},
            }

        with patch.object(provider, "_make_request", side_effect=fake_make_request):
            result = await provider.get_invoices(user_email="user@example.com", limit=10)

        assert len(result) == 1
        assert result[0]["source"] == "order"

    @pytest.mark.asyncio
    async def test_empty_history_returns_empty_list(self, provider):
        with patch.object(provider, "_make_request", AsyncMock(return_value={"data": []})):
            result = await provider.get_invoices(
                user_email="nobody@example.com", limit=10, subscription_ids=[]
            )
        assert result == []

    @pytest.mark.asyncio
    async def test_subscription_invoice_failure_does_not_break_orders(self, provider):
        async def fake_make_request(method, endpoint, params=None, **kwargs):
            if endpoint == "/orders":
                return {
                    "data": [self._order("1", 1001, "2026-01-01T00:00:00.000000Z")],
                    "meta": {"page": {"currentPage": 1, "lastPage": 1}},
                }
            raise LemonSqueezyAPIError(status_code=400, message="boom")

        with patch.object(provider, "_make_request", side_effect=fake_make_request):
            result = await provider.get_invoices(
                user_email="user@example.com", limit=10, subscription_ids=["sub_1"]
            )

        assert len(result) == 1
        assert result[0]["source"] == "order"

    @pytest.mark.asyncio
    async def test_pagination_follows_last_page_and_respects_limit(self, provider):
        pages = {
            1: {
                "data": [
                    self._order(f"o{i}", 1000 + i, f"2026-01-0{i}T00:00:00.000000Z")
                    for i in range(1, 4)
                ],
                "meta": {"page": {"currentPage": 1, "lastPage": 2}},
            },
            2: {
                "data": [
                    self._order(f"p{i}", 2000 + i, f"2026-02-0{i}T00:00:00.000000Z")
                    for i in range(1, 4)
                ],
                "meta": {"page": {"currentPage": 2, "lastPage": 2}},
            },
        }

        async def fake_make_request(method, endpoint, params=None, **kwargs):
            if endpoint == "/orders":
                return pages[params["page[number]"]]
            return {"data": []}

        with patch.object(provider, "_make_request", side_effect=fake_make_request):
            result = await provider.get_invoices(user_email="user@example.com", limit=5)

        assert len(result) == 5


class TestReconcileAndSettleReads:
    """The reconciler's read and the duplicate settlement's invoice (F11, #336)."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "answer",
        [
            {},
            {"data": {"attributes": {}}},
            {"data": {"attributes": {"updated_at": "2026-10-06T09:00:00Z"}}},
            {"data": {"attributes": {"status": "weird", "updated_at": "2026-10-06T09:00:00Z"}}},
            {"data": {"attributes": {"status": "unpaid"}}},
        ],
    )
    async def test_an_incomplete_subscription_read_is_refused(self, provider, answer):
        """Applied anyway, a missing status would read as active and give the plan back."""
        with patch.object(provider, "_make_request", AsyncMock(return_value=answer)):
            with pytest.raises(LemonSqueezyError):
                await provider.get_subscription_attributes("sub_1")

    @pytest.mark.asyncio
    async def test_a_complete_subscription_read_is_returned(self, provider):
        attributes = {"status": "unpaid", "updated_at": "2026-10-06T09:00:00Z"}
        answer = {"data": {"attributes": attributes}}
        with patch.object(provider, "_make_request", AsyncMock(return_value=answer)):
            assert await provider.get_subscription_attributes("sub_1") == attributes

    @pytest.mark.asyncio
    async def test_the_latest_invoice_is_the_newest_whatever_its_status(self, provider):
        """A partly refunded newest invoice is returned as it is, never an older paid one."""
        rows = [
            {"id": "1", "status": "paid", "total": 8900, "created_at": "2026-08-06T09:00:00Z"},
            {
                "id": "2",
                "status": "partial_refund",
                "total": 8900,
                "refunded": True,
                "created_at": "2026-09-06T09:00:00Z",
            },
        ]
        with patch.object(provider, "_paginate", AsyncMock(return_value=rows)) as paginate:
            invoice = await provider.latest_invoice("sub_1")

        assert invoice == {"id": "2", "status": "partial_refund", "total": 8900, "refunded": True}
        params = paginate.await_args.args[1]
        assert params == {"filter[subscription_id]": "sub_1"}

    @pytest.mark.asyncio
    async def test_no_invoice_is_none(self, provider):
        with patch.object(provider, "_paginate", AsyncMock(return_value=[])):
            assert await provider.latest_invoice("sub_1") is None


class TestClose:
    """Test close method."""

    @pytest.mark.asyncio
    async def test_close(self, provider):
        """Test closing provider connection."""
        with patch.object(provider.client, "aclose", new_callable=AsyncMock) as mock_close:
            await provider.close()
            mock_close.assert_called_once()
