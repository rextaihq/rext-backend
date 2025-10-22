"""
Tests for Sentry payment error tracking (Phase 4, Task 4.2.1).

Tests comprehensive error capture and context enrichment for all payment
operations including checkout, subscriptions, webhooks, and portal access.
"""

import pytest
from unittest.mock import patch, MagicMock, call
from uuid import uuid4

from src.api.lib.sentry_config import (
    capture_payment_exception,
    set_payment_context,
    add_payment_breadcrumb,
)


@pytest.fixture
def mock_sentry():
    """Mock sentry_sdk functions for testing."""
    with patch("src.api.lib.sentry_config.sentry_sdk") as mock_sdk:
        # Mock push_scope context manager
        mock_scope = MagicMock()
        mock_sdk.push_scope.return_value.__enter__.return_value = mock_scope
        mock_sdk.push_scope.return_value.__exit__.return_value = False

        # Mock capture_exception to return event ID
        mock_sdk.capture_exception.return_value = "test_event_id_123"

        yield mock_sdk


class TestCapturePaymentException:
    """Test suite for capture_payment_exception function."""

    def test_capture_with_basic_operation(self, mock_sentry):
        """Test capturing exception with basic operation."""
        exception = ValueError("Payment failed")

        event_id = capture_payment_exception(
            exception,
            operation="checkout"
        )

        assert event_id == "test_event_id_123"
        mock_sentry.capture_exception.assert_called_once_with(exception)

    def test_capture_with_all_payment_context(self, mock_sentry):
        """Test capturing exception with full payment context."""
        exception = RuntimeError("API Error")
        user_id = str(uuid4())
        subscription_id = str(uuid4())
        customer_id = "cus_123"
        plan_id = str(uuid4())
        amount = 29.99

        event_id = capture_payment_exception(
            exception,
            operation="checkout",
            user_id=user_id,
            subscription_id=subscription_id,
            customer_id=customer_id,
            plan_id=plan_id,
            amount=amount,
            context={"extra_field": "extra_value"}
        )

        assert event_id == "test_event_id_123"

        # Verify scope was configured
        mock_scope = mock_sentry.push_scope.return_value.__enter__.return_value

        # Verify tags were set
        assert mock_scope.set_tag.call_count >= 5
        tag_calls = mock_scope.set_tag.call_args_list
        assert call("payment_operation", "checkout") in tag_calls
        assert call("payment_provider", "lemonsqueezy") in tag_calls
        assert call("subscription_id", subscription_id) in tag_calls
        assert call("customer_id", customer_id) in tag_calls
        assert call("plan_id", plan_id) in tag_calls

        # Verify context was set
        mock_scope.set_context.assert_called_once()
        context_call = mock_scope.set_context.call_args
        assert context_call[0][0] == "payment"
        payment_context = context_call[0][1]
        assert payment_context["operation"] == "checkout"
        assert payment_context["provider"] == "lemonsqueezy"
        assert payment_context["user_id"] == user_id
        assert payment_context["subscription_id"] == subscription_id
        assert payment_context["customer_id"] == customer_id
        assert payment_context["plan_id"] == plan_id
        assert payment_context["amount"] == amount
        assert payment_context["extra_field"] == "extra_value"

    def test_capture_with_warning_level(self, mock_sentry):
        """Test capturing exception with warning level."""
        exception = Exception("Minor issue")

        capture_payment_exception(
            exception,
            operation="email_send",
            level="warning"
        )

        mock_scope = mock_sentry.push_scope.return_value.__enter__.return_value
        assert mock_scope.level == "warning"

    def test_capture_checkout_operation(self, mock_sentry):
        """Test capturing checkout-specific errors."""
        exception = ValueError("Invalid variant ID")

        capture_payment_exception(
            exception,
            operation="checkout",
            user_id="user_123",
            plan_id="plan_456",
            amount=29.99,
            context={
                "variant_id": "variant_789",
                "discount_code": "SAVE20"
            }
        )

        mock_scope = mock_sentry.push_scope.return_value.__enter__.return_value
        context_call = mock_scope.set_context.call_args[0][1]
        assert context_call["amount"] == 29.99
        assert context_call["variant_id"] == "variant_789"
        assert context_call["discount_code"] == "SAVE20"

    def test_capture_subscription_cancellation(self, mock_sentry):
        """Test capturing subscription cancellation errors."""
        exception = RuntimeError("Cancellation failed")

        capture_payment_exception(
            exception,
            operation="cancel_subscription",
            user_id="user_123",
            subscription_id="sub_456",
            context={
                "cancel_immediately": True,
                "reason": "User requested"
            }
        )

        mock_scope = mock_sentry.push_scope.return_value.__enter__.return_value
        tag_calls = mock_scope.set_tag.call_args_list
        assert call("payment_operation", "cancel_subscription") in tag_calls

    def test_capture_webhook_processing_error(self, mock_sentry):
        """Test capturing webhook processing errors."""
        exception = Exception("Invalid webhook payload")

        capture_payment_exception(
            exception,
            operation="webhook",
            subscription_id="sub_123",
            customer_id="cus_456",
            context={
                "event_type": "subscription_created",
                "event_id": "evt_789"
            }
        )

        mock_scope = mock_sentry.push_scope.return_value.__enter__.return_value
        context_call = mock_scope.set_context.call_args[0][1]
        assert context_call["event_type"] == "subscription_created"
        assert context_call["event_id"] == "evt_789"


