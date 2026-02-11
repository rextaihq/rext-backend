# Task 059: Fix 7 Non-Existent ErrorCode Enum Values Used in 22 Locations

## Metadata
- **Task ID:** TASK-059
- **Source:** Backend User Management Audit (Finding #1 under P0 Critical)
- **Audit Report:** `audit-reports/backend-user-management.md`
- **Priority:** P0 Critical
- **Category:** bug
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `ErrorCode` enum defined in `src/api/schema/response_schemas.py` is the single source of truth for all error codes used in API error responses. However, 7 enum values that do not exist in this enum are referenced across 22 call sites in 5 user management route files: `password.py`, `profile.py`, `user_status.py`, `management.py`, and `auth.py`.

When any of these 22 error paths is triggered at runtime, Python raises `AttributeError: 'INVALID_INPUT' is not a member of 'ErrorCode'` because accessing a non-existent member on a `str`-based `Enum` subclass raises `AttributeError`. This means that instead of returning the intended 4xx error response (e.g., 400 Validation Error, 401 Unauthorized, 403 Forbidden, 404 Not Found), FastAPI's exception handler catches the unhandled `AttributeError` and returns a generic `500 Internal Server Error`. The client receives no useful error information, and the actual validation/permission/authentication issue is masked.

The 7 non-existent values and their correct replacements are:

| Non-Existent Value | Correct Enum Member | Occurrences |
|---|---|---|
| `ErrorCode.INVALID_INPUT` | `ErrorCode.INVALID_VALUE` | 12 |
| `ErrorCode.VALIDATION_ERROR` | `ErrorCode.VALIDATION_FAILED` | 2 |
| `ErrorCode.AUTHENTICATION_FAILED` | `ErrorCode.UNAUTHORIZED` | 1 |
| `ErrorCode.NOT_FOUND` | `ErrorCode.RESOURCE_NOT_FOUND` | 2 |
| `ErrorCode.PERMISSION_DENIED` | `ErrorCode.INSUFFICIENT_PERMISSIONS` | 3 |
| `ErrorCode.AUTHENTICATION_ERROR` | `ErrorCode.UNAUTHORIZED` | 1 |
| `ErrorCode.AUTHORIZATION_ERROR` | `ErrorCode.FORBIDDEN` | 1 |

The actual `ErrorCode` enum defines `INVALID_VALUE = "invalid_value"`, `VALIDATION_FAILED = "validation_failed"`, `UNAUTHORIZED = "unauthorized"`, `RESOURCE_NOT_FOUND = "resource_not_found"`, `INSUFFICIENT_PERMISSIONS = "insufficient_permissions"`, and `FORBIDDEN = "forbidden"` — these are the correct members to use. The non-existent values appear to be common naming conventions from other frameworks that were used without verifying against the project's actual enum definition.

---

## Current Code

```python
# File: src/api/routes/users/password.py
# Line 150 — reset_password endpoint, invalid token error
code=ErrorCode.INVALID_INPUT,

# Line 182 — reset_password endpoint, ResourceNotFoundException handler
code=ErrorCode.INVALID_INPUT,

# Line 270 — change_password endpoint, RextValidationException handler
code=ErrorCode.INVALID_INPUT,

# Line 314 — verify_password endpoint, missing password
code=ErrorCode.VALIDATION_ERROR,

# Line 327 — verify_password endpoint, invalid password
code=ErrorCode.AUTHENTICATION_FAILED,

# Line 342 — verify_password endpoint, ResourceNotFoundException handler
code=ErrorCode.NOT_FOUND,
```

```python
# File: src/api/routes/users/profile.py
# Line 211 — upload_avatar, invalid file type
code=ErrorCode.INVALID_INPUT,

# Line 225 — upload_avatar, file too large
code=ErrorCode.INVALID_INPUT,

# Line 243 — upload_avatar, invalid image content
code=ErrorCode.INVALID_INPUT,

# Line 254 — upload_avatar, SVG blocked
code=ErrorCode.INVALID_INPUT,

# Line 650 — deactivate_account, confirmation not set
code=ErrorCode.INVALID_INPUT,

# Line 661 — deactivate_account, invalid password
code=ErrorCode.AUTHENTICATION_ERROR,

# Line 674 — deactivate_account, already deactivated
code=ErrorCode.INVALID_INPUT,
```

```python
# File: src/api/routes/users/user_status.py
# Line 51 — suspend_user, admin permission check
code=ErrorCode.PERMISSION_DENIED,

# Line 148 — activate_user, admin permission check
code=ErrorCode.PERMISSION_DENIED,

# Line 243 — ban_user, admin permission check
code=ErrorCode.PERMISSION_DENIED,

# Line 350 — deactivate_user, already deactivated check
code=ErrorCode.INVALID_INPUT,

# Line 386 — deactivate_user, active subscriptions check
code=ErrorCode.VALIDATION_ERROR,
```

```python
# File: src/api/routes/users/management.py
# Line 161 — delete_user, manual permission check
code=ErrorCode.AUTHORIZATION_ERROR,

# Line 191 — delete_user, ResourceNotFoundException handler
code=ErrorCode.NOT_FOUND,
```

```python
# File: src/api/routes/users/auth.py
# Line 594 — refresh_token, missing refresh token
code=ErrorCode.INVALID_INPUT,

# Line 742 — resend_verification, missing email
code=ErrorCode.INVALID_INPUT,
```

---

## Why This Matters (Context & Reasoning)

The `error()` response utility from `src/utils/response_utils.py` is the project's standardized mechanism for returning structured error responses. It takes an `ErrorCode` enum value, a message, status code, and severity level. Every user-facing error path in the user management routes relies on this utility to produce consistent, client-parseable error responses.

When 22 out of these error paths crash with `AttributeError` instead of returning the intended error, the following consequences occur:
- **Password reset failures** return 500 instead of 400 (bad token) or 404 (user not found)
- **Avatar upload validation errors** (wrong file type, too large, invalid content) return 500 instead of 400
- **Account deactivation** fails with 500 when the user enters a wrong password (should be 401) or is already deactivated (should be 400)
- **Admin actions** (suspend, ban, activate users) return 500 instead of 403 when non-admin users attempt them
- **User deletion** returns 500 instead of 403 (no permission) or 404 (user not found)

This makes error handling completely non-functional for these 22 paths, which are among the most commonly triggered error flows in the application.

---

## Impact

- **Severity:** All 22 affected error paths return 500 Internal Server Error instead of the correct 4xx status code, making client-side error handling impossible for these flows.
- **Affected Users/Flows:** Password management (reset, change, verify), avatar upload, account deactivation, admin user management (suspend/ban/activate/delete), token refresh, email verification resend.
- **Blast Radius:** 5 route files across the entire user management module. The same anti-pattern also exists in `notification_routes.py` (6 locations) and `workspace_members.py` (1 location) outside the user management scope.

---

## Recommended Solution

Replace each non-existent `ErrorCode` value with the correct enum member. The replacements are mechanical — the error semantics remain the same, only the enum member name changes.

### Step 1: Fix `password.py` (6 replacements)

```python
# File: src/api/routes/users/password.py

# Line 150: Replace ErrorCode.INVALID_INPUT with ErrorCode.INVALID_VALUE
code=ErrorCode.INVALID_VALUE,

# Line 182: Replace ErrorCode.INVALID_INPUT with ErrorCode.INVALID_VALUE
code=ErrorCode.INVALID_VALUE,

# Line 270: Replace ErrorCode.INVALID_INPUT with ErrorCode.INVALID_VALUE
code=ErrorCode.INVALID_VALUE,

# Line 314: Replace ErrorCode.VALIDATION_ERROR with ErrorCode.VALIDATION_FAILED
code=ErrorCode.VALIDATION_FAILED,

# Line 327: Replace ErrorCode.AUTHENTICATION_FAILED with ErrorCode.UNAUTHORIZED
code=ErrorCode.UNAUTHORIZED,

# Line 342: Replace ErrorCode.NOT_FOUND with ErrorCode.RESOURCE_NOT_FOUND
code=ErrorCode.RESOURCE_NOT_FOUND,
```

### Step 2: Fix `profile.py` (7 replacements)

```python
# File: src/api/routes/users/profile.py

# Lines 211, 225, 243, 254, 650, 674: Replace ErrorCode.INVALID_INPUT with ErrorCode.INVALID_VALUE
code=ErrorCode.INVALID_VALUE,

# Line 661: Replace ErrorCode.AUTHENTICATION_ERROR with ErrorCode.UNAUTHORIZED
code=ErrorCode.UNAUTHORIZED,
```

### Step 3: Fix `user_status.py` (5 replacements)

```python
# File: src/api/routes/users/user_status.py

# Lines 51, 148, 243: Replace ErrorCode.PERMISSION_DENIED with ErrorCode.INSUFFICIENT_PERMISSIONS
code=ErrorCode.INSUFFICIENT_PERMISSIONS,

# Line 350: Replace ErrorCode.INVALID_INPUT with ErrorCode.INVALID_VALUE
code=ErrorCode.INVALID_VALUE,

# Line 386: Replace ErrorCode.VALIDATION_ERROR with ErrorCode.VALIDATION_FAILED
code=ErrorCode.VALIDATION_FAILED,
```

### Step 4: Fix `management.py` (2 replacements)

```python
# File: src/api/routes/users/management.py

# Line 161: Replace ErrorCode.AUTHORIZATION_ERROR with ErrorCode.FORBIDDEN
code=ErrorCode.FORBIDDEN,

# Line 191: Replace ErrorCode.NOT_FOUND with ErrorCode.RESOURCE_NOT_FOUND
code=ErrorCode.RESOURCE_NOT_FOUND,
```

### Step 5: Fix `auth.py` (2 replacements)

```python
# File: src/api/routes/users/auth.py

# Lines 594, 742: Replace ErrorCode.INVALID_INPUT with ErrorCode.INVALID_VALUE
code=ErrorCode.INVALID_VALUE,
```

No new imports are needed — `ErrorCode` is already imported in all affected files, and the replacement values (`INVALID_VALUE`, `VALIDATION_FAILED`, `UNAUTHORIZED`, `RESOURCE_NOT_FOUND`, `INSUFFICIENT_PERMISSIONS`, `FORBIDDEN`) all exist in the same enum.

---

## Other Affected Locations

The same non-existent `ErrorCode` values are used outside the user management routes. These are in scope for other audit reports but should be fixed with the same approach:

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/routes/notifications/notification_routes.py` | 79, 176, 219, 299, 342, 452 | `ErrorCode.INVALID_INPUT` used in 6 notification route error paths |
| `src/api/routes/workspaces/workspace_members.py` | 262 | `ErrorCode.VALIDATION_ERROR` used in workspace member validation |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Start the backend server: `cd rext-backend && uvicorn src.main:app --reload`
2. Attempt a password reset with an invalid token:
   ```bash
   curl -X POST http://localhost:8000/api/v1/user/password/reset \
     -H "Content-Type: application/json" \
     -d '{"token": "invalid-token", "new_password": "NewPass123!"}'
   ```
3. Observe a 500 Internal Server Error response instead of the expected 400 error with `ErrorCode.INVALID_VALUE`.
4. Check server logs for `AttributeError: 'INVALID_INPUT' is not a member of 'ErrorCode'`.

### After Fix (Verify the Solution):
1. Repeat the same request as above.
2. Observe a 400 Bad Request response with the JSON body containing `"code": "invalid_value"` and `"message": "Invalid or expired reset token"`.
3. Verify no `AttributeError` appears in the server logs.

### Additional Verification:
4. As a non-admin user, attempt to suspend another user to verify `INSUFFICIENT_PERMISSIONS` is returned (403):
   ```bash
   curl -X POST http://localhost:8000/api/v1/user/{user_id}/suspend \
     -H "Authorization: Bearer <non-admin-token>" \
     -H "Content-Type: application/json" \
     -d '{"reason": "test"}'
   ```
5. Upload an invalid file (e.g., a `.txt` file renamed to `.jpg`) to the avatar endpoint to verify `INVALID_VALUE` is returned (400).

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -v -k "user" --tb=short
```

---

## Acceptance Criteria

- [ ] All 22 occurrences of non-existent `ErrorCode` values are replaced with valid enum members
- [ ] `ErrorCode.INVALID_INPUT` → `ErrorCode.INVALID_VALUE` in all 12 locations
- [ ] `ErrorCode.VALIDATION_ERROR` → `ErrorCode.VALIDATION_FAILED` in 2 locations
- [ ] `ErrorCode.AUTHENTICATION_FAILED` → `ErrorCode.UNAUTHORIZED` in 1 location
- [ ] `ErrorCode.NOT_FOUND` → `ErrorCode.RESOURCE_NOT_FOUND` in 2 locations
- [ ] `ErrorCode.PERMISSION_DENIED` → `ErrorCode.INSUFFICIENT_PERMISSIONS` in 3 locations
- [ ] `ErrorCode.AUTHENTICATION_ERROR` → `ErrorCode.UNAUTHORIZED` in 1 location
- [ ] `ErrorCode.AUTHORIZATION_ERROR` → `ErrorCode.FORBIDDEN` in 1 location
- [ ] All affected error paths return the correct HTTP status codes (400, 401, 403, 404) instead of 500
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Python Enum documentation — Ensuring unique members](https://docs.python.org/3.11/library/enum.html#ensuring-unique-enumeration-values)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [FastAPI Error Handling — HTTPException](https://fastapi.tiangolo.com/tutorial/handling-errors/)
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-015 (B1 — Login Error Response Leaks Details — same `error()` utility pattern)
