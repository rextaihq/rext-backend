"""
Tests for Payment Logging Utilities

Tests the payment-specific logging helpers, correlation IDs, timing context,
and structured logging functionality.

Phase 4, Task 4.2.2
"""

import pytest
import time
import structlog
from contextlib import nullcontext as does_not_raise
from unittest.mock import Mock, patch, MagicMock

from src.api.lib.logging_config import (
    PaymentLogContext,
    generate_payment_correlation_id,
    bind_payment_context,
    log_payment_operation,
    log_payment_timing,
    clear_payment_context,
)


class TestPaymentLogContext:
    """Test PaymentLogContext dataclass"""

    def test_minimal_context(self):
        """Test context with only required fields"""
        context = PaymentLogContext(operation="checkout")

        assert context.operation == "checkout"
        assert context.provider == "lemonsqueezy"
        assert context.user_id is None

    def test_full_context(self):
        """Test context with all fields"""
        context = PaymentLogContext(
            operation="checkout",
            provider="lemonsqueezy",
            user_id="user_123",
            subscription_id="sub_456",
            customer_id="cus_789",
            plan_id="plan_abc",
            variant_id="var_def",
            status="active",
            amount=2999,
            currency="USD",
            event_type="subscription_created",
            correlation_id="pay_123abc"
        )

        assert context.operation == "checkout"
        assert context.user_id == "user_123"
        assert context.subscription_id == "sub_456"
        assert context.amount == 2999

    def test_to_dict_excludes_none(self):
        """Test that to_dict excludes None values"""
        context = PaymentLogContext(
            operation="checkout",
            user_id="user_123",
            subscription_id=None,
        )

        result = context.to_dict()

        assert "operation" in result
        assert "user_id" in result
        assert "subscription_id" not in result  # None values excluded
        assert "provider" in result  # Has default value


class TestGeneratePaymentCorrelationId:
    """Test correlation ID generation"""

    def test_generates_unique_ids(self):
        """Test that each call generates a unique ID"""
        id1 = generate_payment_correlation_id()
        id2 = generate_payment_correlation_id()

        assert id1 != id2
        assert isinstance(id1, str)
        assert isinstance(id2, str)

    def test_id_format(self):
        """Test that IDs have the expected format"""
        correlation_id = generate_payment_correlation_id()

        assert correlation_id.startswith("pay_")
        assert len(correlation_id) == 20  # "pay_" + 16 hex chars

    def test_id_is_hex(self):
        """Test that ID contains only hex characters"""
        correlation_id = generate_payment_correlation_id()
        hex_part = correlation_id[4:]  # Remove "pay_" prefix

        # Should not raise ValueError
        int(hex_part, 16)


class TestBindPaymentContext:
    """Test payment context binding"""

    def test_bind_minimal_context(self):
        """Test binding with minimal fields"""
        with patch('structlog.contextvars.bind_contextvars') as mock_bind:
            bind_payment_context(operation="checkout")

            mock_bind.assert_called_once()
            call_args = mock_bind.call_args[1]
            assert call_args["operation"] == "checkout"
            assert call_args["provider"] == "lemonsqueezy"

    def test_bind_full_context(self):
        """Test binding with all fields"""
        with patch('structlog.contextvars.bind_contextvars') as mock_bind:
            bind_payment_context(
                operation="checkout",
                user_id="user_123",
                subscription_id="sub_456",
                customer_id="cus_789",
                plan_id="plan_abc"
            )

            mock_bind.assert_called_once()
            call_args = mock_bind.call_args[1]
            assert call_args["user_id"] == "user_123"
            assert call_args["subscription_id"] == "sub_456"

    def test_bind_with_kwargs(self):
        """Test binding with additional kwargs"""
        with patch('structlog.contextvars.bind_contextvars') as mock_bind:
            bind_payment_context(
                operation="webhook",
                event_type="subscription_created",
                correlation_id="pay_abc123"
            )

            mock_bind.assert_called_once()
            call_args = mock_bind.call_args[1]
            assert call_args["event_type"] == "subscription_created"
            assert call_args["correlation_id"] == "pay_abc123"


class TestLogPaymentOperation:
    """Test payment operation logging helper"""

    def test_logs_with_correct_level(self):
        """Test that correct log level is used"""
        mock_logger = Mock()
        mock_logger.info = Mock()

        log_payment_operation(
            mock_logger,
            "info",
            "Test message",
            operation="checkout"
        )

        mock_logger.info.assert_called_once()

    def test_logs_with_context(self):
        """Test that context is included in log"""
        mock_logger = Mock()
        mock_logger.info = Mock()

        log_payment_operation(
            mock_logger,
            "info",
            "Test message",
            operation="checkout",
            user_id="user_123",
            amount=2999
        )

        call_args = mock_logger.info.call_args
        assert "Test message" in call_args[0]
        assert call_args[1]["operation"] == "checkout"
        assert call_args[1]["user_id"] == "user_123"

    def test_supports_all_log_levels(self):
        """Test that all log levels work"""
        mock_logger = Mock()
        mock_logger.info = Mock()
        mock_logger.warning = Mock()
        mock_logger.error = Mock()
        mock_logger.debug = Mock()

        for level in ["info", "warning", "error", "debug"]:
            log_payment_operation(
                mock_logger,
                level,
                f"Test {level}",
                operation="test"
            )

        mock_logger.info.assert_called_once()
        mock_logger.warning.assert_called_once()
        mock_logger.error.assert_called_once()
        mock_logger.debug.assert_called_once()


