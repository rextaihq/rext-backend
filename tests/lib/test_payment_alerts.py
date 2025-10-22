"""
Tests for Payment Alert Functions

Tests the payment alert helper functions, alert triggering, and
integration with Sentry monitoring.

Phase 4, Task 4.2.3
"""

import pytest
from unittest.mock import Mock, patch, call
from src.api.lib.sentry_config import (
    trigger_payment_alert,
    alert_webhook_signature_failure,
    alert_api_error,
    alert_subscription_creation_failure,
    alert_checkout_failure,
    alert_cancellation_error,
)


class TestTriggerPaymentAlert:
    """Test trigger_payment_alert function"""

    @patch('sentry_sdk.capture_message')
    @patch('sentry_sdk.push_scope')
    def test_triggers_alert_with_correct_tags(self, mock_push_scope, mock_capture):
        """Test that alert is triggered with correct tags"""
        mock_scope = Mock()
        mock_push_scope.return_value.__enter__.return_value = mock_scope

        trigger_payment_alert(
            alert_type="test_alert",
            message="Test alert message",
            severity="high"
        )

        # Verify scope tags were set
        assert mock_scope.set_tag.called
        tag_calls = [call[0] for call in mock_scope.set_tag.call_args_list]
        assert ("alert", "true") in tag_calls
        assert ("alert_type", "test_alert") in tag_calls
        assert ("alert_severity", "high") in tag_calls

        # Verify message was captured
        mock_capture.assert_called_once_with("Test alert message", level="error")

    @patch('sentry_sdk.capture_message')
    @patch('sentry_sdk.push_scope')
    def test_includes_payment_tags(self, mock_push_scope, mock_capture):
        """Test that payment-specific tags are included"""
        mock_scope = Mock()
        mock_push_scope.return_value.__enter__.return_value = mock_scope

        trigger_payment_alert(
            alert_type="test",
            message="Test",
            user_id="user_123",
            subscription_id="sub_456",
            operation="checkout"
        )

        tag_calls = [call[0] for call in mock_scope.set_tag.call_args_list]
        assert ("user_id", "user_123") in tag_calls
        assert ("subscription_id", "sub_456") in tag_calls
        assert ("payment_operation", "checkout") in tag_calls
        assert ("payment_provider", "lemonsqueezy") in tag_calls

    @patch('sentry_sdk.capture_message')
    @patch('sentry_sdk.push_scope')
    def test_sets_correct_sentry_level_for_severity(self, mock_push_scope, mock_capture):
        """Test that Sentry level matches severity"""
        mock_scope = Mock()
        mock_push_scope.return_value.__enter__.return_value = mock_scope

        # Test critical -> error
        trigger_payment_alert("test", "Test", severity="critical")
        mock_capture.assert_called_with("Test", level="error")

        # Test high -> error
        trigger_payment_alert("test", "Test", severity="high")
        mock_capture.assert_called_with("Test", level="error")

        # Test medium -> warning
        trigger_payment_alert("test", "Test", severity="medium")
        mock_capture.assert_called_with("Test", level="warning")

        # Test low -> info
        trigger_payment_alert("test", "Test", severity="low")
        mock_capture.assert_called_with("Test", level="info")

    @patch('sentry_sdk.capture_message')
    @patch('sentry_sdk.push_scope')
    def test_includes_context(self, mock_push_scope, mock_capture):
        """Test that context is set correctly"""
        mock_scope = Mock()
        mock_push_scope.return_value.__enter__.return_value = mock_scope

        context = {
            "error_message": "Test error",
            "endpoint": "/test",
            "status_code": 500
        }

        trigger_payment_alert(
            "test",
            "Test",
            context=context
        )

        # Verify context was set
        mock_scope.set_context.assert_called_once()
        call_args = mock_scope.set_context.call_args[0]
        assert call_args[0] == "alert"
        assert "error_message" in call_args[1]


class TestAlertWebhookSignatureFailure:
    """Test alert_webhook_signature_failure function"""

    @patch('src.api.lib.sentry_config.trigger_payment_alert')
    def test_calls_trigger_with_correct_params(self, mock_trigger):
        """Test that alert is triggered with correct parameters"""
        alert_webhook_signature_failure(
            payload_length=1024,
            endpoint="/webhooks/test"
        )

        mock_trigger.assert_called_once()
        call_args = mock_trigger.call_args[1]
        assert call_args["alert_type"] == "webhook_signature_failure"
        assert call_args["severity"] == "high"
        assert call_args["operation"] == "webhook_verification"
        assert call_args["context"]["payload_length"] == 1024
        assert call_args["context"]["endpoint"] == "/webhooks/test"
        assert call_args["context"]["category"] == "security"


