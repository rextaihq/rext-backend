# Task 134: Cancel Endpoint Returns HTTP 200 for Errors — Clients Cannot Distinguish Success from Failure

## Metadata
- **Task ID:** TASK-134
- **Source:** Backend Subscription & Billing Audit (Finding #13 under P1 High)
- **Audit Report:** `audit-reports/backend-subscription-billing.md`
- **Priority:** P1 High
- **Category:** broken-functionality
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `cancel_subscription` endpoint in `src/api/routes/subscriptions/subscription_routes.py` (lines 423-493) has two distinct error paths that both return HTTP 200 status codes with embedded error information in the response body, instead of returning proper HTTP 4xx/5xx error responses.

**Error Path 1 — Subscription Not Found (lines 446-457):**
When `service.cancel()` returns `None` (no active subscription found), the handler returns a raw dict with `"success": False` and an embedded `"error"` object containing `"status_code": 404`. However, the actual HTTP response status code is 200 because the handler returns a plain dict (which the `@db_transaction_handler` decorator wraps in a `success()` JSONResponse with status 200).

```python
if not subscription:
    return {
        "success": False,
        "meta": {"request_id": request.headers.get("X-Request-ID")},
        "data": None,
        "error": {
            "code": "not_found",
            "message": "No active subscription found to cancel",
            "severity": "high",
            "status_code": 404
        }
    }
```

**Error Path 2 — Exception Handling (lines 482-493):**
When any exception occurs during cancellation (payment provider errors, database errors, service layer failures), the handler catches the broad `Exception`, swallows the stack trace, and returns HTTP 200 with a raw dict containing `"success": False` and `str(e)` as the error message. This has two compounding problems:
1. HTTP 200 makes the error invisible to standard HTTP error handling (frontend `response.ok`, monitoring tools, API gateways, load balancers)
2. `str(e)` leaks internal error details (database column names, Python traceback fragments, third-party service names) directly to the client

```python
except Exception as e:
    return {
        "success": False,
        "meta": {"request_id": request.headers.get("X-Request-ID")},
        "data": None,
        "error": {
            "code": "internal_server_error",
            "message": str(e),
            "severity": "high",
            "status_code": 500
        }
    }
```

The irony is that the `@db_transaction_handler("cancel subscription")` decorator applied to this endpoint (line 425) already contains proper error handling infrastructure. At lines 196-230 of `src/utils/route_decorators.py`, the decorator catches all exceptions, rolls back the transaction, logs the full stack trace server-side, and returns a proper `error()` response with HTTP 500. But the handler's internal `try/except` block catches the exception **before** the decorator can handle it, completely bypassing this infrastructure.

Additionally, the codebase already has the proper `not_found()` utility function in `src/utils/response_utils.py` (lines 349-381) that returns a `JSONResponse` with HTTP 404 status code and the standardized error envelope format. The `error()` utility (lines 170-222) supports all the `ErrorCode` values including `RESOURCE_NOT_FOUND`, `EXTERNAL_SERVICE_ERROR`, and `INTERNAL_SERVER_ERROR`.

---

## Current Code

```python
# File: src/api/routes/subscriptions/subscription_routes.py
# Lines: 423-493 (cancel_subscription endpoint)

@router.post("/cancel", response_model=dict)
@require_permissions("subscription.manage")
@db_transaction_handler("cancel subscription")
async def cancel_subscription(
    request: Request,
    cancel_data: SubscriptionCancelRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _rate_limit: None = Depends(subscription_cancel_rate_limit())
):
    user_id = current_user.get("identity")
    service = SubscriptionService(db)

    try:
        # Cancel subscription
        subscription = await service.cancel(
            user_id=user_id,
            reason=cancel_data.reason,
            cancel_immediately=cancel_data.cancel_immediately,
            background_tasks=background_tasks
        )

        if not subscription:
            return {
                "success": False,
                "meta": {"request_id": request.headers.get("X-Request-ID")},
                "data": None,
                "error": {
                    "code": "not_found",
                    "message": "No active subscription found to cancel",
                    "severity": "high",
                    "status_code": 404
                }
            }

        message = (
            "Subscription cancelled immediately"
            if cancel_data.cancel_immediately
            else f"Subscription will end on {subscription.end_date.strftime('%Y-%m-%d') if subscription.end_date else 'N/A'}"
        )

        # Schedule cancellation notification
        await schedule_if_allowed(
            db=db,
            user_id=str(user_id),
            background_tasks=background_tasks,
            pref_flag="subscription_cancelled",
            message="Your subscription has been cancelled.",
            payload={"subscription_id": str(subscription.id), "type": "cancelled"},
        )

        return {
            "success": True,
            "meta": {"request_id": request.headers.get("X-Request-ID")},
            "data": subscription.to_dict(),
            "message": message
        }

    except Exception as e:
        return {
            "success": False,
            "meta": {"request_id": request.headers.get("X-Request-ID")},
            "data": None,
            "error": {
                "code": "internal_server_error",
                "message": str(e),
                "severity": "high",
                "status_code": 500
            }
        }
```

```python
# File: src/utils/route_decorators.py
# Lines: 196-230 (db_transaction_handler — already handles exceptions properly)

            except Exception as e:
                # Unexpected errors - rollback and return error response
                if db and hasattr(db, "rollback"):
                    await db.rollback()
                # Log unexpected exception at ERROR level with full stack trace
                logger.exception(
                    f"Unexpected error in {operation_name}",
                    extra={...}
                )
                # Return standardized error response
                return error(
                    message=f"Failed to {operation_name}",
                    code=error_code,
                    status_code=500,
                    severity=error_severity,
                    request=request,
                    context=context
                )
```

```python
# File: src/utils/response_utils.py
# Lines: 349-381 (not_found utility — available but unused in cancel endpoint)

def not_found(
    resource_type: str = "resource",
    resource_id: Optional[str] = None,
    request: Optional[Request] = None
) -> JSONResponse:
    # Returns proper HTTP 404 JSONResponse with standardized error envelope
```

---

## Why This Matters (Context & Reasoning)

Returning HTTP 200 for error conditions is a well-known anti-pattern that breaks multiple layers of error handling:

1. **Frontend `response.ok` check:** The standard way to check for errors in JavaScript's `fetch()` API is `response.ok`, which checks if the HTTP status code is in the 200-299 range. When the cancel endpoint returns 200 for errors, `response.ok` is `true`, and the frontend treats the failure as a success. The user sees "Subscription cancelled" when it actually wasn't.

2. **HTTP middleware and monitoring:** API gateways, load balancers, CDNs, and monitoring tools (Sentry, DataDog, New Relic) track HTTP error rates using status codes. When errors return 200, these tools report 0% error rate even when the endpoint is consistently failing. This eliminates visibility into production issues.

3. **Retry logic:** HTTP client libraries and API gateways often automatically retry 5xx responses. When a transient payment provider error returns 200, no automatic retry occurs — the error is permanent from the client's perspective.

4. **Security — information leakage:** The `str(e)` in the error response (line 489) can expose Python exception messages containing database column names, SQL query fragments, third-party API error details, file paths, and internal service names. This aids attackers in mapping the system's internals.

5. **`db_transaction_handler` bypass:** The decorator already handles transaction rollback and proper error responses. The internal `try/except` block prevents the decorator from functioning, meaning database transactions may not be properly rolled back on error (the decorator's rollback at line 198 is never reached because the handler returns a "success" dict to the decorator).

The cancel operation is particularly sensitive because it involves both local database state and the external LemonSqueezy payment provider. A failed cancellation that appears successful to the user means their subscription continues and they continue to be charged.

---

## Impact

- **Severity:** Users may believe their subscription was successfully cancelled when it actually failed. The frontend cannot distinguish success from failure using standard HTTP status code checks. Internal error details are leaked to clients. Monitoring tools cannot detect error rate spikes on this endpoint.
- **Affected Users/Flows:** All users cancelling subscriptions via the API. Frontend cancel subscription flow. Admin monitoring of cancellation error rates.
- **Blast Radius:** Directly affects the cancel subscription endpoint. The same anti-pattern exists in the checkout routes (`checkout_routes.py:105-109`, `checkout_routes.py:269-273`) where `str(e)` is leaked via `HTTPException`, but those at least use proper HTTP status codes.

---

## Recommended Solution

Remove the internal `try/except` block entirely and use the `not_found()` response utility for the subscription-not-found case. Let the `@db_transaction_handler` decorator handle all unexpected exceptions — it already returns proper HTTP 500 with the `error()` utility, logs server-side, and rolls back the transaction.

### Step 1: Update the import to include `not_found` and `error`

```python
# File: src/api/routes/subscriptions/subscription_routes.py
# Replace line 27:
from src.utils.response_utils import success, created, not_found, error
```

### Step 2: Replace the cancel endpoint with proper error handling

```python
# File: src/api/routes/subscriptions/subscription_routes.py
# Replace lines 423-493 with:

@router.post("/cancel", response_model=dict)
@require_permissions("subscription.manage")
@db_transaction_handler("cancel subscription")
async def cancel_subscription(
    request: Request,
    cancel_data: SubscriptionCancelRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _rate_limit: None = Depends(subscription_cancel_rate_limit())
):
    user_id = current_user.get("identity")
    service = SubscriptionService(db)

    subscription = await service.cancel(
        user_id=user_id,
        reason=cancel_data.reason,
        cancel_immediately=cancel_data.cancel_immediately,
        background_tasks=background_tasks
    )

    if not subscription:
        return not_found(
            resource_type="subscription",
            request=request
        )

    message = (
        "Subscription cancelled immediately"
        if cancel_data.cancel_immediately
        else f"Subscription will end on {subscription.end_date.strftime('%Y-%m-%d') if subscription.end_date else 'N/A'}"
    )

    # Schedule cancellation notification
    await schedule_if_allowed(
        db=db,
        user_id=str(user_id),
        background_tasks=background_tasks,
        pref_flag="subscription_cancelled",
        message="Your subscription has been cancelled.",
        payload={"subscription_id": str(subscription.id), "type": "cancelled"},
    )

    return {
        "success": True,
        "meta": {"request_id": request.headers.get("X-Request-ID")},
        "data": subscription.to_dict(),
        "message": message
    }
```

### Step 3: Verify the `db_transaction_handler` catches remaining exceptions

No changes needed to the decorator. The decorator at `src/utils/route_decorators.py:196-230` already:
1. Catches `Exception` at line 196
2. Rolls back the database transaction at line 198-199
3. Logs the full exception with stack trace at line 206-212
4. Returns a proper `error()` response with HTTP 500 at lines 223-230
5. Uses a generic message (`"Failed to cancel subscription"`) that doesn't leak internals

By removing the internal `try/except`, exceptions from `service.cancel()` (including LemonSqueezy API errors, database errors, etc.) will propagate up to the decorator, which handles them correctly.

### Step 4: Fix `str(e)` leakage in checkout_routes.py

While the checkout routes use `HTTPException` (which returns proper HTTP status codes), they still leak `str(e)`:

```python
# File: src/api/routes/subscriptions/checkout_routes.py
# Line 108: Replace str(e) with generic message
        logger.error(f"Failed to create portal session: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create portal session. Please try again or contact support."
        )

# Line 272: Replace str(e) with generic message
        logger.error(f"Failed to cancel subscription: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel subscription. Please try again or contact support."
        )
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/routes/subscriptions/checkout_routes.py` | 105-109 | Portal session error handler leaks `str(e)` via `HTTPException.detail` — but at least uses HTTP 500 |
| `src/api/routes/subscriptions/checkout_routes.py` | 269-273 | Cancel via checkout leaks `str(e)` via `HTTPException.detail` — same issue |
| `src/api/routes/subscriptions/subscription_routes.py` | 707-708 | Invoice retrieval logs `str(e)` and silently returns empty list — separate but related issue |
| `src/utils/route_decorators.py` | 216-219 | `db_transaction_handler` includes `str(e)` in error context — should be gated by a `DEBUG` mode flag in production |
| `src/utils/response_utils.py` | 349-381 | `not_found()` utility — already exists and should be used for the not-found case |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Make a cancel request for a user with no active subscription:
   ```bash
   curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/api/subscriptions/cancel \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{"reason": "testing"}'
   ```
2. Observe: HTTP status code is `200`
3. Inspect response body: Contains `"success": false` with embedded `"status_code": 404`
4. Trigger a service exception (e.g., disconnect LemonSqueezy API key temporarily)
5. Attempt to cancel an active subscription
6. Observe: HTTP status code is still `200` and response body contains `str(e)` with internal error details

### After Fix (Verify the Solution):
1. Make a cancel request for a user with no active subscription:
   ```bash
   curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/api/subscriptions/cancel \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{"reason": "testing"}'
   ```
2. Observe: HTTP status code is `404`
3. Inspect response body: Standardized error response from `not_found()` utility
4. Trigger a service exception
5. Observe: HTTP status code is `500`
6. Inspect response body: Generic message `"Failed to cancel subscription"` — no internal details
7. Check server logs: Full exception details are logged server-side

### Unit Test:
```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_cancel_subscription_not_found_returns_404(client, auth_headers):
    """Verify that cancelling a non-existent subscription returns HTTP 404."""
    with patch("src.services.subscription_service.SubscriptionService.cancel", return_value=None):
        response = await client.post(
            "/api/subscriptions/cancel",
            json={"reason": "testing"},
            headers=auth_headers
        )
        assert response.status_code == 404
        data = response.json()
        assert data["success"] is False


@pytest.mark.asyncio
async def test_cancel_subscription_error_returns_500(client, auth_headers):
    """Verify that a service exception returns HTTP 500 without leaking internal details."""
    with patch(
        "src.services.subscription_service.SubscriptionService.cancel",
        side_effect=Exception("Database connection lost: psycopg2.OperationalError")
    ):
        response = await client.post(
            "/api/subscriptions/cancel",
            json={"reason": "testing"},
            headers=auth_headers
        )
        assert response.status_code == 500
        data = response.json()
        assert data["success"] is False
        # Internal error details should NOT be in the response
        assert "psycopg2" not in str(data)
        assert "Database connection lost" not in str(data)
```

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "subscription or cancel" -v
```

---

## Acceptance Criteria

- [ ] Cancel endpoint returns HTTP 404 when no active subscription is found (not HTTP 200)
- [ ] Cancel endpoint returns HTTP 500 when a service exception occurs (not HTTP 200)
- [ ] Error responses use the standardized `not_found()` and `error()` utilities from `response_utils.py`
- [ ] Internal error messages (`str(e)`) are NOT included in client-facing error responses
- [ ] Internal error messages are logged server-side with full stack trace
- [ ] The `@db_transaction_handler` decorator handles unexpected exceptions (no internal `try/except`)
- [ ] Database transactions are properly rolled back on error (via the decorator)
- [ ] `checkout_routes.py` `str(e)` leakage in `HTTPException.detail` is replaced with generic messages
- [ ] Frontend can reliably distinguish success from failure using HTTP status codes
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** https://developer.mozilla.org/en-US/docs/Web/HTTP/Status — HTTP response status codes reference
- **Security Advisory:** OWASP — Information Exposure Through an Error Message (CWE-209): https://cwe.mitre.org/data/definitions/209.html
- **Migration Guide:** N/A
- **Best Practice Reference:** https://fastapi.tiangolo.com/tutorial/handling-errors/ — FastAPI error handling documentation
- **Related Issues/PRs:** See `db_transaction_handler` in `src/utils/route_decorators.py` (lines 44-233) which already implements the correct error handling pattern

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-132 (No Retry Logic on LemonSqueezy API Calls — cancel calls to LemonSqueezy benefit from retry before reaching the error path), Finding #14 (Internal Error Messages Leaked — overlapping issue with `str(e)` leakage across multiple endpoints)
