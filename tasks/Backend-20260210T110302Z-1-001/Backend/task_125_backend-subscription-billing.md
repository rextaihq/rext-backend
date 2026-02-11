# Task 125: X-Forwarded-For Header Trusted for IP Whitelist — Spoofable Bypass

## Metadata
- **Task ID:** TASK-125
- **Source:** B5 - Subscription & Billing (Finding #10 under P1 High)
- **Audit Report:** `audit-reports/backend-subscription-billing.md`
- **Priority:** P1 High
- **Category:** security
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The webhook IP whitelist middleware in `rext-backend/src/api/middleware/webhook_security.py` extracts the client IP address from the `X-Forwarded-For` HTTP header without any validation that the header was set by a trusted reverse proxy. The `_get_client_ip` static method at line 91 blindly trusts this header:

```python
forwarded_for = request.headers.get("X-Forwarded-For")
if forwarded_for:
    client_ip = forwarded_for.split(",")[0].strip()
    return client_ip
```

The `X-Forwarded-For` header is a standard mechanism used by proxies and load balancers to communicate the original client IP. However, it is trivially spoofable — any HTTP client can set this header to any value. An attacker can bypass the entire IP whitelist by sending a request with `X-Forwarded-For: 159.223.172.1` (matching the whitelisted `159.223.172.0/24` CIDR range), even when their actual IP is completely different.

This vulnerability is classified under OWASP's "Security Misconfiguration" (A05:2021) and specifically matches CWE-348 (Use of Less Trusted Source). According to OWASP guidelines, `X-Forwarded-For` should never be trusted from arbitrary clients — it should only be accepted from known, trusted proxy IP addresses.

The same vulnerable pattern also exists in `src/api/middleware/rate_limiter.py` at line 202 and `src/api/middleware/request_tracker.py` at line 282, where `X-Forwarded-For` is used for rate limiting keys and logging respectively. While those are less critical than the webhook security bypass, an attacker could use IP spoofing to evade rate limits.

While HMAC signature verification (the second security layer) remains intact, defense-in-depth requires both layers to function correctly. The IP whitelist is intended to be the first line of defense, and its bypass reduces the system to single-factor webhook authentication.

---

## Current Code

```python
# File: rext-backend/src/api/middleware/webhook_security.py
# Lines: 91-130
@staticmethod
def _get_client_ip(request: Request) -> str:
    """
    Extract client IP from request, handling proxies.

    Checks headers in order of preference:
    1. X-Forwarded-For (first IP in comma-separated list)
    2. X-Real-IP
    3. request.client.host (direct connection)
    """
    # Check X-Forwarded-For header (set by proxies/load balancers)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # X-Forwarded-For can be comma-separated, take first IP (original client)
        client_ip = forwarded_for.split(",")[0].strip()
        logger.debug(
            f"Client IP from X-Forwarded-For: {client_ip}",
            extra={"x_forwarded_for": forwarded_for}
        )
        return client_ip

    # Check X-Real-IP header (alternative proxy header)
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        client_ip = real_ip.strip()
        logger.debug(
            f"Client IP from X-Real-IP: {client_ip}",
            extra={"x_real_ip": real_ip}
        )
        return client_ip

    # Direct connection (no proxy)
    client_ip = request.client.host if request.client else "unknown"
    logger.debug(f"Client IP from direct connection: {client_ip}")
    return client_ip
```

---

## Why This Matters (Context & Reasoning)

The webhook IP whitelist is the first security layer protecting the billing system's webhook endpoints. These endpoints process payment events from LemonSqueezy — subscription creations, cancellations, payment failures, and refunds. If an attacker can bypass the IP whitelist, they can send forged webhook payloads to the endpoint. While HMAC signature verification should catch forged payloads, relying on a single security layer violates defense-in-depth principles.

In a production deployment behind a load balancer or CDN (AWS ALB, Cloudflare, nginx), the application receives connections from the proxy, not directly from clients. The proxy sets `X-Forwarded-For` to communicate the original client IP. However, the proxy appends to (not replaces) any existing `X-Forwarded-For` header. This means if a client sends `X-Forwarded-For: 159.223.172.1`, the proxy would produce `X-Forwarded-For: 159.223.172.1, <actual-client-ip>`. The code takes the first IP (`split(",")[0]`), which is the attacker-controlled value.

The correct approach is to either: (a) use `request.client.host` which gives the direct connection IP (the proxy's IP in proxied setups, or the real client IP in direct connections), combined with Starlette's `ProxyHeadersMiddleware` configured with trusted proxy IPs; or (b) take the rightmost untrusted IP from the `X-Forwarded-For` chain by knowing which IPs are trusted proxies.

---

## Impact

- **Severity:** Complete bypass of webhook IP whitelist security layer. Attacker can send requests that appear to originate from whitelisted LemonSqueezy IPs. Combined with rate limiter evasion (same pattern in `rate_limiter.py`), attacker can also bypass rate limiting.
- **Affected Users/Flows:** All webhook processing (subscription lifecycle events, payment events, license events). Also affects rate limiting accuracy for all API endpoints.
- **Blast Radius:** High — the IP extraction pattern is duplicated in 3 middleware files (`webhook_security.py`, `rate_limiter.py`, `request_tracker.py`), meaning this fix needs to be applied consistently across all three.

---

## Recommended Solution

The recommended approach uses Uvicorn/Starlette's built-in `ProxyHeadersMiddleware` for trusted proxy header handling, and modifies the webhook security middleware to use `request.client.host` instead of reading raw headers.

### Step 1: Configure ProxyHeadersMiddleware in server.py

Starlette provides `ProxyHeadersMiddleware` which correctly handles `X-Forwarded-For` by only trusting headers from known proxy IPs. When the middleware detects a request from a trusted proxy, it updates `request.client.host` with the real client IP from the forwarded headers.

```python
# File: rext-backend/src/api/server.py
# Add after the existing middleware imports (around line 17):
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
```

```python
# File: rext-backend/src/api/server.py
# Add as the FIRST middleware (before CORS, around line 126):
# Proxy headers middleware - MUST be innermost (added first)
# This correctly processes X-Forwarded-For only from trusted proxies
# and updates request.client.host with the real client IP
app.add_middleware(
    ProxyHeadersMiddleware,
    trusted_hosts=settings.TRUSTED_PROXY_IPS.split(",") if hasattr(settings, "TRUSTED_PROXY_IPS") and settings.TRUSTED_PROXY_IPS else ["127.0.0.1", "::1"]
)
```

### Step 2: Add TRUSTED_PROXY_IPS to settings

```python
# File: rext-backend/src/api/config.py
# Add to the Settings class:
TRUSTED_PROXY_IPS: str = os.getenv("TRUSTED_PROXY_IPS", "127.0.0.1,::1")
```

### Step 3: Fix webhook_security.py to use request.client.host

```python
# File: rext-backend/src/api/middleware/webhook_security.py
# Replace the _get_client_ip method (lines 91-130) with:
@staticmethod
def _get_client_ip(request: Request) -> str:
    """
    Extract client IP from request.

    Uses request.client.host which is set correctly by ProxyHeadersMiddleware
    when behind a trusted reverse proxy. Do NOT read X-Forwarded-For directly
    as it is spoofable.

    Args:
        request: FastAPI request object

    Returns:
        Client IP address as string
    """
    client_ip = request.client.host if request.client else "unknown"
    logger.debug(
        f"Client IP resolved: {client_ip}",
        extra={"client_ip": client_ip}
    )
    return client_ip
```

### Step 4: Fix rate_limiter.py to use request.client.host

```python
# File: rext-backend/src/api/middleware/rate_limiter.py
# Replace lines 199-206 in get_client_key method:
def get_client_key(self, request: Request) -> str:
    """
    Generate a unique key for the client.

    Prefers user ID if authenticated, falls back to IP address.
    Uses request.client.host (set by ProxyHeadersMiddleware for proxied requests).
    """
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return f"user:{user_id}"

    client_ip = request.client.host if request.client else "unknown"
    return f"ip:{client_ip}"
```

### Step 5: Fix request_tracker.py to use request.client.host

```python
# File: rext-backend/src/api/middleware/request_tracker.py
# Replace lines 271-293 in _get_client_ip method:
def _get_client_ip(self, request: Request) -> str:
    """
    Extract client IP address from request.

    Uses request.client.host which is set correctly by ProxyHeadersMiddleware.
    """
    return getattr(request.client, "host", "unknown") if request.client else "unknown"
```

### Step 6: Set TRUSTED_PROXY_IPS in production environment

```bash
# In production .env or environment configuration:
# Set to your load balancer / CDN IP ranges
TRUSTED_PROXY_IPS="10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/api/middleware/rate_limiter.py` | `199-206` | Same `X-Forwarded-For` trust pattern in `get_client_key()` — allows rate limit evasion |
| `rext-backend/src/api/middleware/request_tracker.py` | `271-293` | Same pattern in `_get_client_ip()` — affects logging accuracy |
| `rext-backend/src/api/middleware/rate_limiter.py` | `400-402` | `EndpointRateLimiter.__call__` also reads `request.client.host` directly — less affected but should be consistent |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Start the backend server locally
2. Send a webhook request with a spoofed `X-Forwarded-For` header:
   ```bash
   curl -X POST http://localhost:2024/api/v1/subscriptions/webhooks/lemonsqueezy \
     -H "X-Forwarded-For: 159.223.172.1" \
     -H "Content-Type: application/json" \
     -d '{"test": "payload"}'
   ```
3. Observe that the request passes IP whitelist validation (the response will fail at HMAC verification, but the IP check passes)

### After Fix (Verify the Solution):
1. Send the same request — it should now be rejected with 403 because `request.client.host` returns the actual client IP (127.0.0.1 for localhost), not the spoofed header value
2. Verify that legitimate webhook requests still work when `TRUSTED_PROXY_IPS` is correctly configured

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "webhook" -v
```

---

## Acceptance Criteria

- [ ] `X-Forwarded-For` header is no longer read directly in any middleware for security decisions
- [ ] `ProxyHeadersMiddleware` is configured with `trusted_hosts` setting
- [ ] `TRUSTED_PROXY_IPS` environment variable is documented and configurable
- [ ] Webhook IP whitelist uses `request.client.host` exclusively
- [ ] Rate limiter uses `request.client.host` exclusively
- [ ] Request tracker uses `request.client.host` exclusively
- [ ] Spoofed `X-Forwarded-For` headers no longer bypass IP whitelist
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Uvicorn ProxyHeadersMiddleware](https://www.uvicorn.org/settings/#proxy-headers) — Starlette/Uvicorn built-in proxy header handling
- **Security Advisory:** [CWE-348: Use of Less Trusted Source](https://cwe.mitre.org/data/definitions/348.html) — Trusting client-supplied headers for security decisions
- **Best Practice Reference:** [OWASP HTTP Request Smuggling / Header Manipulation](https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/07-Input_Validation_Testing/17-Testing_for_HTTP_Incoming_Requests) — OWASP guidance on trusting HTTP headers
- **Migration Guide:** N/A
- **Related Issues/PRs:** [Starlette ProxyHeadersMiddleware source](https://github.com/encode/uvicorn/blob/master/uvicorn/middleware/proxy_headers.py)

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-019 (Missing Security Headers from B1), TASK-065 (No Rate Limiting on OAuth Endpoints from B3)
