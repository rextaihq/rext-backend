# Task 023: Add Permission Check to Impersonation Status Endpoint

## Metadata
- **Task ID:** TASK-023
- **Source:** B1 - Authentication & Authorization (Finding #26 under P3 Low)
- **Audit Report:** `audit-reports/backend-authentication.md`
- **Priority:** P3 Low
- **Category:** security
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `GET /impersonate/status` endpoint in `src/api/routes/users/impersonation.py` (lines 194-243) lacks a `@require_permissions` decorator, making it the only endpoint in the impersonation routes file without explicit permission enforcement.

While this endpoint does require authentication (via `Depends(get_current_user)`), it does not enforce any specific permission. The other two impersonation endpoints have proper permission decorators:
- `POST /impersonate/start` — Has `@require_permissions("user.update")` and `dependencies=[Depends(is_admin)]`
- `POST /impersonate/stop` — Has `@require_permissions("user.update")`

The `/impersonate/status` endpoint reads from the JWT token to check if the current user is impersonating someone. Although it only reads data and doesn't modify state, consistent permission enforcement is a security best practice. Any endpoint that reveals information about user state should require at minimum `user.read` permission.

The OWASP Access Control Cheat Sheet recommends enforcing access control rules on all requests, including read-only endpoints, to maintain defense in depth. Inconsistent permission patterns also make code reviews and security audits more difficult.

---

## Current Code

```python
# File: rext-backend/src/api/routes/users/impersonation.py
# Lines: 194-243
@router.get("/impersonate/status", response_model=ImpersonationStatusResponse)
async def get_impersonation_status(
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
) -> dict:
    """
    Get the current impersonation status.

    Returns impersonation details if the current user is impersonating someone,
    or a simple status response if not impersonating.

    This endpoint reads from the JWT token and does not require database access or permissions.
    """
    is_impersonating = current_user.get("is_impersonating", False)
    session_id = current_user.get("session_id")

    if is_impersonating and session_id:
        service = ImpersonationService(db)
        is_valid = await service.is_session_valid(session_id)

        if not is_valid:
            raise HTTPException(
        status_code=401,
        detail="Impersonation session has been invalidated. Please obtain a new token.",
    )

    if not is_impersonating:
        return {"is_impersonating": False}

    # Build response with impersonation details from JWT token
    response = {
        "is_impersonating": True,
        "original_user_id": current_user.get("original_user_id"),
        "impersonated_user_id": current_user.get("identity"),
        "impersonated_user_email": current_user.get("email"),
        "impersonated_user_name": current_user.get("full_name"),
        "started_at": current_user.get("impersonation_started_at"),
        "session_id": session_id
    }

    logger.debug(
        "Impersonation status checked",
        extra={
            "is_impersonating": is_impersonating,
            "impersonated_user_id": response.get("impersonated_user_id"),
            "session_id": session_id
        },
    )

    return response
```

### Comparison with Other Endpoints in Same File

```python
# Line 29-36: Start endpoint HAS permission decorator
@router.post("/impersonate/start", dependencies=[Depends(is_admin)])
@require_permissions("user.update")
@db_transaction_handler("start impersonation", auto_commit=False)
async def start_impersonation(...):

# Line 107-113: Stop endpoint HAS permission decorator
@router.post("/impersonate/stop")
@require_permissions("user.update")
@db_transaction_handler("stop impersonation", auto_commit=True)
async def stop_impersonation(...):

# Line 194: Status endpoint MISSING permission decorator
@router.get("/impersonate/status", response_model=ImpersonationStatusResponse)
async def get_impersonation_status(...):  # <-- No @require_permissions
```

---

## Why This Matters (Context & Reasoning)

The impersonation feature allows admins to act as other users for debugging and support purposes. The status endpoint reveals:
- Whether impersonation is active
- The original admin user's ID
- The impersonated user's ID, email, and name
- The impersonation session ID
- When impersonation started

While this information is derived from the JWT token (which the caller already possesses), enforcing permissions provides:

1. **Consistency:** All impersonation endpoints follow the same security pattern
2. **Defense in Depth:** Even if authentication is compromised, permission checks add another layer
3. **Audit Trail:** Permission checks can be logged for security monitoring
4. **Future-Proofing:** If the endpoint is extended to return more data, permissions are already in place

The docstring even notes "does not require database access or permissions" — this is incorrect thinking. Authentication (who you are) and authorization (what you can do) are separate concerns, and both should be enforced.

---

## Impact

- **Severity:** Low. The endpoint only returns information already present in the user's JWT token. However, inconsistent permission patterns are a code smell.
- **Affected Users/Flows:** Any authenticated user can call this endpoint. Should be restricted to users with `user.read` permission.
- **Blast Radius:** Isolated to this single endpoint.

---

## Recommended Solution

Add the `@require_permissions` decorator with `user.read` permission to match the read-only nature of this endpoint.

### Step 1: Add Permission Decorator

```python
# File: rext-backend/src/api/routes/users/impersonation.py
# Lines: 194-198 - Replace:
@router.get("/impersonate/status", response_model=ImpersonationStatusResponse)
async def get_impersonation_status(
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
) -> dict:

# With:
@router.get("/impersonate/status", response_model=ImpersonationStatusResponse)
@require_permissions("user.read", workspace_scoped=False)
async def get_impersonation_status(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
) -> dict:
```

### Step 2: Add Request Import (if not present)

The `@require_permissions` decorator requires a `request: Request` parameter. Check if `Request` is already imported:

```python
# File: rext-backend/src/api/routes/users/impersonation.py
# Line 5 - Verify import exists:
from fastapi import APIRouter, Depends, HTTPException, Request
```

The import is already present on line 5, so no change needed.

### Step 3: Update the Docstring

```python
# File: rext-backend/src/api/routes/users/impersonation.py
# Update the docstring (lines 199-206) to remove the incorrect statement:

    """
    Get the current impersonation status.

    Returns impersonation details if the current user is impersonating someone,
    or a simple status response if not impersonating.

    Requires user.read permission for consistency with other user-related endpoints.
    """
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| None | - | This is an isolated change to one endpoint |

---

## Testing Instructions

### Before Fix (Demonstrate the Issue):
1. Create a test user without `user.read` permission (edge case)
2. Authenticate and get a JWT token
3. Call `GET /api/user/impersonate/status`
4. Observe the endpoint returns data without checking permissions

### After Fix (Verify the Solution):
1. Create a test user without `user.read` permission
2. Authenticate and get a JWT token
3. Call `GET /api/user/impersonate/status`
4. Observe the endpoint returns 403 Forbidden

5. Grant `user.read` permission to the test user
6. Re-authenticate and call the endpoint
7. Observe the endpoint returns impersonation status successfully

### Test with Normal User (has user.read):
```bash
# Get auth token
TOKEN=$(curl -s -X POST http://localhost:8000/api/user/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "password"}' \
  | jq -r '.data.access_token')

# Call impersonation status
curl -X GET http://localhost:8000/api/user/impersonate/status \
  -H "Authorization: Bearer $TOKEN"

# Expected: {"is_impersonating": false}
```

### Run Existing Tests:
```bash
cd rext-backend
pytest tests/ -v -k "impersonat"
```

---

## Acceptance Criteria

- [ ] `@require_permissions("user.read", workspace_scoped=False)` decorator added to endpoint
- [ ] `request: Request` parameter added to function signature
- [ ] Docstring updated to reflect permission requirement
- [ ] Endpoint returns 403 for users without `user.read` permission
- [ ] Endpoint works normally for users with `user.read` permission
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [FastAPI Security Dependencies](https://fastapi.tiangolo.com/tutorial/security/)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [OWASP Access Control Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Access_Control_Cheat_Sheet.html)
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-008 (Commented-Out Workspace Validation in Route Decorators), TASK-009 (Test Stub Bypasses Permission Checks)
