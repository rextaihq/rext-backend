"""
Tests for Webhook Security Monitor

Tests the webhook signature verification failure tracking and alerting system.
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest


class AsyncIterator:
    def __init__(self, items):
        self.items = items

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.items:
            raise StopAsyncIteration
        return self.items.pop(0)


from src.services.webhook_security_monitor import (  # noqa: E402 -- intentional: avoids a circular import
    WebhookFailureRecord,
    WebhookSecurityMonitor,
)


@pytest.fixture
def monitor():
    """Create a fresh WebhookSecurityMonitor instance for each test"""
    return WebhookSecurityMonitor()


@pytest.fixture
def mock_redis():
    """Mock Redis client for testing"""
    with patch("src.services.webhook_security_monitor.cache") as mock_cache:
        # We use a regular MagicMock for the client because we need to
        # specifically control which methods are async and which aren't.
        mock_redis_client = MagicMock()

        # Async methods
        mock_redis_client.zadd = AsyncMock()
        mock_redis_client.zremrangebyscore = AsyncMock()
        mock_redis_client.expire = AsyncMock()
        mock_redis_client.zcount = AsyncMock()
        mock_redis_client.get = AsyncMock()
        mock_redis_client.set = AsyncMock()
        mock_redis_client.delete = AsyncMock()
        mock_redis_client.execute = AsyncMock()

        # Pipeline mock
        mock_pipe = MagicMock()
        mock_pipe.zadd = MagicMock()
        mock_pipe.zremrangebyscore = MagicMock()
        mock_pipe.expire = MagicMock()
        mock_pipe.zcount = MagicMock()
        mock_pipe.execute = AsyncMock()
        mock_redis_client.pipeline.return_value = mock_pipe

        # scan_iter is NOT a coroutine, it returns an async iterator
        mock_redis_client.scan_iter = MagicMock()

        # Default return values
        mock_redis_client.zcount.return_value = 0
        mock_redis_client.get.return_value = None
        mock_pipe.execute.return_value = [None, None, None, 0]

        mock_cache.redis = mock_redis_client
        yield mock_redis_client


class TestWebhookFailureRecording:
    """Test failure recording functionality"""

    @pytest.mark.asyncio
    async def test_record_single_failure(self, monitor, mock_redis):
        """Test recording a single verification failure"""
        mock_redis.pipeline.return_value.execute.return_value = [None, None, None, 1]
        mock_redis.zcount.return_value = 1

        await monitor.record_verification_failure(
            ip_address="192.168.1.100",
            event_type="subscription_created",
            signature_prefix="abc12345",
            payload_size=1024,
        )

        stats = await monitor.get_failure_stats("192.168.1.100")
        assert stats["failure_count"] == 1
        assert stats["ip_address"] == "192.168.1.100"

    @pytest.mark.asyncio
    async def test_record_multiple_failures_same_ip(self, monitor, mock_redis):
        """Test recording multiple failures from same IP"""
        mock_redis.pipeline.return_value.execute.return_value = [None, None, None, 3]
        mock_redis.zcount.return_value = 3

        for i in range(3):
            await monitor.record_verification_failure(
                ip_address="192.168.1.100", event_type="subscription_created"
            )

        stats = await monitor.get_failure_stats("192.168.1.100")
        assert stats["failure_count"] == 3

    @pytest.mark.asyncio
    async def test_record_failures_different_ips(self, monitor, mock_redis):
        """Test recording failures from different IPs"""
        mock_redis.zcount.return_value = 1
        mock_redis.pipeline.return_value.execute.return_value = [None, None, None, 1]

        # We need a way to mock scan_iter for overall stats
        mock_redis.scan_iter.side_effect = lambda *args, **kwargs: AsyncIterator(
            [
                "webhook_security:failures:192.168.1.100",
                "webhook_security:failures:192.168.1.101",
                "webhook_security:failures:192.168.1.102",
            ]
        )

        await monitor.record_verification_failure(ip_address="192.168.1.100")
        await monitor.record_verification_failure(ip_address="192.168.1.101")
        await monitor.record_verification_failure(ip_address="192.168.1.102")

        # Reset scan_iter for the stats call
        mock_redis.scan_iter.side_effect = lambda *args, **kwargs: AsyncIterator(
            [
                "webhook_security:failures:192.168.1.100",
                "webhook_security:failures:192.168.1.101",
                "webhook_security:failures:192.168.1.102",
            ]
        )

        overall_stats = await monitor.get_failure_stats()
        assert overall_stats["total_ips_with_failures"] == 3
        assert overall_stats["total_failures_in_window"] == 3


class TestTimeWindowCleanup:
    """Test time window and cleanup functionality"""

    @pytest.mark.asyncio
    async def test_old_failures_cleaned_up(self, monitor, mock_redis):
        """Test that failures outside time window are removed"""
        # Redis handles cleanup inline with zremrangebyscore
        mock_redis.pipeline.return_value.execute.return_value = [None, None, None, 1]
        mock_redis.zcount.return_value = 1

        await monitor.record_verification_failure(ip_address="192.168.1.100")

        # In Redis implementation, cleanup is automatic during record
        stats = await monitor.get_failure_stats("192.168.1.100")
        assert stats["failure_count"] == 1

    @pytest.mark.asyncio
    async def test_ip_removed_when_no_recent_failures(self, monitor, mock_redis):
        """Test that IP stats return 0 when no recent failures"""
        mock_redis.zcount.return_value = 0

        # IP should return 0 failures
        stats = await monitor.get_failure_stats("192.168.1.100")
        assert stats["failure_count"] == 0


class TestAlertThreshold:
    """Test alerting threshold and cooldown logic"""

    @pytest.mark.asyncio
    async def test_should_not_alert_below_threshold(self, monitor, mock_redis):
        """Test that alerts are not triggered below threshold"""
        mock_redis.zcount.return_value = 4
        mock_redis.get.return_value = None

        assert not await monitor.should_alert("192.168.1.100")

    @pytest.mark.asyncio
    @patch("src.services.webhook_security_monitor.logger")
    @patch("src.services.webhook_security_monitor.sentry_sdk")
    async def test_should_alert_at_threshold(self, mock_sentry, mock_logger, monitor, mock_redis):
        """Test that alerts are triggered at threshold"""
        mock_redis.zcount.return_value = 5
        mock_redis.get.return_value = None
        mock_redis.pipeline.return_value.execute.return_value = [None, None, None, 5]

        await monitor.record_verification_failure(ip_address="192.168.1.100")

        assert mock_logger.critical.called

    @pytest.mark.asyncio
    @patch("src.services.webhook_security_monitor.logger")
    @patch("src.services.webhook_security_monitor.sentry_sdk")
    async def test_should_alert_above_threshold(
        self, mock_sentry, mock_logger, monitor, mock_redis
    ):
        """Test that alerts are triggered above threshold"""
        mock_redis.zcount.return_value = 10
        mock_redis.get.return_value = None
        mock_redis.pipeline.return_value.execute.return_value = [None, None, None, 10]

        await monitor.record_verification_failure(ip_address="192.168.1.100")

        assert mock_logger.critical.called

    @pytest.mark.asyncio
    @patch("src.services.webhook_security_monitor.logger")
    @patch("src.services.webhook_security_monitor.sentry_sdk")
    async def test_alert_cooldown_prevents_spam(
        self, mock_sentry, mock_logger, monitor, mock_redis
    ):
        """Test that alert cooldown prevents repeated alerts"""
        mock_redis.zcount.return_value = 5
        mock_redis.get.return_value = "1"  # CD active

        assert not await monitor.should_alert("192.168.1.100")

    @pytest.mark.asyncio
    @patch("src.services.webhook_security_monitor.logger")
    @patch("src.services.webhook_security_monitor.sentry_sdk")
    async def test_alert_after_cooldown_expires(
        self, mock_sentry, mock_logger, monitor, mock_redis
    ):
        """Test that alerts can be sent again after cooldown"""
        mock_redis.zcount.return_value = 5
        mock_redis.get.return_value = None  # CD expired

        assert await monitor.should_alert("192.168.1.100")


class TestSecurityAlert:
    """Test security alert generation"""

    @pytest.mark.asyncio
    @patch("src.services.webhook_security_monitor.logger")
    @patch("src.services.webhook_security_monitor.sentry_sdk")
    async def test_alert_sent_at_threshold(self, mock_sentry, mock_logger, monitor, mock_redis):
        """Test that alert is sent when threshold reached"""
        mock_redis.pipeline.return_value.execute.return_value = [None, None, None, 5]
        mock_redis.get.return_value = None
        mock_redis.zcount.return_value = 5

        await monitor.record_verification_failure(ip_address="192.168.1.100")

        # Verify logger.critical was called
        mock_logger.critical.assert_called()
        call_args = mock_logger.critical.call_args[0][0]
        assert "SECURITY ALERT" in call_args
        assert "192.168.1.100" in call_args

    @pytest.mark.asyncio
    @patch("src.services.webhook_security_monitor.logger")
    @patch("src.services.webhook_security_monitor.sentry_sdk")
    async def test_alert_includes_failure_details(
        self, mock_sentry, mock_logger, monitor, mock_redis
    ):
        """Test that alert includes detailed failure information"""
        mock_redis.pipeline.return_value.execute.return_value = [None, None, None, 5]
        mock_redis.get.return_value = None
        mock_redis.zcount.return_value = 5

        await monitor.record_verification_failure(
            ip_address="192.168.1.100",
            event_type="subscription_created",
            signature_prefix="abc12345",
        )

        # Check logger was called with extra context
        assert mock_logger.critical.called
        call_kwargs = mock_logger.critical.call_args[1]
        extra = call_kwargs.get("extra", {})

        assert extra["ip_address"] == "192.168.1.100"
        assert extra["failure_count"] == 5

    @pytest.mark.asyncio
    @patch("src.services.webhook_security_monitor.logger")
    @patch("src.services.webhook_security_monitor.sentry_sdk")
    async def test_sentry_alert_sent(self, mock_sentry, mock_logger, monitor, mock_redis):
        """Test that Sentry alert is sent with proper context"""
        mock_redis.pipeline.return_value.execute.return_value = [None, None, None, 5]
        mock_redis.get.return_value = None
        mock_redis.zcount.return_value = 5

        await monitor.record_verification_failure(ip_address="192.168.1.100")

        # Verify Sentry capture_message was called
        mock_sentry.capture_message.assert_called_once()
        call_args = mock_sentry.capture_message.call_args[0][0]
        assert "Webhook Security Alert" in call_args
        assert "192.168.1.100" in call_args


class TestFailureStats:
    """Test failure statistics retrieval"""

    @pytest.mark.asyncio
    async def test_stats_for_specific_ip(self, monitor, mock_redis):
        """Test getting stats for specific IP"""
        mock_redis.zcount.return_value = 2

        stats = await monitor.get_failure_stats("192.168.1.100")

        assert stats["ip_address"] == "192.168.1.100"
        assert stats["failure_count"] == 2
        assert stats["time_window_minutes"] == 5

    @pytest.mark.asyncio
    async def test_stats_for_nonexistent_ip(self, monitor, mock_redis):
        """Test getting stats for IP with no failures"""
        mock_redis.zcount.return_value = 0
        stats = await monitor.get_failure_stats("192.168.1.999")

        assert stats["failure_count"] == 0

    @pytest.mark.asyncio
    async def test_overall_stats(self, monitor, mock_redis):
        """Test getting overall failure statistics"""
        mock_redis.zcount.return_value = 1
        mock_redis.scan_iter.side_effect = lambda *args, **kwargs: AsyncIterator(
            ["webhook_security:failures:192.168.1.100", "webhook_security:failures:192.168.1.101"]
        )

        stats = await monitor.get_failure_stats()

        assert stats["total_ips_with_failures"] == 2
        assert stats["total_failures_in_window"] == 2
        assert "192.168.1.100" in stats["ips"]
        assert "192.168.1.101" in stats["ips"]


class TestClearFailures:
    """Test manual failure clearing"""

    @pytest.mark.asyncio
    async def test_clear_failures_for_ip(self, monitor, mock_redis):
        """Test clearing failures for specific IP"""
        mock_redis.pipeline.return_value.execute = AsyncMock()
        mock_redis.zcount.return_value = 0

        # Clear failures
        await monitor.clear_failures("192.168.1.100")

        # Should have no failures
        stats = await monitor.get_failure_stats("192.168.1.100")
        assert stats["failure_count"] == 0

    @pytest.mark.asyncio
    async def test_clear_nonexistent_ip(self, monitor, mock_redis):
        """Test clearing failures for IP with no failures (should not error)"""
        # Should not raise exception
        await monitor.clear_failures("192.168.1.999")


class TestConcurrentFailures:
    """Test handling of concurrent failure scenarios"""

    @pytest.mark.asyncio
    async def test_rapid_failures_from_same_ip(self, monitor, mock_redis):
        """Test handling rapid consecutive failures from same IP"""
        mock_redis.pipeline.return_value.execute.return_value = [None, None, None, 20]
        mock_redis.get.return_value = None
        mock_redis.zcount.return_value = 20

        # Simulate rapid attack
        for i in range(20):
            await monitor.record_verification_failure(ip_address="192.168.1.100")

        stats = await monitor.get_failure_stats("192.168.1.100")
        assert stats["failure_count"] == 20

    @pytest.mark.asyncio
    async def test_failures_from_multiple_ips_simultaneously(self, monitor, mock_redis):
        """Test tracking failures from multiple IPs at once"""
        mock_redis.scan_iter.side_effect = lambda *args, **kwargs: AsyncIterator(
            [f"webhook_security:failures:192.168.1.{i}" for i in range(1, 11)]
        )
        mock_redis.zcount.return_value = 3

        overall_stats = await monitor.get_failure_stats()
        assert overall_stats["total_ips_with_failures"] == 10
        assert overall_stats["total_failures_in_window"] == 30
