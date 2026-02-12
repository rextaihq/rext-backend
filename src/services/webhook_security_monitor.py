"""
Webhook Security Monitoring Service

Tracks webhook verification failures and generates security alerts for potential attacks.

This service monitors webhook signature verification failures and:
1. Tracks failure counts by IP address and time window
2. Detects potential attacks (multiple failures in short time)
3. Generates security alerts via logging and Sentry
4. Provides security metrics for monitoring

Usage:
    from src.services.webhook_security_monitor import webhook_security_monitor

    # Record failure
    webhook_security_monitor.record_verification_failure(
        ip_address="192.168.1.100",
        event_type="subscription_created",
        signature_prefix="abc123"
    )

    # Check if should alert
    if webhook_security_monitor.should_alert(ip_address):
        # Send alert to security team
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from collections import defaultdict, deque
from dataclasses import dataclass
import sentry_sdk

from src.utils.logger import logger


@dataclass
class WebhookFailureRecord:
    """Record of a webhook verification failure"""
    timestamp: datetime
    ip_address: str
    event_type: Optional[str]
    signature_prefix: str
    payload_size: int


class WebhookSecurityMonitor:
    """
    Monitors webhook security and detects potential attacks.

    Tracks verification failures and generates alerts when suspicious
    patterns are detected (e.g., multiple failures from same IP).
    """

    # Alert thresholds
    FAILURE_THRESHOLD = 5  # Number of failures before alerting
    TIME_WINDOW_MINUTES = 5  # Time window for counting failures
    ALERT_COOLDOWN_MINUTES = 15  # Minimum time between alerts for same IP

    def __init__(self):
        """Initialize security monitor"""
        # Storage: {ip_address: deque of WebhookFailureRecord}
        self._failures: Dict[str, deque] = defaultdict(deque)

        # Track when we last alerted for each IP (prevent spam)
        self._last_alert: Dict[str, datetime] = {}

        logger.info("WebhookSecurityMonitor initialized")

    def record_verification_failure(
        self,
        ip_address: str,
        event_type: Optional[str] = None,
        signature_prefix: str = "",
        payload_size: int = 0
    ) -> None:
        """
        Record a webhook signature verification failure.

        Args:
            ip_address: IP address of the request
            event_type: Type of webhook event (if parseable)
            signature_prefix: First 8 chars of received signature
            payload_size: Size of payload in bytes
        """
        record = WebhookFailureRecord(
            timestamp=datetime.now(timezone.utc),
            ip_address=ip_address,
            event_type=event_type,
            signature_prefix=signature_prefix,
            payload_size=payload_size
        )

        # Add to failure tracking
        self._failures[ip_address].append(record)

        # Clean up old failures (outside time window)
        self._cleanup_old_failures(ip_address)

        # Check if we should alert
        failure_count = len(self._failures[ip_address])

        logger.info(
            f"Webhook verification failure recorded",
            extra={
                "event": "verification_failure_recorded",
                "ip_address": ip_address,
                "event_type": event_type,
                "failure_count_in_window": failure_count,
                "time_window_minutes": self.TIME_WINDOW_MINUTES
            }
        )

        # Alert if threshold exceeded and not in cooldown
        if self.should_alert(ip_address):
            self._send_security_alert(ip_address, failure_count)

    def _cleanup_old_failures(self, ip_address: str) -> None:
        """
        Remove failures outside the time window.

        Args:
            ip_address: IP address to clean up failures for
        """
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=self.TIME_WINDOW_MINUTES)
        failures = self._failures[ip_address]

        while failures and failures[0].timestamp < cutoff:
            failures.popleft()

        # Remove IP entirely if no recent failures
        if not failures:
            del self._failures[ip_address]

    def should_alert(self, ip_address: str) -> bool:
        """
        Check if we should send a security alert for this IP.

        Args:
            ip_address: IP address to check

        Returns:
            True if should alert, False otherwise
        """
        # Check if enough failures
        failure_count = len(self._failures.get(ip_address, []))
        if failure_count < self.FAILURE_THRESHOLD:
            return False

        # Check alert cooldown
        last_alert = self._last_alert.get(ip_address)
        if last_alert:
            cooldown_end = last_alert + timedelta(minutes=self.ALERT_COOLDOWN_MINUTES)
            if datetime.now(timezone.utc) < cooldown_end:
                return False  # Still in cooldown

        return True

    def _send_security_alert(self, ip_address: str, failure_count: int) -> None:
        """
        Send security alert for suspicious webhook activity.

        Args:
            ip_address: IP address with suspicious activity
            failure_count: Number of failures in time window
        """
        failures = list(self._failures[ip_address])

        # Build alert message
        alert_message = (
            f"SECURITY ALERT: Multiple webhook verification failures detected\n"
            f"IP Address: {ip_address}\n"
            f"Failures in last {self.TIME_WINDOW_MINUTES} minutes: {failure_count}\n"
            f"Threshold: {self.FAILURE_THRESHOLD}\n"
            f"This may indicate:\n"
            f"  - Attempted webhook spoofing attack\n"
            f"  - Misconfigured webhook sender\n"
            f"  - Invalid webhook secret\n"
            f"Action: Monitor and consider blocking IP if attacks persist"
        )

        # Log critical security event
        logger.critical(
            alert_message,
            extra={
                "event": "webhook_security_alert",
                "severity": "CRITICAL",
                "ip_address": ip_address,
                "failure_count": failure_count,
                "time_window_minutes": self.TIME_WINDOW_MINUTES,
                "first_failure": failures[0].timestamp.isoformat(),
                "last_failure": failures[-1].timestamp.isoformat(),
                "event_types": [f.event_type for f in failures if f.event_type],
                "signature_prefixes": [f.signature_prefix for f in failures]
            }
        )

        # Send to Sentry for alerting
        with sentry_sdk.push_scope() as scope:
            scope.set_context("webhook_security", {
                "ip_address": ip_address,
                "failure_count": failure_count,
                "time_window_minutes": self.TIME_WINDOW_MINUTES,
                "threshold": self.FAILURE_THRESHOLD,
                "first_failure": failures[0].timestamp.isoformat(),
                "last_failure": failures[-1].timestamp.isoformat(),
            })

            scope.set_tag("security_event", "webhook_verification_failures")
            scope.set_tag("ip_address", ip_address)
            scope.level = "error"

            sentry_sdk.capture_message(
                f"Webhook Security Alert: {failure_count} verification failures from {ip_address}",
                level="error"
            )

        # Update last alert time
        self._last_alert[ip_address] = datetime.now(timezone.utc)

        logger.info(
            f"Security alert sent for IP {ip_address}. Alert cooldown: {self.ALERT_COOLDOWN_MINUTES} minutes",
            extra={"event": "security_alert_sent", "ip_address": ip_address}
        )

    def get_failure_stats(self, ip_address: Optional[str] = None) -> Dict:
        """
        Get failure statistics for monitoring.

        Args:
            ip_address: Optional IP to get stats for. If None, returns overall stats.

        Returns:
            Dictionary with failure statistics
        """
        if ip_address:
            failures = list(self._failures.get(ip_address, []))
            return {
                "ip_address": ip_address,
                "failure_count": len(failures),
                "time_window_minutes": self.TIME_WINDOW_MINUTES,
                "first_failure": failures[0].timestamp.isoformat() if failures else None,
                "last_failure": failures[-1].timestamp.isoformat() if failures else None,
            }
        else:
            # Overall stats
            total_failures = sum(len(failures) for failures in self._failures.values())
            return {
                "total_ips_with_failures": len(self._failures),
                "total_failures_in_window": total_failures,
                "time_window_minutes": self.TIME_WINDOW_MINUTES,
                "threshold": self.FAILURE_THRESHOLD,
                "ips": list(self._failures.keys())
            }

    def clear_failures(self, ip_address: str) -> None:
        """
        Clear failure records for an IP address (manual reset).

        Args:
            ip_address: IP address to clear failures for
        """
        if ip_address in self._failures:
            del self._failures[ip_address]

        if ip_address in self._last_alert:
            del self._last_alert[ip_address]

        logger.info(
            f"Cleared webhook verification failures for IP {ip_address}",
            extra={"event": "failures_cleared", "ip_address": ip_address}
        )


# Global singleton instance
webhook_security_monitor = WebhookSecurityMonitor()
