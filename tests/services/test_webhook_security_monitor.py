"""
Tests for Webhook Security Monitor

Tests the webhook signature verification failure tracking and alerting system.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

from src.services.webhook_security_monitor import (
    WebhookSecurityMonitor,
    WebhookFailureRecord
)


@pytest.fixture
def monitor():
    """Create a fresh WebhookSecurityMonitor instance for each test"""
    return WebhookSecurityMonitor()


class TestWebhookFailureRecording:
    """Test failure recording functionality"""

    def test_record_single_failure(self, monitor):
        """Test recording a single verification failure"""
        monitor.record_verification_failure(
            ip_address="192.168.1.100",
            event_type="subscription_created",
            signature_prefix="abc12345",
            payload_size=1024
        )

        stats = monitor.get_failure_stats("192.168.1.100")
        assert stats["failure_count"] == 1
        assert stats["ip_address"] == "192.168.1.100"

    def test_record_multiple_failures_same_ip(self, monitor):
        """Test recording multiple failures from same IP"""
        for i in range(3):
            monitor.record_verification_failure(
                ip_address="192.168.1.100",
                event_type="subscription_created"
            )

        stats = monitor.get_failure_stats("192.168.1.100")
        assert stats["failure_count"] == 3

    def test_record_failures_different_ips(self, monitor):
        """Test recording failures from different IPs"""
        monitor.record_verification_failure(ip_address="192.168.1.100")
        monitor.record_verification_failure(ip_address="192.168.1.101")
        monitor.record_verification_failure(ip_address="192.168.1.102")

        overall_stats = monitor.get_failure_stats()
        assert overall_stats["total_ips_with_failures"] == 3
        assert overall_stats["total_failures_in_window"] == 3


class TestTimeWindowCleanup:
    """Test time window and cleanup functionality"""

    def test_old_failures_cleaned_up(self, monitor):
        """Test that failures outside time window are removed"""
        # Record a failure
        monitor.record_verification_failure(ip_address="192.168.1.100")

        # Manually set timestamp to old value (simulate time passing)
        old_time = datetime.now(timezone.utc) - timedelta(minutes=10)  # Older than 5min window
        monitor._failures["192.168.1.100"][0] = WebhookFailureRecord(
            timestamp=old_time,
            ip_address="192.168.1.100",
            event_type=None,
            signature_prefix="",
            payload_size=0
        )

        # Record new failure (triggers cleanup)
        monitor.record_verification_failure(ip_address="192.168.1.100")

        # Should only have 1 recent failure
        stats = monitor.get_failure_stats("192.168.1.100")
        assert stats["failure_count"] == 1

    def test_ip_removed_when_no_recent_failures(self, monitor):
        """Test that IP is removed from tracking when no recent failures"""
        # Record a failure
        monitor.record_verification_failure(ip_address="192.168.1.100")

        # Set to old timestamp
        old_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        monitor._failures["192.168.1.100"][0] = WebhookFailureRecord(
            timestamp=old_time,
            ip_address="192.168.1.100",
            event_type=None,
            signature_prefix="",
            payload_size=0
        )

        # Cleanup
        monitor._cleanup_old_failures("192.168.1.100")

        # IP should be removed entirely
        assert "192.168.1.100" not in monitor._failures


class TestAlertThreshold:
    """Test alerting threshold and cooldown logic"""

    def test_should_not_alert_below_threshold(self, monitor):
        """Test that alerts are not triggered below threshold"""
        # Record failures below threshold (5)
        for i in range(4):
            monitor.record_verification_failure(ip_address="192.168.1.100")

        assert not monitor.should_alert("192.168.1.100")

    @patch("src.services.webhook_security_monitor.logger")
    @patch("src.services.webhook_security_monitor.sentry_sdk")
    def test_should_alert_at_threshold(self, mock_sentry, mock_logger, monitor):
        """Test that alerts are triggered at threshold"""
        # Record exactly threshold number of failures (5)
        # The 5th failure will trigger the alert
        for i in range(5):
            monitor.record_verification_failure(ip_address="192.168.1.100")

        # Verify alert was triggered (logger.critical called)
        assert mock_logger.critical.called

    @patch("src.services.webhook_security_monitor.logger")
    @patch("src.services.webhook_security_monitor.sentry_sdk")
    def test_should_alert_above_threshold(self, mock_sentry, mock_logger, monitor):
        """Test that alerts are triggered above threshold"""
        # Record more than threshold
        for i in range(10):
            monitor.record_verification_failure(ip_address="192.168.1.100")

        # Verify alert was triggered
        assert mock_logger.critical.called

    @patch("src.services.webhook_security_monitor.logger")
    @patch("src.services.webhook_security_monitor.sentry_sdk")
    def test_alert_cooldown_prevents_spam(self, mock_sentry, mock_logger, monitor):
        """Test that alert cooldown prevents repeated alerts"""
        # Trigger first alert
        for i in range(5):
            monitor.record_verification_failure(ip_address="192.168.1.100")

        # Should not alert again immediately
        assert not monitor.should_alert("192.168.1.100")

    @patch("src.services.webhook_security_monitor.logger")
    @patch("src.services.webhook_security_monitor.sentry_sdk")
    def test_alert_after_cooldown_expires(self, mock_sentry, mock_logger, monitor):
        """Test that alerts can be sent again after cooldown"""
        # Trigger first alert
        for i in range(5):
            monitor.record_verification_failure(ip_address="192.168.1.100")

        # Manually set last alert time to past (simulate cooldown expiry)
        old_time = datetime.now(timezone.utc) - timedelta(minutes=20)  # Beyond 15min cooldown
        monitor._last_alert["192.168.1.100"] = old_time

        # Should be able to alert again
        assert monitor.should_alert("192.168.1.100")


class TestSecurityAlert:
    """Test security alert generation"""

    @patch("src.services.webhook_security_monitor.logger")
    @patch("src.services.webhook_security_monitor.sentry_sdk")
    def test_alert_sent_at_threshold(self, mock_sentry, mock_logger, monitor):
        """Test that alert is sent when threshold reached"""
        # Record threshold failures
        for i in range(5):
            monitor.record_verification_failure(ip_address="192.168.1.100")

        # Verify logger.critical was called
        mock_logger.critical.assert_called()
        call_args = mock_logger.critical.call_args[0][0]
        assert "SECURITY ALERT" in call_args
        assert "192.168.1.100" in call_args

    @patch("src.services.webhook_security_monitor.logger")
    @patch("src.services.webhook_security_monitor.sentry_sdk")
    def test_alert_includes_failure_details(self, mock_sentry, mock_logger, monitor):
        """Test that alert includes detailed failure information"""
        # Record failures with various event types
        monitor.record_verification_failure(
            ip_address="192.168.1.100",
            event_type="subscription_created",
            signature_prefix="abc12345"
        )
        monitor.record_verification_failure(
            ip_address="192.168.1.100",
            event_type="subscription_updated",
            signature_prefix="def67890"
        )
        for i in range(3):
            monitor.record_verification_failure(ip_address="192.168.1.100")

        # Check logger was called with extra context
        assert mock_logger.critical.called
        call_kwargs = mock_logger.critical.call_args[1]
        extra = call_kwargs.get("extra", {})

        assert extra["ip_address"] == "192.168.1.100"
        assert extra["failure_count"] == 5
        assert "event_types" in extra
        assert "signature_prefixes" in extra

    @patch("src.services.webhook_security_monitor.logger")
    @patch("src.services.webhook_security_monitor.sentry_sdk")
    def test_sentry_alert_sent(self, mock_sentry, mock_logger, monitor):
        """Test that Sentry alert is sent with proper context"""
        # Record threshold failures
        for i in range(5):
            monitor.record_verification_failure(ip_address="192.168.1.100")

        # Verify Sentry capture_message was called
        mock_sentry.capture_message.assert_called_once()
        call_args = mock_sentry.capture_message.call_args[0][0]
        assert "Webhook Security Alert" in call_args
        assert "192.168.1.100" in call_args


class TestFailureStats:
    """Test failure statistics retrieval"""

    def test_stats_for_specific_ip(self, monitor):
        """Test getting stats for specific IP"""
        monitor.record_verification_failure(ip_address="192.168.1.100")
        monitor.record_verification_failure(ip_address="192.168.1.100")

        stats = monitor.get_failure_stats("192.168.1.100")

        assert stats["ip_address"] == "192.168.1.100"
        assert stats["failure_count"] == 2
        assert stats["time_window_minutes"] == 5
        assert "first_failure" in stats
        assert "last_failure" in stats

    def test_stats_for_nonexistent_ip(self, monitor):
        """Test getting stats for IP with no failures"""
        stats = monitor.get_failure_stats("192.168.1.999")

        assert stats["failure_count"] == 0
        assert stats["first_failure"] is None
        assert stats["last_failure"] is None

    def test_overall_stats(self, monitor):
        """Test getting overall failure statistics"""
        monitor.record_verification_failure(ip_address="192.168.1.100")
        monitor.record_verification_failure(ip_address="192.168.1.100")
        monitor.record_verification_failure(ip_address="192.168.1.101")

        stats = monitor.get_failure_stats()

        assert stats["total_ips_with_failures"] == 2
        assert stats["total_failures_in_window"] == 3
        assert "192.168.1.100" in stats["ips"]
        assert "192.168.1.101" in stats["ips"]


class TestClearFailures:
    """Test manual failure clearing"""

    def test_clear_failures_for_ip(self, monitor):
        """Test clearing failures for specific IP"""
        # Record some failures
        for i in range(3):
            monitor.record_verification_failure(ip_address="192.168.1.100")

        # Clear failures
        monitor.clear_failures("192.168.1.100")

        # Should have no failures
        stats = monitor.get_failure_stats("192.168.1.100")
        assert stats["failure_count"] == 0

    def test_clear_failures_removes_from_tracking(self, monitor):
        """Test that clearing removes IP from internal tracking"""
        monitor.record_verification_failure(ip_address="192.168.1.100")
        monitor.clear_failures("192.168.1.100")

        assert "192.168.1.100" not in monitor._failures
        assert "192.168.1.100" not in monitor._last_alert

    def test_clear_nonexistent_ip(self, monitor):
        """Test clearing failures for IP with no failures (should not error)"""
        # Should not raise exception
        monitor.clear_failures("192.168.1.999")


class TestConcurrentFailures:
    """Test handling of concurrent failure scenarios"""

    def test_rapid_failures_from_same_ip(self, monitor):
        """Test handling rapid consecutive failures from same IP"""
        # Simulate rapid attack
        for i in range(20):
            monitor.record_verification_failure(ip_address="192.168.1.100")

        stats = monitor.get_failure_stats("192.168.1.100")
        assert stats["failure_count"] == 20

    def test_failures_from_multiple_ips_simultaneously(self, monitor):
        """Test tracking failures from multiple IPs at once"""
        ips = [f"192.168.1.{i}" for i in range(1, 11)]

        for ip in ips:
            for _ in range(3):
                monitor.record_verification_failure(ip_address=ip)

        overall_stats = monitor.get_failure_stats()
        assert overall_stats["total_ips_with_failures"] == 10
        assert overall_stats["total_failures_in_window"] == 30
