# Task 064: Remove Internal Error Details Leaked to Clients via `str(e)`

## Metadata
- **Task ID:** TASK-064
- **Source:** Backend User Management Audit (Finding #10 under P1 High)
- **Audit Report:** `audit-reports/backend-user-management.md`
- **Priority:** P1 High
- **Category:** security
- **Effort Estimate:** medium (1-4 hours)

---

## Description

Across four user management route files (`auth.py`, `user_status.py`, `management.py`, `profile.py`), catch-all exception handlers include raw Python exception strings in client-facing HTTP error responses via `context={"error_details": str(e)}`. The `error()` response utility in `src/utils/response_utils.py` passes the `context` dictionary directly into `create_error_response()`, which serializes it via `response.model_dump()` and returns it as a `JSONResponse` body (lines 208-222). There is no sanitization or filtering of the `context` values — whatever is passed in `context` reaches the client verbatim.

This means that when any unexpected exception occurs in these 13 endpoints, the full Python exception string — which may include database connection details, SQL queries, file paths, module names, internal class names, and stack trace fragments — is returned to the client as part of the JSON error response body.

This is classified as CWE-209 (Generation of Error Message Containing Sensitive Information) and maps to OWASP Top Ten 2021 A04 (Insecure Design). An attacker who triggers errors on these endpoints can harvest internal implementation details to refine further attacks (e.g., learning the database engine, table names, or ORM version from a `SQLAlchemyError` string).

Additionally, `profile.py` has a related but distinct pattern: 5 locations pass `str(e)` into notification payloads (`payload={"user_id": ..., "error": str(e)}`), which are stored in the database via `schedule_if_allowed()` and potentially displayed to the user as in-app notifications. Two of these (lines 334 and 449) are inside `except ResourceNotFoundException:` blocks where `e` is actually unbound (addressed separately in TASK-060), but the remaining three (lines 178, 353, 468) in `except Exception as e:` blocks will store the internal error string in the notification system.

All 13 endpoints already have `logger.error()` calls immediately before the `error()` response, so the exception details are already being logged server-side. The client-facing `context` parameter is purely redundant from a debugging perspective and only serves to leak information.

---

## Current Code

```python
# File: src/api/routes/users/auth.py
# Lines: 551-562 (login endpoint — representative of all 8 instances in auth.py)
    except Exception as e:
        # Rollback transaction on error
        await db.rollback()
        logger.error(f"Login failed: {str(e)}", exc_info=True)
        return error(
            message="Login failed due to server error",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )
```

```python
# File: src/api/routes/users/user_status.py
# Lines: 113-122 (suspend_user — representative of all 4 instances in user_status.py)
    except Exception as e:
        logger.error(f"Error suspending user {user_id}: {str(e)}")
        return error(
            message="Failed to suspend user",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )
```

```python
# File: src/api/routes/users/management.py
# Lines: 447-456 (export_data — 1 instance)
    except Exception as e:
        logger.error(f"Error exporting data for user {current_user.get('identity')}: {str(e)}")
        return error(
            message="Failed to export user data",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )
```

```python
# File: src/api/routes/users/profile.py
# Lines: 344-359 (upload_avatar — except Exception as e handler — notification payload pattern)
    except Exception as e:
        logger.error(f"Error uploading avatar: {str(e)}")
        # Schedule notification
        await schedule_if_allowed(
            db=db,
            user_id=str(user_id),
            background_tasks=background_tasks,
            pref_flag="in_app_notifications",
            message="failed to upload avatar",
            payload={"user_id": str(user_id), "error": str(e)},
            workspace_id=None
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload avatar"
        )
```

---

## Why This Matters (Context & Reasoning)

These 13 endpoints cover core user management operations: login, token refresh, logout, email verification, OAuth login/link/unlink, user suspend/activate/ban, account deactivation, and data export. These are some of the most security-sensitive endpoints in the application because they handle authentication, authorization, and account lifecycle operations.

When an unexpected error occurs (database timeout, ORM error, external service failure), the current code sends the raw Python exception string back to the client. For example, a `sqlalchemy.exc.OperationalError` would expose the database connection string format, table names, and query structure. A `ConnectionRefusedError` would reveal internal hostnames and port numbers. Even a simple `TypeError` reveals internal function signatures and module paths.

This information is invaluable to an attacker performing reconnaissance. Knowing the exact ORM, database engine, table structure, and internal module paths dramatically reduces the effort needed to craft injection attacks or exploit known vulnerabilities in specific library versions.

The `logger.error()` calls already capture the full exception details server-side with proper log levels, so removing the client-facing exposure has zero impact on debugging capability.

---

## Impact

- **Severity:** Internal implementation details (database errors, file paths, module names, query structures) are exposed to any client that triggers an error on these 13 endpoints. This aids attackers in reconnaissance and targeted exploitation.
- **Affected Users/Flows:** Login, token refresh, logout, email verification, resend verification, OAuth login, OAuth link, OAuth unlink, user suspend, user activate, user ban, account deactivation, and data export.
- **Blast Radius:** 13 endpoints across 4 route files in user management. The same pattern also exists in `src/api/security/dependencies.py` (2 instances) and `src/utils/route_decorators.py` (1 conditional instance) — those are outside user management scope but listed in Other Affected Locations.

---

## Recommended Solution

Remove the `context={"error_details": str(e)}` parameter from all `error()` calls in catch-all exception handlers. The `logger.error()` calls already log the exception server-side. For `profile.py` notification payloads, replace `str(e)` with a generic message.

### Step 1: Remove `context` from all 8 `error()` calls in `auth.py`

```python
# File: src/api/routes/users/auth.py
# At lines 555-562, 615-622, 663-670, 710-717, 776-783, 916-923, 997-1004, 1038-1045
# Replace each occurrence of this pattern:
        return error(
            message="<existing message>",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )
# With (simply remove the context line):
        return error(
            message="<existing message>",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )
```

The 8 locations in `auth.py` and their corresponding `message` values:

| Line | Endpoint | Message |
|------|----------|---------|
| 560 | login | `"Login failed due to server error"` |
| 620 | refresh_access_token | `"Failed to refresh token"` |
| 668 | logout_user | `"Logout failed"` |
| 715 | verify_email | `"Failed to verify email"` |
| 781 | resend_verification | `"Failed to resend verification email"` |
| 921 | oauth_login | `"OAuth login failed"` |
| 1002 | link_oauth | `"Failed to link OAuth account"` |
| 1043 | unlink_oauth | `"Failed to unlink OAuth account"` |

### Step 2: Remove `context` from all 4 `error()` calls in `user_status.py`

```python
# File: src/api/routes/users/user_status.py
# At lines 115-122, 210-217, 307-314, 463-470
# Remove the context={"error_details": str(e)} line from each error() call.
```

The 4 locations:

| Line | Endpoint | Message |
|------|----------|---------|
| 120 | suspend_user | `"Failed to suspend user"` |
| 215 | activate_user | `"Failed to activate user"` |
| 312 | ban_user | `"Failed to ban user"` |
| 468 | deactivate_account | `"Failed to deactivate account"` |

### Step 3: Remove `context` from `error()` call in `management.py`

```python
# File: src/api/routes/users/management.py
# Lines: 449-456
# Replace:
        return error(
            message="Failed to export user data",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )
# With:
        return error(
            message="Failed to export user data",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )
```

### Step 4: Replace `str(e)` in `profile.py` notification payloads

```python
# File: src/api/routes/users/profile.py
# At lines 178, 353, 468 (the except Exception as e handlers):
# Replace each:
            payload={"user_id": str(user_id), "error": str(e)},
# With:
            payload={"user_id": str(user_id), "error": "An internal error occurred"},
```

Note: Lines 334 and 449 are in `except ResourceNotFoundException:` blocks where `e` is unbound — these are addressed by TASK-060. After TASK-060 is resolved, verify those lines also use a generic message instead of `str(e)`.

Also replace line 613 (the `except Exception as e` in notification preferences update):

```python
# File: src/api/routes/users/profile.py
# Line 613:
# Replace:
            payload={"user_id": str(user_id), "error": str(e)},
# With:
            payload={"user_id": str(user_id), "error": "An internal error occurred"},
```

---

## Other Affected Locations

The same `context={"error_details": str(e)}` pattern exists outside user management routes:

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/security/dependencies.py` | 83, 188 | `RextAuthenticationException` raised with `context={"error_details": str(e)}` in `get_current_user` and `get_current_user_optional` — these flow through middleware and may appear in auth error responses |
| `src/utils/route_decorators.py` | 218 | `db_transaction_handler` decorator conditionally includes `str(e)` when `include_error_details=True` — this is configurable per-route but defaults are not verified |
| `src/utils/file_upload_utils.py` | 255 | `context={"error": str(e)}` in file upload error handling |
| `src/api/routes/content/modules/sites.py` | 77 | `context={"error": str(e)}` in sites route error handling |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Start the backend server locally.
2. Send a login request with valid credentials but tamper with the database connection (e.g., stop the database temporarily) to trigger an unexpected error.
3. Observe the error response JSON body — it should contain a `context` field with `error_details` containing the raw Python exception string (e.g., database connection error message).

```bash
# Example: trigger a login error and inspect the response
curl -X POST http://localhost:8000/api/v1/user/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@test.com", "password": "test123"}' | python -m json.tool
# Look for "context": {"error_details": "..."} in the response
```

### After Fix (Verify the Solution):
1. Trigger the same error conditions.
2. Verify the error response JSON body does NOT contain `context`, `error_details`, or any raw exception strings.
3. Verify the server logs still contain the full exception details via `logger.error()`.
4. Verify all 13 endpoints return generic error messages without internal details.

### Run Existing Tests:
```bash
cd rext-backend
python -m pytest tests/ -v -k "auth or user_status or management or profile" --no-header
```

---

## Acceptance Criteria

- [ ] All 13 `error()` calls in user management routes no longer include `context={"error_details": str(e)}`
- [ ] All 6 notification payload locations in `profile.py` use generic error messages instead of `str(e)`
- [ ] Error responses return only the generic `message` field (e.g., "Login failed due to server error") with no `context` or `error_details`
- [ ] Server-side `logger.error()` calls remain unchanged — exceptions are still logged for debugging
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [CWE-209: Generation of Error Message Containing Sensitive Information](https://cwe.mitre.org/data/definitions/209.html) — the exact weakness classification for this finding
- **Security Advisory:** [OWASP Top Ten 2021 A04: Insecure Design](https://owasp.org/Top10/A04_2021-Insecure_Design/) — this vulnerability maps to the Insecure Design category
- **Best Practice Reference:** [OWASP Error Handling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html) — guidelines for secure error handling in web applications
- **Migration Guide:** N/A
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None (can be implemented independently)
- **Blocks:** None
- **Related:**
  - TASK-015 (B1 Finding 17): "Login Error Response Leaks Details" — covers the same `auth.py` pattern as P2, scoped to login. If TASK-015 has already been implemented, the 8 `auth.py` locations may already be fixed. The remaining 5 locations in `user_status.py` (4) and `management.py` (1) still need to be addressed.
  - TASK-060 (B3 Finding 3): "Unbound Variable `e` in Exception Handlers" — the `str(e)` references at profile.py:334 and 449 are in `ResourceNotFoundException` handlers where `e` is unbound. TASK-060 fixes the `NameError`; this task ensures the remaining `str(e)` in `except Exception as e:` handlers is also cleaned up.