class TestLogPaymentTiming:
    """Test payment timing context manager"""

    def test_logs_start_and_completion(self):
        """Test that start and completion are logged"""
        mock_logger = Mock()
        mock_logger.debug = Mock()
        mock_logger.info = Mock()

        with log_payment_timing(
            mock_logger,
            "checkout",
            "Test operation"
        ):
            pass

        # Should log debug for start, info for completion
        assert mock_logger.debug.called
        assert mock_logger.info.called

    def test_includes_duration(self):
        """Test that duration is included in completion log"""
        mock_logger = Mock()
        mock_logger.debug = Mock()
        mock_logger.info = Mock()

        with log_payment_timing(
            mock_logger,
            "checkout",
            "Test operation"
        ):
            time.sleep(0.01)  # Small delay

        # Check completion log includes duration_ms
        call_args = mock_logger.info.call_args[1]
        assert "duration_ms" in call_args
        assert call_args["duration_ms"] > 0

    def test_context_can_be_updated(self):
        """Test that execution context can be updated"""
        mock_logger = Mock()
        mock_logger.debug = Mock()
        mock_logger.info = Mock()

        with log_payment_timing(
            mock_logger,
            "checkout",
            "Test operation"
        ) as ctx:
            ctx["session_id"] = "ses_123"
            ctx["amount"] = 2999

        # Check completion log includes updated context
        call_args = mock_logger.info.call_args[1]
        assert call_args["session_id"] == "ses_123"
        assert call_args["amount"] == 2999

    def test_logs_error_on_exception(self):
        """Test that exceptions are logged as errors"""
        mock_logger = Mock()
        mock_logger.debug = Mock()
        mock_logger.error = Mock()

        with pytest.raises(ValueError):
            with log_payment_timing(
                mock_logger,
                "checkout",
                "Test operation"
            ):
                raise ValueError("Test error")

        # Should log error with exception info
        assert mock_logger.error.called
        call_args = mock_logger.error.call_args[1]
        assert "error" in call_args
        assert "duration_ms" in call_args

    def test_error_includes_duration(self):
        """Test that error log includes duration"""
        mock_logger = Mock()
        mock_logger.debug = Mock()
        mock_logger.error = Mock()

        with pytest.raises(ValueError):
            with log_payment_timing(
                mock_logger,
                "checkout",
                "Test operation"
            ):
                time.sleep(0.01)
                raise ValueError("Test error")

        call_args = mock_logger.error.call_args[1]
        assert call_args["duration_ms"] > 0

    def test_custom_log_level(self):
        """Test using custom log level for success"""
        mock_logger = Mock()
        mock_logger.debug = Mock()
        mock_logger.warning = Mock()

        with log_payment_timing(
            mock_logger,
            "checkout",
            "Test operation",
            level="warning"
        ):
            pass

        # Should use warning level for completion
        assert mock_logger.warning.called


class TestClearPaymentContext:
    """Test clearing payment context"""

    def test_clears_context(self):
        """Test that context variables are cleared"""
        with patch('structlog.contextvars.clear_contextvars') as mock_clear:
            clear_payment_context()

            mock_clear.assert_called_once()


class TestIntegration:
    """Integration tests for logging flow"""

    def test_full_logging_flow(self):
        """Test complete logging flow with context binding and timing"""
        mock_logger = Mock()
        mock_logger.info = Mock()
        mock_logger.debug = Mock()

        # Bind context
        with patch('structlog.contextvars.bind_contextvars') as mock_bind:
            bind_payment_context(
                operation="checkout",
                user_id="user_123"
            )
            mock_bind.assert_called_once()

        # Log with timing
        with log_payment_timing(
            mock_logger,
            "checkout",
            "Creating checkout session",
            variant_id="var_123"
        ) as ctx:
            ctx["session_id"] = "ses_456"

        # Clear context
        with patch('structlog.contextvars.clear_contextvars') as mock_clear:
            clear_payment_context()
            mock_clear.assert_called_once()

    def test_correlation_id_flow(self):
        """Test correlation ID generation and usage"""
        correlation_id = generate_payment_correlation_id()

        assert correlation_id.startswith("pay_")

        # Use in context
        with patch('structlog.contextvars.bind_contextvars') as mock_bind:
            bind_payment_context(
                operation="webhook",
                correlation_id=correlation_id
            )

            call_args = mock_bind.call_args[1]
            assert call_args["correlation_id"] == correlation_id