class TestAlertApiError:
    """Test alert_api_error function"""

    @patch('src.api.lib.sentry_config.trigger_payment_alert')
    def test_calls_trigger_for_5xx_errors(self, mock_trigger):
        """Test that 5xx errors trigger critical alerts"""
        alert_api_error(
            method="POST",
            endpoint="/checkouts",
            status_code=500,
            error_message="Internal Server Error",
            operation="checkout"
        )

        mock_trigger.assert_called_once()
        call_args = mock_trigger.call_args[1]
        assert call_args["alert_type"] == "api_error"
        assert call_args["severity"] == "critical"  # 5xx = critical
        assert call_args["operation"] == "checkout"

    @patch('src.api.lib.sentry_config.trigger_payment_alert')
    def test_calls_trigger_for_4xx_errors(self, mock_trigger):
        """Test that 4xx errors trigger high severity alerts"""
        alert_api_error(
            method="GET",
            endpoint="/subscriptions",
            status_code=404,
            error_message="Not Found",
            operation="get_subscription"
        )

        mock_trigger.assert_called_once()
        call_args = mock_trigger.call_args[1]
        assert call_args["severity"] == "high"  # 4xx = high

    @patch('src.api.lib.sentry_config.trigger_payment_alert')
    def test_includes_api_error_context(self, mock_trigger):
        """Test that API error context is included"""
        alert_api_error(
            method="PATCH",
            endpoint="/subscriptions/123",
            status_code=502,
            error_message="Bad Gateway",
            operation="update_subscription",
            user_id="user_123",
            subscription_id="sub_456"
        )

        call_args = mock_trigger.call_args[1]
        context = call_args["context"]
        assert context["method"] == "PATCH"
        assert context["endpoint"] == "/subscriptions/123"
        assert context["status_code"] == 502
        assert context["error_message"] == "Bad Gateway"
        assert context["category"] == "api_error"
        assert context["revenue_impact"] == "direct"


class TestAlertSubscriptionCreationFailure:
    """Test alert_subscription_creation_failure function"""

    @patch('src.api.lib.sentry_config.trigger_payment_alert')
    def test_calls_trigger_with_critical_severity(self, mock_trigger):
        """Test that subscription failures trigger critical alerts"""
        alert_subscription_creation_failure(
            user_id="user_123",
            variant_id="var_456",
            error_message="User not found",
            event_id="evt_789"
        )

        mock_trigger.assert_called_once()
        call_args = mock_trigger.call_args[1]
        assert call_args["alert_type"] == "subscription_creation_failure"
        assert call_args["severity"] == "critical"
        assert call_args["operation"] == "webhook_subscription_created"
        assert call_args["user_id"] == "user_123"

    @patch('src.api.lib.sentry_config.trigger_payment_alert')
    def test_includes_subscription_context(self, mock_trigger):
        """Test that subscription context is included"""
        alert_subscription_creation_failure(
            user_id="user_123",
            variant_id="var_456",
            error_message="Plan not found",
            event_id="evt_789"
        )

        call_args = mock_trigger.call_args[1]
        context = call_args["context"]
        assert context["variant_id"] == "var_456"
        assert context["error_message"] == "Plan not found"
        assert context["event_id"] == "evt_789"
        assert context["category"] == "subscription_failure"
        assert context["revenue_impact"] == "direct"
        assert context["customer_impact"] == "high"


class TestAlertCheckoutFailure:
    """Test alert_checkout_failure function"""

    @patch('src.api.lib.sentry_config.trigger_payment_alert')
    def test_calls_trigger_with_high_severity(self, mock_trigger):
        """Test that checkout failures trigger high severity alerts"""
        alert_checkout_failure(
            user_id="user_123",
            variant_id="var_456",
            error_message="API error",
            correlation_id="pay_abc123"
        )

        mock_trigger.assert_called_once()
        call_args = mock_trigger.call_args[1]
        assert call_args["alert_type"] == "checkout_failure"
        assert call_args["severity"] == "high"
        assert call_args["operation"] == "checkout"

    @patch('src.api.lib.sentry_config.trigger_payment_alert')
    def test_includes_correlation_id(self, mock_trigger):
        """Test that correlation ID is included"""
        alert_checkout_failure(
            user_id="user_123",
            variant_id="var_456",
            error_message="Test error",
            correlation_id="pay_xyz789"
        )

        call_args = mock_trigger.call_args[1]
        context = call_args["context"]
        assert context["correlation_id"] == "pay_xyz789"


class TestAlertCancellationError:
    """Test alert_cancellation_error function"""

    @patch('src.api.lib.sentry_config.trigger_payment_alert')
    def test_calls_trigger_with_medium_severity(self, mock_trigger):
        """Test that cancellation errors trigger medium severity alerts"""
        alert_cancellation_error(
            subscription_id="sub_123",
            user_id="user_456",
            error_message="API error"
        )

        mock_trigger.assert_called_once()
        call_args = mock_trigger.call_args[1]
        assert call_args["alert_type"] == "cancellation_error"
        assert call_args["severity"] == "medium"
        assert call_args["operation"] == "cancel_subscription"
        assert call_args["subscription_id"] == "sub_123"
        assert call_args["user_id"] == "user_456"


class TestIntegration:
    """Integration tests for alert system"""

    @patch('sentry_sdk.capture_message')
    @patch('sentry_sdk.push_scope')
    def test_full_alert_flow(self, mock_push_scope, mock_capture):
        """Test complete alert flow from helper to Sentry"""
        mock_scope = Mock()
        mock_push_scope.return_value.__enter__.return_value = mock_scope

        # Trigger a subscription creation failure alert
        alert_subscription_creation_failure(
            user_id="user_123",
            variant_id="var_456",
            error_message="User not found",
            event_id="evt_789"
        )

        # Verify all expected tags and context were set
        assert mock_scope.set_tag.called
        assert mock_scope.set_context.called
        assert mock_capture.called

        # Verify message includes user ID
        captured_message = mock_capture.call_args[0][0]
        assert "user_123" in captured_message
