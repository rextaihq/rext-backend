# Task 127: Internal Error Messages Leaked to Clients via str(e)

## Metadata
- **Task ID:** TASK-127
- **Source:** B5 - Subscription & Billing (Finding #14 under P1 High)
- **Audit Report:** `audit-reports/backend-subscription-billing.md`
- **Priority:** P1 High
- **Category:** security
- **Effort Estimate:** medium (1-4 hours)

---

## Description

Multiple route handlers across the subscription and billing endpoints include raw Python exception messages (`str(e)`) in client-facing HTTP error responses. This leaks internal implementation details to API consumers, including database error messages, Python traceback fragments, third-party service names, internal file paths, and SQL query fragments.

The pattern appears in at least 6 locations across 4 files in the billing subsystem:

1. **`subscription_routes.py` line 489** — Cancel endpoint catches all exceptions and returns the raw error message in an HTTP 200 response body: `"message": str(e)`. This is doubly problematic: not only does it leak the error, it returns it with a 200 status code (see TASK-130, Finding 13).

2. **`checkout_routes.py` line 108** — Portal session endpoint: `detail=f"Failed to create portal session: {str(e)}"` in an HTTPException.

3. **`checkout_routes.py` line 272** — Cancel subscription endpoint: `detail=f"Failed to cancel subscription: {str(e)}"`.

4. **`license_routes.py` line 140** — License validation endpoint: `detail=f"License validation failed: {str(e)}"`.

5. **`admin/refund_routes.py` line 326** — Admin refund creation: `detail=f"Failed to create refund: {str(e)}"`.

6. **`webhook_routes.py` line 76** — Only in server-side logging (acceptable), but the pattern is inconsistent.

According to OWASP's Error Handling guidance (CWE-209: Generation of Error Message Containing Sensitive Information), error messages returned to clients should never contain internal system details. The exception messages from libraries like SQLAlchemy, httpx, and LemonSqueezy SDK can contain database table names, column names, connection strings, API endpoint URLs, and authentication token fragments.

For example, a SQLAlchemy error might reveal: `"(sqlalchemy.exc.IntegrityError) duplicate key value violates unique constraint "user_subscriptions_provider_subscription_id_key"`. This tells an attacker the exact table name, constraint name, and column name — all useful for SQL injection attempts or understanding the database schema.

The project already has a `db_transaction_handler` decorator (in `src/utils/route_decorators.py`) that handles exceptions generically without leaking details. Many of the affected endpoints already use this decorator, but they ALSO have their own try/except blocks that catch exceptions BEFORE the decorator can handle them, and those inner catch blocks include `str(e)`.

---

## Current Code

```python
# File: rext-backend/src/api/routes/subscriptions/subscription_routes.py
# Lines: 482-493
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
# File: rext-backend/src/api/routes/subscriptions/checkout_routes.py
# Lines: 104-109
    except Exception as e:
        logger.error(f"Failed to create portal session: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create portal session: {str(e)}"
        )
```

```python
# File: rext-backend/src/api/routes/subscriptions/license_routes.py
# Lines: 130-141
    except Exception as e:
        logger.error(
            f"License validation failed: {str(e)}",
            extra={
                "license_key_prefix": license_data.license_key[:8],
                "error": str(e)
            }
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"License validation failed: {str(e)}"
        )
```

```python
# File: rext-backend/src/api/routes/subscriptions/admin/refund_routes.py
# Lines: 319-327
    except Exception as e:
        logger.error(
            f"Failed to create refund for order {lemonsqueezy_order_id}: {str(e)}",
            extra={"admin_user_id": str(admin_user_id), "error": str(e)}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create refund: {str(e)}"
        )
```

---

## Why This Matters (Context & Reasoning)

The billing system handles sensitive financial operations — subscription management, payment processing, license validation, and refunds. These endpoints interact with external payment providers (LemonSqueezy), the database, and internal services. When any of these fail, the exception message often contains:

- **Database details:** Table names, constraint names, column names from SQLAlchemy errors
- **API details:** LemonSqueezy API endpoint URLs, response bodies, HTTP status codes
- **Internal paths:** Python module paths from import errors or file-related exceptions
- **Connection details:** Redis/database connection strings from connection errors

This information is valuable to attackers for reconnaissance. It maps the internal architecture, reveals which third-party services are used, and can expose database schema details useful for SQL injection.

The proper pattern is to log the full exception server-side (which is already done in most cases) and return a generic, user-friendly message to the client. The `db_transaction_handler` decorator already implements this correctly — it logs the full error and returns `"Failed to {operation_name}"` without including `str(e)`. The problem is that some endpoints have redundant try/except blocks that catch exceptions before the decorator can handle them.

---

## Impact

- **Severity:** Information leakage enables attacker reconnaissance. Internal system details (database schema, API endpoints, service names) are exposed in production error responses. Classified as CWE-209.
- **Affected Users/Flows:** Any API consumer who triggers an error on subscription cancel, portal session creation, license validation, checkout, or admin refund endpoints.
- **Blast Radius:** 6+ endpoints across 4 route files in the billing subsystem. The pattern may also exist in other subsystems (see Other Affected Locations).

---

## Recommended Solution

For each affected endpoint, either (a) remove the redundant try/except block and let the `db_transaction_handler` decorator handle errors, or (b) keep the try/except but replace `str(e)` with a generic message in the client response while keeping `str(e)` in server-side logging.

### Step 1: Fix subscription_routes.py cancel endpoint

```python
# File: rext-backend/src/api/routes/subscriptions/subscription_routes.py
# Replace the except block at lines 482-493 with:
    except Exception as e:
        logger.error(
            f"Failed to cancel subscription: {str(e)}",
            extra={"user_id": str(user_id)},
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel subscription. Please try again or contact support."
        )
```

### Step 2: Fix checkout_routes.py portal session

```python
# File: rext-backend/src/api/routes/subscriptions/checkout_routes.py
# Replace the except block at lines 104-109 with:
    except Exception as e:
        logger.error(
            f"Failed to create portal session: {str(e)}",
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create billing portal session. Please try again or contact support."
        )
```

### Step 3: Fix checkout_routes.py cancel subscription

```python
# File: rext-backend/src/api/routes/subscriptions/checkout_routes.py
# Replace the except block at lines 268-273 with:
    except Exception as e:
        logger.error(
            f"Failed to cancel subscription: {str(e)}",
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel subscription. Please try again or contact support."
        )
```

### Step 4: Fix license_routes.py validate

```python
# File: rext-backend/src/api/routes/subscriptions/license_routes.py
# Replace the except block at lines 130-141 with:
    except Exception as e:
        logger.error(
            f"License validation failed: {str(e)}",
            extra={
                "license_key_prefix": license_data.license_key[:8],
                "error": str(e)
            },
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="License validation failed. Please verify your license key and try again."
        )
```

### Step 5: Fix admin/refund_routes.py

```python
# File: rext-backend/src/api/routes/subscriptions/admin/refund_routes.py
# Replace the except block at lines 319-327 with:
    except Exception as e:
        logger.error(
            f"Failed to create refund for order {lemonsqueezy_order_id}: {str(e)}",
            extra={"admin_user_id": str(admin_user_id), "error": str(e)},
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create refund. Please check the order ID and try again."
        )
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/api/routes/subscriptions/checkout_routes.py` | `179` | `logger.warning(f"Failed to generate portal URL: {str(e)}")` — logging only, OK |
| `rext-backend/src/api/routes/subscriptions/webhook_routes.py` | `76` | `f"LemonSqueezy webhook background processing failed: {str(e)}"` — logging only, OK |
| `rext-backend/src/api/routes/subscriptions/subscription_routes.py` | `707-708` | `str(e)` in logger only — OK, but uses `str(e)` in `extra` dict |
| `rext-backend/src/utils/route_decorators.py` | `216-221` | `db_transaction_handler` includes `str(e)` in context when `include_error_details=True` — should verify this doesn't reach clients |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Call the portal session endpoint with an invalid customer ID to trigger an error:
   ```bash
   curl -X GET http://localhost:2024/api/v1/subscriptions/portal \
     -H "Authorization: Bearer <valid-token>"
   ```
2. Observe the error response contains internal details like LemonSqueezy API error messages

### After Fix (Verify the Solution):
1. Trigger the same error
2. Verify the response contains only: `"Failed to create billing portal session. Please try again or contact support."`
3. Verify the full error details appear in server-side logs (stdout/structured logs)

### Edge Cases to Test:
- Database connection error → should return generic message, not connection string
- LemonSqueezy API timeout → should return generic message, not URL/timeout details
- Invalid UUID parameter → should return 422 validation error (FastAPI handles this), not internal error

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "subscription or license or checkout or refund" -v
```

---

## Acceptance Criteria

- [ ] No `str(e)` appears in any client-facing response body across billing route files
- [ ] All error responses use generic, user-friendly messages
- [ ] Server-side logging still includes full error details with `exc_info=True`
- [ ] The `db_transaction_handler` decorator's `include_error_details` parameter is verified to not expose `str(e)` to clients in production
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [FastAPI Error Handling](https://fastapi.tiangolo.com/tutorial/handling-errors/) — FastAPI's recommended patterns for error responses
- **Security Advisory:** [CWE-209: Generation of Error Message Containing Sensitive Information](https://cwe.mitre.org/data/definitions/209.html) — MITRE classification for this vulnerability
- **Best Practice Reference:** [OWASP Error Handling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html) — OWASP guidance on secure error handling
- **Migration Guide:** N/A
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-015 (Login Error Response Leaks Details from B1), TASK-064 (Internal Error Details Leaked via `str(e)` from B3), TASK-104 (Inconsistent Error Handling from B4)