class TestSetPaymentContext:
    """Test suite for set_payment_context function."""

    def test_set_basic_context(self, mock_sentry):
        """Test setting basic payment context."""
        set_payment_context(
            operation="checkout"
        )

        mock_sentry.set_context.assert_called_once()
        context_call = mock_sentry.set_context.call_args
        assert context_call[0][0] == "payment"
        payment_context = context_call[0][1]
        assert payment_context["operation"] == "checkout"
        assert payment_context["provider"] == "lemonsqueezy"

    def test_set_full_context(self, mock_sentry):
        """Test setting full payment context."""
        user_id = str(uuid4())
        subscription_id = str(uuid4())
        customer_id = "cus_123"
        plan_id = str(uuid4())

        set_payment_context(
            operation="update_subscription",
            user_id=user_id,
            subscription_id=subscription_id,
            customer_id=customer_id,
            plan_id=plan_id,
            amount=49.99,
            metadata={"upgrade": True}
        )

        context_call = mock_sentry.set_context.call_args[0][1]
        assert context_call["operation"] == "update_subscription"
        assert context_call["user_id"] == user_id
        assert context_call["subscription_id"] == subscription_id
        assert context_call["customer_id"] == customer_id
        assert context_call["plan_id"] == plan_id
        assert context_call["amount"] == 49.99
        assert context_call["metadata"] == {"upgrade": True}

        # Verify tags were set
        assert mock_sentry.set_tag.call_count >= 2
        tag_calls = mock_sentry.set_tag.call_args_list
        assert call("payment_operation", "update_subscription") in tag_calls
        assert call("payment_provider", "lemonsqueezy") in tag_calls

    def test_context_without_optional_fields(self, mock_sentry):
        """Test setting context without optional fields."""
        set_payment_context(operation="portal_access")

        context_call = mock_sentry.set_context.call_args[0][1]
        assert "user_id" not in context_call
        assert "subscription_id" not in context_call
        assert "customer_id" not in context_call
        assert context_call["operation"] == "portal_access"


class TestAddPaymentBreadcrumb:
    """Test suite for add_payment_breadcrumb function."""

    def test_add_basic_breadcrumb(self, mock_sentry):
        """Test adding basic payment breadcrumb."""
        add_payment_breadcrumb(
            "Creating checkout session",
            operation="checkout"
        )

        mock_sentry.add_breadcrumb.assert_called_once()
        breadcrumb_call = mock_sentry.add_breadcrumb.call_args[1]
        assert breadcrumb_call["message"] == "Creating checkout session"
        assert breadcrumb_call["category"] == "payment"
        assert breadcrumb_call["level"] == "info"
        assert breadcrumb_call["data"]["operation"] == "checkout"
        assert breadcrumb_call["data"]["provider"] == "lemonsqueezy"

    def test_add_breadcrumb_with_data(self, mock_sentry):
        """Test adding breadcrumb with additional data."""
        add_payment_breadcrumb(
            "Processing subscription update",
            operation="update_subscription",
            level="info",
            data={
                "subscription_id": "sub_123",
                "old_plan": "Basic",
                "new_plan": "Pro"
            }
        )

        breadcrumb_call = mock_sentry.add_breadcrumb.call_args[1]
        assert breadcrumb_call["data"]["subscription_id"] == "sub_123"
        assert breadcrumb_call["data"]["old_plan"] == "Basic"
        assert breadcrumb_call["data"]["new_plan"] == "Pro"

    def test_add_breadcrumb_warning_level(self, mock_sentry):
        """Test adding breadcrumb with warning level."""
        add_payment_breadcrumb(
            "Retry payment attempt",
            operation="payment_retry",
            level="warning"
        )

        breadcrumb_call = mock_sentry.add_breadcrumb.call_args[1]
        assert breadcrumb_call["level"] == "warning"

    def test_add_webhook_breadcrumb(self, mock_sentry):
        """Test adding webhook-specific breadcrumb."""
        add_payment_breadcrumb(
            "Processing webhook event",
            operation="webhook",
            data={
                "event_type": "subscription_created",
                "event_id": "evt_123"
            }
        )

        breadcrumb_call = mock_sentry.add_breadcrumb.call_args[1]
        assert breadcrumb_call["data"]["event_type"] == "subscription_created"
        assert breadcrumb_call["data"]["event_id"] == "evt_123"


