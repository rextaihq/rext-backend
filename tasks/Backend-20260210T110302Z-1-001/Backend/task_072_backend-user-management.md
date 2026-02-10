# Task 072: 5 Different Error Handling Patterns Across User Management Routes

## Metadata
- **Task ID:** TASK-072
- **Source:** B3 - User Management (Finding #12 under P1 High)
- **Audit Report:** `audit-reports/backend-user-management.md`
- **Priority:** P1 High
- **Category:** code-quality
- **Effort Estimate:** large (4+ hours)

---

## Description

The user management route files use five distinct error handling patterns, creating an inconsistent API that returns different error response formats depending on which endpoint is called. This makes it impossible for frontend clients to rely on a single error schema and complicates debugging, monitoring, and error recovery logic.

The five patterns identified across the 18 route files in `src/api/routes/users/` are:

1. **Manual try/catch + `error()` utility** — Used in `profile.py`, `management.py`, `user_status.py`. Routes wrap logic in `try/except` blocks and return structured responses via the `error()` helper from `response_utils`, which includes `ErrorCode`, `ErrorSeverity`, and request context. This produces the project's standardized error envelope.

2. **`@db_transaction_handler` decorator** — Used in `sessions.py`, `roles.py`, `admin.py`, `user_security.py`. The decorator (defined in `src/utils/route_decorators.py` lines 44-233) automatically wraps the route in try/catch, handles commits/rollbacks, and formats success/error responses. This is the cleanest pattern — routes contain zero error handling boilerplate.

3. **Middleware-caught service exceptions** — Used partially in `sessions.py` where `RextValidationException` is raised and caught by the global `ErrorHandlerMiddleware` (in `src/api/middleware/error_handler.py`). The middleware converts it to a standardized error response.

4. **Direct `HTTPException`** — Used in `email_preferences.py`, `onboarding.py`. Routes raise FastAPI's native `HTTPException`, which produces the default FastAPI error format `{"detail": "..."}` — a completely different schema from the project's standardized `error()` envelope. These responses lack `ErrorCode`, `ErrorSeverity`, request ID tracking, and structured metadata.

5. **Mixed patterns within the same file** — `profile.py` uses Pattern 1 (`error()` utility) for some endpoints and Pattern 4 (`raise HTTPException`) for others (e.g., avatar upload error at line 356 and avatar delete error). This means the same route file returns two different error formats depending on which endpoint fails.

The project has invested in a comprehensive error handling infrastructure: a custom exception hierarchy (18+ exception types in `src/api/middleware/exceptions.py`), the `@db_transaction_handler` decorator, and the `ErrorHandlerMiddleware`. Patterns 1, 4, and 5 bypass this infrastructure partially or completely, creating inconsistency and duplicating error handling logic that the decorator already provides.

---

## Current Code

### Pattern 1 — Manual try/catch + `error()` (user_status.py):
```python
# File: rext-backend/src/api/routes/users/user_status.py
# Lines: 28-50 (simplified)
@router.post("/{user_id}/suspend", response_model=UserStatusResponse)
@require_permissions("user.update")
async def suspend_user(
    user_id: str,
    request: Request,
    status_data: UserStatusRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    try:
        if not is_admin(current_user):
            return error(
                message="Insufficient permissions. Admin role required.",
                code=ErrorCode.FORBIDDEN,
                status_code=403,
                severity=ErrorSeverity.HIGH,
                request=request
            )
        # ... business logic ...
    except Exception as e:
        logger.error(f"Error suspending user: {str(e)}")
        raise
```

### Pattern 2 — `@db_transaction_handler` (sessions.py):
```python
# File: rext-backend/src/api/routes/users/sessions.py
# Lines: 20-58
@router.get("/sessions")
@require_permissions("user.read", workspace_scoped=False)
@db_transaction_handler("list user sessions", auto_commit=False)
async def list_user_sessions(
    request: Request,
    current_user: dict = Depends(get_current_user),
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_async_db)
) -> dict:
    """List all active sessions for the current user."""
    # No try/catch needed — decorator handles everything
    user_uuid = UUID(str(current_user.get("identity")))
    # ... business logic returns plain dict ...
    return {
        "sessions": sessions,
        "total_count": len(sessions),
        "active_count": active_count,
    }
```

### Pattern 4 — Direct `HTTPException` (email_preferences.py):
```python
# File: rext-backend/src/api/routes/users/email_preferences.py
# Lines: 66-87
@router.get("/")
async def get_preferences(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    try:
        user_id = UUID(current_user["identity"])
        service = EmailPreferencesService(db)
        prefs = await service.get_or_create_preferences(user_id, db)
        return success(data=prefs.to_dict(), message="Email preferences retrieved successfully")
    except Exception as e:
        logger.error(f"Failed to get email preferences: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve email preferences")
```

### Pattern 5 — Mixed patterns (profile.py):
```python
# File: rext-backend/src/api/routes/users/profile.py
# Line 241 uses error() utility (Pattern 1):
            return error(
                message="Invalid image file...",
                code=ErrorCode.INVALID_INPUT,
                status_code=400,
                severity=ErrorSeverity.MEDIUM,
                request=request
            )

# Line 356 uses HTTPException (Pattern 4):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload avatar"
        )
```

---

## Why This Matters (Context & Reasoning)

API consumers (the React frontend) need to parse error responses to display appropriate messages to users, handle retries, and implement error recovery flows. When the same API returns `{"success": false, "error": {"code": "...", "message": "...", "severity": "..."}}` from one endpoint and `{"detail": "..."}` from another, the frontend must implement multiple parsing strategies or risk showing raw error objects to users.

The project has already invested significantly in standardized error handling infrastructure. The `@db_transaction_handler` decorator (Pattern 2) provides:
- Automatic transaction commit on success, rollback on failure
- Standardized success/error response formatting via `success()` / `error()` utilities
- Structured logging with operation context
- Proper exception re-raising for middleware to handle

Routes using Pattern 2 are consistently shorter, cleaner, and produce uniform error responses. Routes using Patterns 1, 4, or 5 duplicate this logic manually (and inconsistently).

Standardizing on Pattern 2 + Pattern 3 (decorator + service exceptions) will:
- Reduce code duplication across route files
- Ensure all error responses follow the same schema
- Make monitoring and alerting more reliable (consistent error codes)
- Simplify the frontend error handling logic

---

## Impact

- **Severity:** Inconsistent API error response format. Frontend cannot rely on a single error schema, leading to unreliable error display and recovery. Some errors leak internal details via `str(e)`, others return generic messages.
- **Affected Users/Flows:** All user management operations — profile, avatar, user status, email preferences, onboarding, sessions, roles, admin operations.
- **Blast Radius:** All 18 route files in `src/api/routes/users/`. The inconsistency affects every user management endpoint to varying degrees.

---

## Recommended Solution

Standardize all user management routes on Pattern 2 (`@db_transaction_handler`) combined with Pattern 3 (service exceptions caught by middleware). This is a large refactoring task that should be done file-by-file.

### General approach for each file:

1. Add `@db_transaction_handler` decorator to each route function
2. Remove manual `try/except` blocks
3. Replace `return error(...)` calls with `raise` of appropriate custom exceptions from `src/api/middleware/exceptions.py`
4. Replace `raise HTTPException(...)` with the appropriate custom exception
5. Let the route return plain data dicts — the decorator wraps them in `success()`
6. Remove unused `error` import from `response_utils` after conversion

### Step 1: Convert `email_preferences.py` (Pattern 4 → Pattern 2)

```python
# File: rext-backend/src/api/routes/users/email_preferences.py
# Add imports at top:
from fastapi import APIRouter, Depends, Request
from src.utils.route_decorators import db_transaction_handler, require_permissions

# Convert get_preferences endpoint:
@router.get("/")
@db_transaction_handler("get email preferences", auto_commit=False)
async def get_preferences(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Get user's email preferences."""
    user_id = UUID(current_user["identity"])
    service = EmailPreferencesService(db)
    prefs = await service.get_or_create_preferences(user_id, db)
    return {"preferences": prefs.to_dict()}


# Convert update_preferences endpoint:
@router.put("/")
@db_transaction_handler("update email preferences", auto_commit=True)
async def update_preferences(
    prefs_request: UpdatePreferencesRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Update user's email preferences."""
    user_id = UUID(current_user["identity"])
    service = EmailPreferencesService(db)
    updates = {k: v for k, v in prefs_request.dict().items() if v is not None}
    if not updates:
        return {"message": "No preferences to update"}
    prefs = await service.update_preferences(user_id, updates, db)
    return {"preferences": prefs.to_dict()}
```

### Step 2: Convert `onboarding.py` (Pattern 4 → Pattern 2)

```python
# File: rext-backend/src/api/routes/users/onboarding.py
# Add import:
from src.utils.route_decorators import db_transaction_handler

# Example conversion for update_onboarding_step:
@router.post("/update", response_model=OnboardingResponse, status_code=status.HTTP_200_OK)
@db_transaction_handler("update onboarding step", auto_commit=True)
async def update_onboarding_step(
    step_update: OnboardingStepUpdate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    current_user: Annotated[Auth.types.MinimalUserDict, Depends(get_current_user)],
):
    """Update onboarding step."""
    user_id = UUID(current_user["identity"])

    if step_update.action == "complete":
        onboarding = await OnboardingService.complete_step(db, user_id, step_update.step)
    elif step_update.action == "skip":
        onboarding = await OnboardingService.skip_step(db, user_id, step_update.step)
    elif step_update.action == "set_current":
        onboarding = await OnboardingService.set_current_step(db, user_id, step_update.step)
    else:
        raise RextValidationException(
            message=f"Invalid action: {step_update.action}. Must be 'complete', 'skip', or 'set_current'",
            validation_errors={"action": "Invalid action value"}
        )
    return onboarding
```

### Step 3: Convert `user_status.py` (Pattern 1 → Pattern 2)

Replace manual try/catch + `error()` calls with `@db_transaction_handler` and custom exceptions. For the admin check, replace `return error(...)` with:

```python
from src.api.middleware.exceptions import RextAuthorizationException

# Instead of: return error(message="Insufficient permissions...", ...)
raise RextAuthorizationException(
    message="Insufficient permissions. Admin role required.",
    required_permission="admin"
)
```

### Step 4: Convert `profile.py` mixed patterns (Pattern 5 → Pattern 2)

The avatar upload and delete endpoints (which use `raise HTTPException`) should be converted to use `@db_transaction_handler`. Validation errors (like invalid image type) should raise `RextValidationException` instead of using `return error(...)`.

### Step 5: Convert `management.py` (Pattern 1 → Pattern 2)

Same approach as user_status.py — add `@db_transaction_handler`, remove manual try/catch, convert `return error()` calls to custom exception raises.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/api/routes/users/profile.py` | `39-78, 345-359` | Mixed Patterns 1 and 4 — needs full conversion to Pattern 2 |
| `rext-backend/src/api/routes/users/management.py` | `throughout` | Pattern 1 — needs conversion to Pattern 2 |
| `rext-backend/src/api/routes/users/user_status.py` | `46-50, throughout` | Pattern 1 — needs conversion to Pattern 2 |
| `rext-backend/src/api/routes/users/email_preferences.py` | `76-87, 102-123` | Pattern 4 — needs conversion to Pattern 2 |
| `rext-backend/src/api/routes/users/onboarding.py` | `all 6 endpoints` | Pattern 4 — needs conversion to Pattern 2 |
| `rext-backend/src/api/routes/users/sessions.py` | — | Already uses Pattern 2. No change needed. |
| `rext-backend/src/api/routes/users/roles.py` | — | Already uses Pattern 2. No change needed. |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Call `GET /user/email-preferences/` with an invalid session to trigger an error.
   - Observe the response format: `{"detail": "Failed to retrieve email preferences"}` (FastAPI default format).
2. Call `POST /{user_id}/suspend` without admin permissions.
   - Observe the response format: `{"success": false, "error": {"code": "forbidden", "message": "...", "severity": "high"}}` (project's structured format).
3. Note the two completely different error response structures from the same API.

### After Fix (Verify the Solution):
1. Repeat both calls above.
2. Both should now return the project's standardized error format with `ErrorCode`, `ErrorSeverity`, and request metadata.
3. Test each converted endpoint with both success and error scenarios.
4. Verify the frontend error handling works consistently across all user management endpoints.

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "user" -v
```

---

## Acceptance Criteria

- [ ] All user management route files use `@db_transaction_handler` for error handling
- [ ] No manual `try/except` blocks remain in route handlers (except for specific input parsing like `authorization.split()`)
- [ ] No direct `HTTPException` raises remain in route handlers
- [ ] All error responses follow the project's standardized error envelope format
- [ ] Business logic errors use custom exceptions from `src/api/middleware/exceptions.py`
- [ ] Transaction commit/rollback is handled by the decorator, not manually
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [FastAPI Error Handling](https://fastapi.tiangolo.com/tutorial/handling-errors/) — FastAPI's built-in error handling and custom exception handlers
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [FastAPI Best Practices — Error Handling](https://github.com/zhanymkanov/fastapi-best-practices#4-follow-the-rest) — recommends consistent error response schemas across all endpoints
- **Related Issues/PRs:** None identified

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-064 (internal error details leaked via `str(e)` — this refactoring will fix many of those leaks by routing errors through the decorator's filtered error handling), TASK-073 (onboarding endpoints — will also need `@db_transaction_handler` when converted)
