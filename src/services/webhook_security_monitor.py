"""
Webhook Security Monitoring Service

Tracks webhook verification failures and generates security alerts for potential attacks.
Uses Redis for persistent, cross-worker failure tracking.
"""

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import sentry_sdk

from src.utils.logger import logger
from src.api.cache.redis_client import cache


@dataclass
class WebhookFailureRecord:
    """Record of a failed webhook signature verification."""
    timestamp: datetime
    ip_address: str
    event_type: Optional[str] = None
    signature_prefix: str = ""
    payload_size: int = 0

    def to_dict(self) -> Dict:
        return asdict(self)


class WebhookSecurityMonitor:
    """
    Monitors and alerts on webhook security events (e.g., signature failures).
    Uses Redis for persistent tracking across worker processes.
    """

    def __init__(self):
        """Initialize security monitor with Redis-backed storage."""
        self.FAILURE_THRESHOLD = 5  # failures per IP
        self.TIME_WINDOW_MINUTES = 5  # tracking window
        self.ALERT_COOLDOWN_MINUTES = 15  # alert suppression window

        self.REDIS_KEY_PREFIX = "webhook_security:"
        self.FAILURE_KEY_PREFIX = f"{self.REDIS_KEY_PREFIX}failures:"
        self.ALERT_KEY_PREFIX = f"{self.REDIS_KEY_PREFIX}last_alert:"

        logger.info("WebhookSecurityMonitor initialized (Redis-backed)")

    async def record_verification_failure(
        self,
        ip_address: str,
        event_type: Optional[str] = None,
        signature_prefix: str = "",
        payload_size: int = 0
    ) -> None:
        """
        Record a webhook signature verification failure in Redis.

        Uses a Redis sorted set with timestamps as scores for sliding window counting.
        """
        now_ts = time.time()
        record_data = json.dumps({
            "ip_address": ip_address,
            "event_type": event_type,
            "signature_prefix": signature_prefix,
            "payload_size": payload_size,
            "timestamp": now_ts
        })

        redis_key = f"{self.FAILURE_KEY_PREFIX}{ip_address}"
        window_seconds = self.TIME_WINDOW_MINUTES * 60

        try:
            redis = cache.redis
            if redis is not None:
                pipe = redis.pipeline()
                # Add failure record with timestamp as score
                pipe.zadd(redis_key, {record_data: now_ts})
                # Remove entries outside the time window
                pipe.zremrangebyscore(redis_key, 0, now_ts - window_seconds)
                # Set TTL to auto-cleanup (window + buffer)
                pipe.expire(redis_key, window_seconds + 60)
                # Count failures in window
                pipe.zcount(redis_key, now_ts - window_seconds, "+inf")
                results = await pipe.execute()
                failure_count = results[3]
            else:
                # Fallback: log warning, no tracking
                logger.warning(
                    "Redis unavailable for webhook security monitoring — failure not tracked",
                    extra={"ip_address": ip_address}
                )
                return
        except Exception as e:
            logger.error(
                f"Failed to record webhook failure in Redis: {e}",
                extra={"ip_address": ip_address}
            )
            return

        logger.info(
            "Webhook verification failure recorded",
            extra={
                "event": "verification_failure_recorded",
                "ip_address": ip_address,
                "event_type": event_type,
                "failure_count_in_window": failure_count,
                "time_window_minutes": self.TIME_WINDOW_MINUTES
            }
        )

        if await self.should_alert(ip_address):
            await self._send_security_alert(ip_address, failure_count)

    async def should_alert(self, ip_address: str) -> bool:
        """
        Check if we should send a security alert for this IP.
        Uses Redis for cross-worker coordination.
        """
        try:
            redis = cache.redis
            if redis is None:
                return False

            now_ts = time.time()
            window_seconds = self.TIME_WINDOW_MINUTES * 60

            # Check failure count
            failure_key = f"{self.FAILURE_KEY_PREFIX}{ip_address}"
            failure_count = await redis.zcount(failure_key, now_ts - window_seconds, "+inf")
            if failure_count < self.FAILURE_THRESHOLD:
                return False

            # Check alert cooldown
            alert_key = f"{self.ALERT_KEY_PREFIX}{ip_address}"
            last_alert = await redis.get(alert_key)
            if last_alert is not None:
                return False  # Still in cooldown

            return True
        except Exception as e:
            logger.error(f"Failed to check alert status in Redis: {e}")
            return False

    async def _send_security_alert(self, ip_address: str, failure_count: int) -> None:
        """
        Send security alert and set cooldown in Redis.
        """
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

        logger.critical(
            alert_message,
            extra={
                "event": "webhook_security_alert",
                "severity": "CRITICAL",
                "ip_address": ip_address,
                "failure_count": failure_count,
                "time_window_minutes": self.TIME_WINDOW_MINUTES,
            }
        )

        with sentry_sdk.push_scope() as scope:
            scope.set_context("webhook_security", {
                "ip_address": ip_address,
                "failure_count": failure_count,
                "time_window_minutes": self.TIME_WINDOW_MINUTES,
                "threshold": self.FAILURE_THRESHOLD,
            })
            scope.set_tag("security_event", "webhook_verification_failures")
            scope.set_tag("ip_address", ip_address)
            scope.level = "error"
            sentry_sdk.capture_message(
                f"Webhook Security Alert: {failure_count} verification failures from {ip_address}",
                level="error"
            )

        # Set alert cooldown in Redis
        try:
            redis = cache.redis
            if redis is not None:
                cooldown_seconds = self.ALERT_COOLDOWN_MINUTES * 60
                alert_key = f"{self.ALERT_KEY_PREFIX}{ip_address}"
                await redis.set(alert_key, "1", ex=cooldown_seconds)
        except Exception as e:
            logger.error(f"Failed to set alert cooldown in Redis: {e}")

        logger.info(
            f"Security alert sent for IP {ip_address}. Alert cooldown: {self.ALERT_COOLDOWN_MINUTES} minutes",
            extra={"event": "security_alert_sent", "ip_address": ip_address}
        )

    async def get_failure_stats(self, ip_address: Optional[str] = None) -> Dict:
        """Get failure statistics from Redis."""
        try:
            redis = cache.redis
            if redis is None:
                return {"error": "Redis unavailable"}

            now_ts = time.time()
            window_seconds = self.TIME_WINDOW_MINUTES * 60

            if ip_address:
                failure_key = f"{self.FAILURE_KEY_PREFIX}{ip_address}"
                failure_count = await redis.zcount(failure_key, now_ts - window_seconds, "+inf")
                return {
                    "ip_address": ip_address,
                    "failure_count": failure_count,
                    "time_window_minutes": self.TIME_WINDOW_MINUTES,
                }
            else:
                # Scan for all failure keys
                keys = []
                async for key in redis.scan_iter(f"{self.FAILURE_KEY_PREFIX}*"):
                    keys.append(key)

                total_failures = 0
                ips = []
                for key in keys:
                    count = await redis.zcount(key, now_ts - window_seconds, "+inf")
                    if count > 0:
                        ip = key.decode() if isinstance(key, bytes) else key
                        ip = ip.replace(self.FAILURE_KEY_PREFIX, "")
                        ips.append(ip)
                        total_failures += count

                return {
                    "total_ips_with_failures": len(ips),
                    "total_failures_in_window": total_failures,
                    "time_window_minutes": self.TIME_WINDOW_MINUTES,
                    "threshold": self.FAILURE_THRESHOLD,
                    "ips": ips
                }
        except Exception as e:
            logger.error(f"Failed to get failure stats from Redis: {e}")
            return {"error": str(e)}

    async def clear_failures(self, ip_address: str) -> None:
        """Clear failure records for an IP address in Redis."""
        try:
            redis = cache.redis
            if redis is not None:
                pipe = redis.pipeline()
                pipe.delete(f"{self.FAILURE_KEY_PREFIX}{ip_address}")
                pipe.delete(f"{self.ALERT_KEY_PREFIX}{ip_address}")
                await pipe.execute()
        except Exception as e:
            logger.error(f"Failed to clear failures in Redis: {e}")

        logger.info(
            f"Cleared webhook verification failures for IP {ip_address}",
            extra={"event": "failures_cleared", "ip_address": ip_address}
        )


# Global instance
webhook_security_monitor = WebhookSecurityMonitor()