class TestPaymentErrorGrouping:
    """Test payment error fingerprinting and grouping."""

    def test_lemonsqueezy_api_error_grouping(self):
        """Test LemonSqueezy API errors are grouped by status code."""
        event = {
            "exception": {
                "values": [{
                    "type": "LemonSqueezyAPIError",
                    "value": "LemonSqueezy API Error (404): Resource not found"
                }]
            },
            "tags": {
                "payment_operation": "get_subscription",
                "payment_provider": "lemonsqueezy"
            }
        }

        from src.api.lib.sentry_config import before_send_filter
        result = before_send_filter(event, {})

        assert result is not None
        assert "fingerprint" in result
        fingerprint = result["fingerprint"]
        assert fingerprint[0] == "lemonsqueezy"  # provider
        assert fingerprint[1] == "get_subscription"  # operation
        assert fingerprint[2] == "LemonSqueezyAPIError"  # error type
        assert fingerprint[3] == "404"  # status code

    def test_payment_operation_tagging(self):
        """Test payment operations are properly tagged."""
        event = {
            "exception": {
                "values": [{
                    "type": "ValueError",
                    "value": "Invalid plan ID"
                }]
            },
            "tags": {
                "payment_operation": "checkout",
                "payment_provider": "lemonsqueezy"
            }
        }

        from src.api.lib.sentry_config import before_send_filter
        result = before_send_filter(event, {})

        assert result is not None
        assert "fingerprint" in result


class TestPaymentTracesSampling:
    """Test payment endpoints get higher sampling rates."""

    def test_checkout_endpoint_sampling(self):
        """Test checkout endpoints are sampled at 100%."""
        from src.api.lib.sentry_config import traces_sampler

        sampling_context = {
            "asgi_scope": {
                "path": "/subscriptions/checkout"
            }
        }

        sample_rate = traces_sampler(sampling_context)
        assert sample_rate == 1.0  # 100% sampling

    def test_webhook_endpoint_sampling(self):
        """Test webhook endpoints are sampled at 100%."""
        from src.api.lib.sentry_config import traces_sampler

        sampling_context = {
            "asgi_scope": {
                "path": "/subscriptions/webhook"
            }
        }

        sample_rate = traces_sampler(sampling_context)
        assert sample_rate == 1.0  # 100% sampling

    def test_subscription_endpoint_sampling(self):
        """Test subscription endpoints are sampled at 80%."""
        from src.api.lib.sentry_config import traces_sampler

        sampling_context = {
            "asgi_scope": {
                "path": "/subscriptions/active"
            }
        }

        sample_rate = traces_sampler(sampling_context)
        assert sample_rate == 0.8  # 80% sampling

    def test_trial_endpoint_sampling(self):
        """Test trial endpoints are sampled at 80%."""
        from src.api.lib.sentry_config import traces_sampler

        sampling_context = {
            "asgi_scope": {
                "path": "/trials/start"
            }
        }

        sample_rate = traces_sampler(sampling_context)
        assert sample_rate == 0.8  # 80% sampling


@pytest.mark.integration
class TestSentryIntegrationWithPaymentFlow:
    """Integration tests for Sentry in payment flows."""

    def test_checkout_flow_with_sentry(self, mock_sentry):
        """Test complete checkout flow with Sentry tracking."""
        # Simulate checkout flow
        set_payment_context(
            operation="checkout",
            user_id="user_123",
            plan_id="plan_456"
        )

        add_payment_breadcrumb(
            "Starting checkout",
            operation="checkout",
            data={"plan_id": "plan_456"}
        )

        # Simulate error
        exception = ValueError("Invalid variant")
        capture_payment_exception(
            exception,
            operation="checkout",
            user_id="user_123",
            plan_id="plan_456"
        )

        # Verify all Sentry calls were made
        assert mock_sentry.set_context.called
        assert mock_sentry.add_breadcrumb.called
        assert mock_sentry.capture_exception.called

    def test_webhook_flow_with_sentry(self, mock_sentry):
        """Test webhook processing with Sentry tracking."""
        # Simulate webhook processing
        set_payment_context(
            operation="webhook_subscription_created",
            subscription_id="sub_123",
            customer_id="cus_456"
        )

        add_payment_breadcrumb(
            "Processing webhook",
            operation="webhook",
            data={"event_type": "subscription_created"}
        )

        # Verify Sentry was called
        assert mock_sentry.set_context.called
        assert mock_sentry.add_breadcrumb.called
