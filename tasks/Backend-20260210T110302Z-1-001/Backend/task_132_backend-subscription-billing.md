# Task 132: No Retry Logic on LemonSqueezy API Calls — Transient Failures Leave System Inconsistent

## Metadata
- **Task ID:** TASK-132
- **Source:** Backend Subscription & Billing Audit (Finding #8 under P1 High)
- **Audit Report:** `audit-reports/backend-subscription-billing.md`
- **Priority:** P1 High
- **Category:** broken-functionality
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The `LemonSqueezyProvider` class (`src/providers/payment/providers/lemonsqueezy.py`, 1,074 lines) is the sole interface between the Rext backend and the LemonSqueezy payment API. Every external payment operation — creating checkouts, cancelling subscriptions, updating subscriptions, validating licenses, processing refunds — flows through the `_make_request()` method (lines 94-242). This method makes bare `httpx` HTTP requests with no retry logic whatsoever.

The `tenacity` library (version `>=8.2.0`) is already declared as a dependency in `pyproject.toml` (line 50) but is never imported or used anywhere in the payment provider code.

When a transient failure occurs — network timeout, DNS resolution failure, TCP connection reset, LemonSqueezy 502/503 error, or 429 rate limit — the `_make_request()` method immediately raises a `LemonSqueezyError` or `LemonSqueezyAPIError` exception. This exception propagates up to the calling route handler, which typically catches it and returns an error response to the user.

The critical problem is that some payment operations modify state on both sides: the local database AND LemonSqueezy's servers. For example, `cancel_subscription()` (lines 561-618) calls `DELETE /subscriptions/{id}` on LemonSqueezy — if the network drops after LemonSqueezy processes the cancellation but before the response arrives, the local system receives a timeout error. The route handler reports failure to the user, but the subscription is actually cancelled on LemonSqueezy's side. The user may retry, causing a second cancellation attempt (which fails because it's already cancelled), leading to confusing error messages.

Similarly, `update_subscription()` (lines 620-683) and `create_checkout_session()` (lines 338-484) are both vulnerable: a transient error on a non-idempotent operation can leave the system in an inconsistent state where the local database and LemonSqueezy disagree on the current subscription state.

The `_make_request()` method already handles `httpx.HTTPError` exceptions (line 223) and reports them to Sentry — but it doesn't retry. It also correctly detects 429 and 5xx errors (lines 200-217) and alerts — but doesn't retry with backoff.

---

## Current Code

```python
# File: src/providers/payment/providers/lemonsqueezy.py
# Lines: 94-242 (_make_request method - abbreviated key section)

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        # ... breadcrumb and logging setup ...

        with log_payment_timing(...) as ctx:
            try:
                response = await self.client.request(
                    method=method,
                    url=endpoint,
                    json=data,
                    params=params
                )
                # ... error handling (raises LemonSqueezyAPIError for 4xx/5xx) ...
                return response.json()

            except httpx.HTTPError as e:
                # No retry — immediately raises
                logger.error(f"LemonSqueezy HTTP error: {str(e)}", ...)
                raise LemonSqueezyError(f"HTTP request failed: {str(e)}") from e
```

```python
# File: pyproject.toml
# Line 50 (tenacity is a dependency but never used)
    "tenacity>=8.2.0",
```

---

## Why This Matters (Context & Reasoning)

LemonSqueezy is an external third-party service accessed over the internet. Transient failures are inevitable in any distributed system:

1. **Network timeouts:** The current `httpx` timeout is 30 seconds (line 87). DNS resolution failures, TCP connection timeouts, and TLS handshake failures are common in production.
2. **Rate limiting (429):** LemonSqueezy enforces API rate limits. Without retry-after handling, burst operations (e.g., webhook processing during a billing cycle) can trigger rate limits that crash the entire batch.
3. **Server errors (502/503/504):** LemonSqueezy performs deployments and maintenance. During these periods, brief 5xx responses are expected and should be retried.
4. **Connection resets:** Cloud infrastructure (load balancers, proxies) may reset idle connections.

The billing system handles real money. An inconsistent state between the local database and LemonSqueezy can result in:
- Users being charged after they believe they've cancelled
- Cancelled subscriptions appearing active in the Rext dashboard
- Failed checkout sessions that actually created subscriptions on LemonSqueezy's side
- Duplicate refunds if a successful refund response is lost

Adding retry logic with exponential backoff is the standard approach for external API integrations and is particularly critical for financial operations.

---

## Impact

- **Severity:** Any transient network error during a payment operation causes immediate failure and potential state inconsistency between the local database and LemonSqueezy. Users may be charged incorrectly or have subscriptions in a broken state.
- **Affected Users/Flows:** All subscription operations (create, cancel, upgrade, downgrade), checkout sessions, license validation/activation, refund processing, and any admin operation that calls the LemonSqueezy API.
- **Blast Radius:** Every single endpoint and service that uses `LemonSqueezyProvider` is affected. This includes subscription routes, checkout routes, license routes, admin routes, webhook retry, and scheduled tasks.

---

## Recommended Solution

Add `tenacity` retry decorators to the `_make_request()` method. Use exponential backoff for transient errors, and handle 429 rate limit responses with `Retry-After` header awareness.

### Step 1: Add tenacity imports to the provider

```python
# File: src/providers/payment/providers/lemonsqueezy.py
# Add after the existing imports (after line 16):

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
    RetryError,
)
```

### Step 2: Create a retryable exception class for transient errors

```python
# File: src/providers/payment/providers/lemonsqueezy.py
# Add after LemonSqueezyAPIError class (after line 49):

class LemonSqueezyTransientError(LemonSqueezyError):
    """Transient error that should be retried (5xx, timeout, network)."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        self.status_code = status_code
        super().__init__(message)
```

### Step 3: Refactor `_make_request` to separate retryable logic

```python
# File: src/providers/payment/providers/lemonsqueezy.py
# Replace the _make_request method (lines 94-242) with:

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(LemonSqueezyTransientError),
        before_sleep=before_sleep_log(logger, log_level=20),  # INFO level
        reraise=True,
    )
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Make HTTP request to LemonSqueezy API with automatic retry on transient errors.

        Retries up to 3 times with exponential backoff (1s, 2s, 4s) for:
        - Network errors (timeout, connection reset, DNS failure)
        - Server errors (500, 502, 503, 504)
        - Rate limit errors (429) with Retry-After header awareness

        Args:
            method: HTTP method (GET, POST, PATCH, DELETE)
            endpoint: API endpoint (e.g., "/customers")
            data: Request body data
            params: Query parameters

        Returns:
            Dict containing response data

        Raises:
            LemonSqueezyAPIError: If request fails with a non-retryable error (4xx)
            LemonSqueezyTransientError: If all retries are exhausted for transient errors
        """
        add_payment_breadcrumb(
            f"LemonSqueezy API: {method} {endpoint}",
            operation="api_request",
            data={
                "method": method,
                "endpoint": endpoint,
                "has_data": data is not None,
                "has_params": params is not None,
            }
        )

        with log_payment_timing(
            logger,
            operation="api_request",
            message=f"LemonSqueezy API: {method} {endpoint}",
            method=method,
            endpoint=endpoint,
            provider="lemonsqueezy"
        ) as ctx:
            try:
                response = await self.client.request(
                    method=method,
                    url=endpoint,
                    json=data,
                    params=params
                )

                ctx["status_code"] = response.status_code

                if response.status_code < 400:
                    logger.debug(
                        f"LemonSqueezy API response: {response.status_code}",
                        method=method,
                        endpoint=endpoint,
                        status_code=response.status_code
                    )
                    return response.json()

                # Parse error details
                try:
                    error_data = response.json()
                    error_message = error_data.get("errors", [{}])[0].get(
                        "detail", "Unknown error"
                    )
                except Exception:
                    error_message = response.text or "Unknown error"

                logger.error(
                    f"LemonSqueezy API error: {response.status_code}",
                    method=method,
                    endpoint=endpoint,
                    status_code=response.status_code,
                    error_message=error_message
                )

                # Handle rate limiting (429) — raise transient for retry
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After", "5")
                    logger.warning(
                        f"LemonSqueezy rate limited. Retry-After: {retry_after}s",
                        method=method,
                        endpoint=endpoint,
                    )
                    alert_api_error(
                        method=method,
                        endpoint=endpoint,
                        status_code=429,
                        error_message="Rate limit exceeded",
                        operation="api_request"
                    )
                    raise LemonSqueezyTransientError(
                        f"Rate limited: {error_message}",
                        status_code=429
                    )

                # Handle server errors (5xx) — raise transient for retry
                if response.status_code >= 500:
                    alert_api_error(
                        method=method,
                        endpoint=endpoint,
                        status_code=response.status_code,
                        error_message=error_message,
                        operation="api_request"
                    )
                    raise LemonSqueezyTransientError(
                        f"Server error ({response.status_code}): {error_message}",
                        status_code=response.status_code
                    )

                # Client errors (4xx except 429) are NOT retryable
                api_error = LemonSqueezyAPIError(
                    status_code=response.status_code,
                    message=error_message,
                    details={"endpoint": endpoint, "method": method}
                )

                capture_payment_exception(
                    api_error,
                    operation="api_request",
                    context={
                        "method": method,
                        "endpoint": endpoint,
                        "status_code": response.status_code,
                        "error_message": error_message,
                    }
                )

                raise api_error

            except httpx.TimeoutException as e:
                logger.error(
                    f"LemonSqueezy timeout: {str(e)}",
                    method=method,
                    endpoint=endpoint,
                )
                capture_payment_exception(
                    e, operation="api_request",
                    context={"method": method, "endpoint": endpoint, "error_type": "timeout"}
                )
                raise LemonSqueezyTransientError(f"Request timeout: {str(e)}") from e

            except httpx.NetworkError as e:
                logger.error(
                    f"LemonSqueezy network error: {str(e)}",
                    method=method,
                    endpoint=endpoint,
                )
                capture_payment_exception(
                    e, operation="api_request",
                    context={"method": method, "endpoint": endpoint, "error_type": "network"}
                )
                raise LemonSqueezyTransientError(f"Network error: {str(e)}") from e

            except httpx.HTTPError as e:
                logger.error(
                    f"LemonSqueezy HTTP error: {str(e)}",
                    method=method,
                    endpoint=endpoint,
                    error_type=type(e).__name__
                )
                capture_payment_exception(
                    e, operation="api_request",
                    context={"method": method, "endpoint": endpoint, "error_type": "http_error"}
                )
                raise LemonSqueezyError(f"HTTP request failed: {str(e)}") from e
```

### Step 4: Update callers to handle RetryError gracefully

The `tenacity` retry decorator with `reraise=True` will re-raise the last exception after all retries are exhausted. No caller changes are needed since the same exception types are raised. However, add a log message for exhausted retries by adding a custom callback:

```python
# File: src/providers/payment/providers/lemonsqueezy.py
# Add after imports, before the class definition:

def _log_retry_exhausted(retry_state):
    """Log when all retries are exhausted."""
    logger.error(
        f"LemonSqueezy API call failed after {retry_state.attempt_number} attempts",
        extra={
            "outcome": str(retry_state.outcome),
            "attempt_number": retry_state.attempt_number,
        }
    )
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/services/subscription_service.py` | varies | Calls `LemonSqueezyProvider` methods — catches `Exception` broadly; may want to handle `LemonSqueezyTransientError` distinctly |
| `src/services/webhook_handlers/subscription_handlers.py` | varies | Webhook handlers may call back to LemonSqueezy API — retry logic protects these calls |
| `src/services/webhook_handlers/order_handlers.py` | varies | Same as above for order-related API calls |
| `src/services/license_service.py` | varies | License validation/activation calls — benefits from retry |
| `src/services/refund_service.py` | varies | Refund creation calls to LemonSqueezy API — critical to retry |
| `src/api/routes/subscriptions/subscription_routes.py` | 437-493 | Cancel endpoint catches broad `Exception` — should distinguish transient vs permanent errors |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Temporarily modify `lemonsqueezy.py` to inject a timeout on the first call:
   ```python
   # In _make_request, before the httpx call:
   import random
   if random.random() < 0.5:
       raise httpx.TimeoutException("Simulated timeout")
   ```
2. Call any subscription endpoint (e.g., GET `/subscriptions/my-subscription`)
3. Observe: The request fails immediately with no retry

### After Fix (Verify the Solution):
1. Use the same timeout injection but now with retry logic in place
2. Call the same endpoint
3. Observe: The request retries automatically (visible in logs as `tenacity` retry messages)
4. After the retry succeeds, the endpoint returns normally

### Unit Test:
```python
import pytest
from unittest.mock import AsyncMock, patch
import httpx

@pytest.mark.asyncio
async def test_retry_on_timeout():
    """Verify that transient errors trigger retries."""
    provider = LemonSqueezyProvider(
        api_key="test_key",
        store_id="test_store",
    )

    # Mock client.request to fail twice then succeed
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": {"id": "1"}}

    call_count = 0
    async def mock_request(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise httpx.TimeoutException("Simulated timeout")
        return mock_response

    provider.client.request = mock_request

    result = await provider._make_request("GET", "/test")
    assert call_count == 3  # 2 failures + 1 success
    assert result == {"data": {"id": "1"}}
```

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "payment or lemonsqueezy or provider" -v
```

---

## Acceptance Criteria

- [ ] `_make_request()` retries on `httpx.TimeoutException` and `httpx.NetworkError` (up to 3 attempts)
- [ ] `_make_request()` retries on HTTP 5xx responses (500, 502, 503, 504)
- [ ] `_make_request()` retries on HTTP 429 rate limit responses
- [ ] `_make_request()` does NOT retry on HTTP 4xx client errors (400, 401, 403, 404, 422)
- [ ] Exponential backoff is used between retries (1s, 2s, 4s approximately)
- [ ] Retry attempts are logged at INFO level
- [ ] Final failure after all retries is logged at ERROR level with attempt count
- [ ] `tenacity` import is added (library already in `pyproject.toml`)
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** https://tenacity.readthedocs.io/en/latest/ — Tenacity retry library documentation
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** https://www.python-httpx.org/advanced/transports/#custom-transports — httpx transport and retry documentation
- **Related Issues/PRs:** See `pyproject.toml` line 50 where `tenacity>=8.2.0` is already listed as a dependency

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-131 (Sandbox Mode Broken — both are LemonSqueezy provider infrastructure issues), TASK-125 (X-Forwarded-For Spoofing — webhook security), TASK-128 (No Rate Limiting on License Endpoints)
