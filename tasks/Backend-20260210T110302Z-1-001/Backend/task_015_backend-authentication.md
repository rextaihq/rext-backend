# Task 015: Remove Internal Error Details from Client-Facing Login Responses

## Metadata
- **Task ID:** TASK-015
- **Source:** Backend Authentication & Authorization Audit (Finding #17 under P2 Medium)
- **Audit Report:** `audit-reports/backend-authentication.md`
- **Priority:** P2 Medium
- **Category:** security
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `src/api/routes/users/auth.py` file contains 8 catch-all exception handlers that leak internal error details to the client via the `context={"error_details": str(e)}` parameter in error responses. When an unexpected exception occurs (database error, type error, attribute error, etc.), the Python exception message is serialized as a string and included in the JSON response body sent to the client.

The `error()` function in `src/utils/response_utils.py` passes the `context` parameter directly into the `create_error_response()` Pydantic model, which is then serialized to JSON and returned as the HTTP response body. This means `str(e)` from any exception — including database errors that may contain SQL queries, table names, column names, connection strings, or internal file paths — is exposed to the client.

This is classified as CWE-209 (Generation of Error Message Containing Sensitive Information) and falls under the OWASP Top 10:2025 category A10 (Mishandling of Exceptional Conditions). The `str(e)` from a SQLAlchemy error, for example, can expose the full SQL query, database schema details, and internal parameter values. From a PostgreSQL connection error, it can expose the database hostname and port. From a Python `AttributeError` or `TypeError`, it can expose internal class names, method signatures, and code structure.

The existing global error handler at `src/api/middleware/error_handler.py` does perform some sanitization (checking for keywords like 'cookie', 'session', 'credential', 'private'), but the `str(e)` in these route-level handlers bypasses this sanitization because the error is caught and returned before reaching the global handler.

The same pattern appears in multiple other route files beyond `auth.py`: `user_status.py` (4 occurrences), `management.py` (1 occurrence), `password.py` (1 occurrence using `message=str(e)`), `profile.py` (multiple occurrences), and others. This task focuses on `auth.py` as the primary target, with the other files documented in "Other Affected Locations."

---

## Current Code

```python
# File: src/api/routes/users/auth.py
# Lines: 551-562 (login endpoint — representative example)
    except Exception as e:
        # Rollback transaction on error
        await db.rollback()
        logger.error(f"Login failed: {str(e)}", exc_info=True)
        return error(
            message="Login failed due to server error",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},  # <-- LEAKS INTERNAL DETAILS
            request=request
        )
```

The same pattern repeats at lines 620 (refresh token), 668 (logout), 715 (verify email), 781 (resend verification), 921 (OAuth login), 1002 (OAuth link), and 1043 (OAuth unlink).

---

## Why This Matters (Context & Reasoning)

Error message leakage is a reconnaissance tool for attackers. By triggering various error conditions (malformed input, invalid tokens, concurrent requests causing race conditions), an attacker can collect internal details about the application's architecture, database schema, library versions, and internal code structure. This information feeds into more targeted attacks such as SQL injection, where knowledge of table and column names significantly reduces the attack surface to explore.

The authentication routes are particularly sensitive because they are publicly accessible (login, registration, password reset) and handle security-critical operations. An attacker can trigger errors on these endpoints without authentication, making them an ideal reconnaissance target.

All 8 occurrences in `auth.py` follow the same pattern: a catch-all `except Exception as e:` block that includes `str(e)` in the client response while also properly logging it server-side. The fix is to remove the `context` parameter from the client response while keeping the `logger.error()` call that already logs the full error server-side with `exc_info=True`.

---

## Impact

- **Severity:** Internal error details (SQL queries, table names, file paths, class names) are exposed to any client triggering a 500 error on authentication endpoints. This aids reconnaissance for targeted attacks.
- **Affected Users/Flows:** All authentication flows — login, token refresh, logout, email verification, OAuth login/link/unlink. These endpoints are publicly accessible.
- **Blast Radius:** Extends beyond `auth.py` — the same pattern exists in 13+ locations across `user_status.py`, `management.py`, and `password.py`. However, `auth.py` is the highest-priority target due to its public exposure.

---

## Recommended Solution

### Step 1: Remove `context={"error_details": str(e)}` from all 8 catch-all handlers in `auth.py`

For each of the 8 occurrences, remove the `context` parameter from the `error()` call. The `logger.error()` call on the line above already logs the full error details server-side with stack trace (`exc_info=True`), so no information is lost.

```python
# File: src/api/routes/users/auth.py

# Line 555-562 (login) — replace with:
        return error(
            message="Login failed due to server error",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )

# Line 615-622 (refresh token) — replace with:
        return error(
            message="Failed to refresh token",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )

# Line 663-670 (logout) — replace with:
        return error(
            message="Logout failed",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )

# Line 710-717 (verify email) — replace with:
        return error(
            message="Failed to verify email",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )

# Line 776-783 (resend verification) — replace with:
        return error(
            message="Failed to resend verification email",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )

# Line 916-923 (OAuth login) — replace with:
        return error(
            message="OAuth login failed",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )

# Line 997-1004 (OAuth link) — replace with:
        return error(
            message="Failed to link OAuth account",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )

# Line 1038-1045 (OAuth unlink) — replace with:
        return error(
            message="Failed to unlink OAuth account",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )
```

### Step 2: Verify the `logger.error()` call preceding each `return error(...)` is preserved

Each catch-all handler already has a `logger.error()` call with `exc_info=True` on the line before the `return error(...)`. This must remain — it is the correct location for the full error details (server-side logs only). Example:

```python
    except Exception as e:
        await db.rollback()
        logger.error(f"Login failed: {str(e)}", exc_info=True)  # KEEP THIS — server-side only
        return error(
            message="Login failed due to server error",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            # context removed — no longer leaks to client
            request=request
        )
```

---

## Other Affected Locations

The same `context={"error_details": str(e)}` pattern exists in these additional files. They should be addressed in follow-up tasks or as part of this task if scope permits:

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/routes/users/user_status.py` | 120, 215, 312, 468 | 4 catch-all handlers leak `str(e)` in suspend/unsuspend/ban/unban endpoints |
| `src/api/routes/users/management.py` | 454 | 1 catch-all handler leaks `str(e)` in user management endpoint |
| `src/api/routes/users/password.py` | 181 | Uses `message=str(e)` directly as the error message (even worse — the error string IS the message) |
| `src/api/routes/subscriptions/license_routes.py` | 135, 140 | Leaks `str(e)` in error context and HTTPException detail |
| `src/api/routes/email/preview.py` | 146, 251 | Leaks `str(e)` in HTTPException detail for email preview endpoints |
| `src/api/routes/subscriptions/subscription_routes.py` | 489 | Leaks `str(e)` as `"message": str(e)` in response dictionary |
| `src/api/routes/workspaces/workspace_knowledge.py` | 204, 393, 575 | Leaks `str(e)` in error message for knowledge endpoints |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Send a malformed login request that triggers an internal error (e.g., corrupt the database connection temporarily, or send a request with a payload that causes a TypeError)
2. Observe the 500 error response body — it should contain `"error_details"` with internal error information
3. Example: `curl -X POST /api/user/login -H "Content-Type: application/json" -d '{"email": "test@test.com", "password": "test"}'` — if the database is down, the response will contain the connection error string

### After Fix (Verify the Solution):
1. Trigger the same error condition
2. Verify the 500 response body does NOT contain `"error_details"` or any `context` field with internal information
3. Verify the error IS logged server-side by checking the application logs (look for `logger.error` entries with `exc_info`)
4. The response should contain only: `"message": "Login failed due to server error"`, the error code, status, and request ID

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -v -k "login or auth or refresh or logout or oauth" --no-header
```

---

## Acceptance Criteria

- [ ] All 8 `context={"error_details": str(e)}` occurrences removed from `auth.py`
- [ ] The `logger.error()` calls with `exc_info=True` are preserved (server-side logging intact)
- [ ] 500 error responses from auth endpoints no longer contain `error_details` in the response body
- [ ] Error responses still contain the generic error message (e.g., "Login failed due to server error")
- [ ] Error responses still contain the request ID for correlation with server logs
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [CWE-209: Generation of Error Message Containing Sensitive Information](https://cwe.mitre.org/data/definitions/209.html) — CWE classification for this vulnerability type
- **Security Advisory:** [OWASP Top 10:2025 — A10: Mishandling of Exceptional Conditions](https://owasp.org/Top10/2025/A10_2025-Mishandling_of_Exceptional_Conditions/) — the 2025 OWASP category that covers CWE-209
- **Migration Guide:** N/A
- **Best Practice Reference:** [Snyk Learn: Error Messages with Sensitive Information](https://learn.snyk.io/lesson/error-message-with-sensitive-information/) — practical guide on identifying and fixing CWE-209 vulnerabilities
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-006 (forgot-password reveals user existence — same information leakage category), B3 Finding 10 (Internal Error Details Leaked to Clients via `str(e)` — same pattern in user management routes), B5 Finding 14 (Internal Error Messages Leaked to Clients — same pattern in subscription routes)
