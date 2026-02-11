# Task 126: Webhook Security Monitor Uses In-Memory Storage Only — Data Lost on Restart

## Metadata
- **Task ID:** TASK-126
- **Source:** B5 - Subscription & Billing (Finding #11 under P1 High)
- **Audit Report:** `audit-reports/backend-subscription-billing.md`
- **Priority:** P1 High
- **Category:** security
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The `WebhookSecurityMonitor` class in `rext-backend/src/services/webhook_security_monitor.py` stores all webhook verification failure records exclusively in Python process memory using a `dict` of `deque` objects (line 62) and a `dict` for last-alert timestamps (line 65):

```python
self._failures: Dict[str, deque] = defaultdict(deque)
self._last_alert: Dict[str, datetime] = {}
```

This design has three critical flaws:

1. **Data loss on restart:** Every application restart, deployment, or worker process recycle wipes all tracked failure data. An attacker can trigger a restart (e.g., by causing an OOM condition) and reset all accumulated failure tracking.

2. **Worker isolation in multi-process deployments:** When running Uvicorn with multiple workers (which is standard for production), each worker process has its own independent `WebhookSecurityMonitor` instance. An attacker can distribute malicious requests across workers to stay below the per-worker threshold. With 4 workers and a threshold of 5 failures, an attacker can make 16 failed attempts (4 per worker) without triggering any alert.

3. **No persistence for forensics:** After an attack, there is no historical record of failure patterns for post-incident analysis. The 5-minute time window means data is automatically purged even without restarts.

The project already has Redis configured and available (`redis[hiredis]>=5.0.0` in `pyproject.toml`, `src/api/cache/redis_client.py` provides a global `cache` instance). The rate limiter middleware (`src/api/middleware/rate_limiter.py`) already demonstrates the Redis sorted set pattern for sliding window counting. The webhook security monitor should use the same approach for consistency and correctness.

According to OWASP's Logging and Monitoring guidelines (OWASP Top 10 A09:2021 — Security Logging and Monitoring Failures), security-relevant events must be stored in a persistent, centralized manner that survives application restarts and is accessible across all application instances.

---

## Current Code

```python
# File: rext-backend/src/services/webhook_security_monitor.py
# Lines: 59-65
def __init__(self):
    """Initialize security monitor"""
    # Storage: {ip_address: deque of WebhookFailureRecord}
    self._failures: Dict[str, deque] = defaultdict(deque)

    # Track when we last alerted for each IP (prevent spam)
    self._last_alert: Dict[str, datetime] = {}

    logger.info("WebhookSecurityMonitor initialized")
```

```python
# File: rext-backend/src/services/webhook_security_monitor.py
# Lines: 69-115
def record_verification_failure(
    self,
    ip_address: str,
    event_type: Optional[str] = None,
    signature_prefix: str = "",
    payload_size: int = 0
) -> None:
    record = WebhookFailureRecord(
        timestamp=datetime.utcnow(),
        ip_address=ip_address,
        event_type=event_type,
        signature_prefix=signature_prefix,
        payload_size=payload_size
    )
    self._failures[ip_address].append(record)
    self._cleanup_old_failures(ip_address)
    failure_count = len(self._failures[ip_address])
    # ... logging ...
    if self.should_alert(ip_address):
        self._send_security_alert(ip_address, failure_count)
```

---

## Why This Matters (Context & Reasoning)

The webhook security monitor is a critical component of the billing system's defense-in-depth strategy. It detects potential webhook spoofing attacks by tracking patterns of signature verification failures. When an attacker sends forged webhooks, each one fails signature verification. The monitor is supposed to detect this pattern and alert the security team.

However, because the data is stored in-memory, the detection mechanism is fundamentally unreliable in production. The application uses Uvicorn which supports multiple worker processes. Most production deployments run 2-8 workers for concurrency. Each worker has its own isolated Python interpreter, so failure data from one worker is invisible to others.

The application already has Redis infrastructure in place and uses it for rate limiting via sorted sets. Migrating the webhook security monitor to Redis is straightforward and aligns with existing patterns in the codebase.

---

## Impact

- **Severity:** Security monitoring data is lost on every restart/deployment. In multi-worker setups, attack detection is fragmented across workers, requiring N times the threshold failures to trigger an alert (where N is the worker count). This effectively disables the security monitoring in production.
- **Affected Users/Flows:** All webhook endpoints — the monitoring system is meant to protect the entire billing webhook pipeline (subscription events, payment events, license events).
- **Blast Radius:** Isolated to the webhook security monitoring subsystem, but the consequence is that attacks on the billing webhook pipeline go undetected.

---

## Recommended Solution

Replace in-memory storage with Redis sorted sets for failure tracking and Redis strings with TTL for alert cooldown tracking. This follows the exact same pattern already used by `RateLimiter` in `src/api/middleware/rate_limiter.py`.

### Step 1: Update imports in webhook_security_monitor.py

```python
# File: rext-backend/src/services/webhook_security_monitor.py
# Replace lines 1-33 with:
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
```

### Step 2: Replace the __init__ method

```python
# File: rext-backend/src/services/webhook_security_monitor.py
# Replace the __init__ method (lines 59-67):
def __init__(self):
    """Initialize security monitor with Redis-backed storage."""
    self.REDIS_KEY_PREFIX = "webhook_security:"
    self.FAILURE_KEY_PREFIX = f"{self.REDIS_KEY_PREFIX}failures:"
    self.ALERT_KEY_PREFIX = f"{self.REDIS_KEY_PREFIX}last_alert:"
    logger.info("WebhookSecurityMonitor initialized (Redis-backed)")
```

### Step 3: Replace record_verification_failure

```python
# File: rext-backend/src/services/webhook_security_monitor.py
# Replace the record_verification_failure method (lines 69-115):
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
```

### Step 4: Replace _cleanup_old_failures (no longer needed as a separate method)

```python
# File: rext-backend/src/services/webhook_security_monitor.py
# Remove the _cleanup_old_failures method entirely — cleanup is handled inline
# by zremrangebyscore in record_verification_failure
```

### Step 5: Replace should_alert

```python
# File: rext-backend/src/services/webhook_security_monitor.py
# Replace the should_alert method (lines 134-156):
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
```

### Step 6: Replace _send_security_alert

```python
# File: rext-backend/src/services/webhook_security_monitor.py
# Replace the _send_security_alert method (lines 158-223):
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
```

### Step 7: Replace get_failure_stats and clear_failures

```python
# File: rext-backend/src/services/webhook_security_monitor.py
# Replace get_failure_stats (lines 225-253):
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
```

### Step 8: Update callers to use async methods

The `record_verification_failure`, `should_alert`, `get_failure_stats`, and `clear_failures` methods are now `async`. Search for all callers and add `await`:

```bash
grep -rn "webhook_security_monitor\.\(record_verification_failure\|should_alert\|get_failure_stats\|clear_failures\)" rext-backend/src/
```

Update each call site to use `await`.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/utils/lemonsqueezy_webhook.py` | Various | Calls `record_verification_failure` — needs `await` |
| `rext-backend/src/api/routes/admin/webhook_monitoring_routes.py` | Various | Calls `get_failure_stats` and `clear_failures` — needs `await` |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Start the backend with 2+ Uvicorn workers
2. Send 3 failed webhook requests to worker 1, 3 to worker 2
3. Observe that neither worker triggers an alert (threshold is 5, each worker only sees 3)
4. Restart the application
5. Observe that all failure data is gone

### After Fix (Verify the Solution):
1. Start the backend with 2+ Uvicorn workers
2. Send 5 failed webhook requests (distributed across workers)
3. Verify that a security alert is triggered (all workers share the Redis counter)
4. Restart the application
5. Verify that failure data persists in Redis (check via `redis-cli KEYS webhook_security:*`)

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "webhook" -v
```

---

## Acceptance Criteria

- [ ] All webhook failure tracking uses Redis sorted sets instead of in-memory dicts
- [ ] Alert cooldown tracking uses Redis keys with TTL instead of in-memory dict
- [ ] Failure data persists across application restarts
- [ ] Failure data is shared across all Uvicorn workers
- [ ] Alert threshold is correctly enforced across workers (5 failures total, not per-worker)
- [ ] All callers updated to use `await` with the now-async methods
- [ ] Graceful fallback when Redis is unavailable (logs warning, does not crash)
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [redis-py Sorted Sets documentation](https://redis-py.readthedocs.io/en/stable/commands.html#redis.commands.SortedSetCommands) — Redis sorted set commands for sliding window pattern
- **Security Advisory:** [OWASP A09:2021 — Security Logging and Monitoring Failures](https://owasp.org/Top10/A09_2021-Security_Logging_and_Monitoring_Failures/) — Security monitoring must be persistent and centralized
- **Migration Guide:** N/A
- **Best Practice Reference:** [Redis Rate Limiting Pattern](https://redis.io/glossary/rate-limiting/) — Sliding window counter pattern using sorted sets
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None (Redis is already configured in the project)
- **Blocks:** None
- **Related:** TASK-125 (X-Forwarded-For Spoofable — same webhook security subsystem)
