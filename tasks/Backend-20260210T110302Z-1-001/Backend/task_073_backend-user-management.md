# Task 073: No `@require_permissions` on Onboarding Endpoints

## Metadata
- **Task ID:** TASK-073
- **Source:** B3 - User Management (Finding #23 under P2 Medium)
- **Audit Report:** `audit-reports/backend-user-management.md`
- **Priority:** P2 Medium
- **Category:** security
- **Effort Estimate:** small (< 1 hour)

---

## Description

All six endpoints in `src/api/routes/users/onboarding.py` lack `@require_permissions` decorator checks. While four of the six endpoints use `Depends(get_current_user)` for authentication (verifying the user is logged in), none perform authorization checks to verify the user has the appropriate permissions to perform the action. The remaining two endpoints use `Depends(get_current_user_optional)` which makes authentication itself optional.

The four state-changing POST endpoints are the primary concern:
- `POST /onboarding/update` (line 62) — modifies onboarding step progress
- `POST /onboarding/complete` (line 105) — marks onboarding as completed
- `POST /onboarding/reset` (line 129) — resets onboarding to start over
- `POST /onboarding/marketing` (line 188) — updates marketing data

Without permission checks, any authenticated user can call these endpoints. While the `OnboardingService` does scope operations to `current_user["identity"]` (so a user can only modify their own onboarding), this relies entirely on the service layer for access control — violating the defense-in-depth principle. If the service layer ever introduces admin functionality (e.g., resetting another user's onboarding), the missing permission check at the route level would expose it immediately.

Every other state-changing endpoint in the user management routes uses `@require_permissions`. For example, `profile.py` uses `@require_permissions("user.update")` on profile update endpoints, `user_status.py` uses `@require_permissions("user.update")` on suspend/activate/ban endpoints, and `management.py` uses `@require_permissions("user.update")` on user update endpoints. The onboarding routes are the only exception.

The two GET endpoints (`GET /onboarding` and `GET /onboarding/should-show`) use optional authentication (`get_current_user_optional`) by design, since they need to gracefully handle unauthenticated requests during the onboarding flow. Adding `@require_permissions` to these would break the intended flow, so they should be left as-is.

---

## Current Code

```python
# File: rext-backend/src/api/routes/users/onboarding.py
# Lines 62-102 (update endpoint — NO @require_permissions):
@router.post("/update", response_model=OnboardingResponse, status_code=status.HTTP_200_OK)
async def update_onboarding_step(
    step_update: OnboardingStepUpdate,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    current_user: Annotated[Auth.types.MinimalUserDict, Depends(get_current_user)],
):
    """Update onboarding step."""
    try:
        user_id = UUID(current_user["identity"])
        # ... business logic ...
    except Exception as e:
        logger.error(f"[Onboarding] Failed to update step: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update onboarding step",
        )
```

```python
# File: rext-backend/src/api/routes/users/onboarding.py
# Lines 105-126 (complete endpoint — NO @require_permissions):
@router.post("/complete", response_model=OnboardingResponse, status_code=status.HTTP_200_OK)
async def complete_onboarding(
    db: Annotated[AsyncSession, Depends(get_async_db)],
    current_user: Annotated[Auth.types.MinimalUserDict, Depends(get_current_user)],
):
    """Mark onboarding as fully completed."""
    try:
        user_id = UUID(current_user["identity"])
        # ...
```

```python
# File: rext-backend/src/api/routes/users/onboarding.py
# Lines 129-157 (reset endpoint — NO @require_permissions):
@router.post("/reset", response_model=OnboardingResponse, status_code=status.HTTP_200_OK)
async def reset_onboarding(
    reset_data: OnboardingReset,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    current_user: Annotated[Auth.types.MinimalUserDict, Depends(get_current_user)],
):
    """Reset onboarding to start from beginning."""
    # ...
```

```python
# File: rext-backend/src/api/routes/users/onboarding.py
# Lines 188-216 (marketing endpoint — NO @require_permissions):
@router.post("/marketing", response_model=OnboardingResponse, status_code=status.HTTP_200_OK)
async def update_marketing_data(
    marketing_data: OnboardingMarketingData,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    current_user: Annotated[Auth.types.MinimalUserDict, Depends(get_current_user)],
):
    """Update marketing data collected during onboarding."""
    # ...
```

---

## Why This Matters (Context & Reasoning)

The `@require_permissions` decorator (defined in `src/utils/route_decorators.py` lines 236-423) provides role-based access control (RBAC) enforcement at the route level. It checks that the authenticated user has been granted the specified permission(s) before the request handler is invoked. This is a core part of the application's security architecture.

Without `@require_permissions`, the onboarding endpoints rely solely on authentication (`get_current_user`), which only verifies that the request has a valid JWT token. This means:

1. **Any authenticated user**, regardless of their role or permission set, can modify onboarding state.
2. If a user's permissions are revoked (e.g., account suspended but token not yet expired), they can still access these endpoints.
3. The endpoints are invisible to the permission auditing system — tools that scan for `@require_permissions` to build permission matrices will miss these endpoints entirely, creating a gap in security documentation.

The `workspace_scoped=False` parameter is required because onboarding is user-level state, not workspace-level. Other user-level endpoints like session management (in `sessions.py` line 21) use this same parameter: `@require_permissions("user.read", workspace_scoped=False)`.

Note: The `require_permissions` import is already present in `onboarding.py` (line 20) but is unused — suggesting the developer intended to add the decorator but forgot.

---

## Impact

- **Severity:** Any authenticated user can access and modify onboarding state without proper authorization checks. If admin-level onboarding management features are added in the future, they would be exposed without protection.
- **Affected Users/Flows:** All onboarding POST endpoints — step update, complete, reset, and marketing data submission.
- **Blast Radius:** Isolated to the 4 POST endpoints in `onboarding.py`. The 2 GET endpoints intentionally use optional auth and should remain as-is.

---

## Recommended Solution

### Step 1: Add `@require_permissions` to the update endpoint

```python
# File: rext-backend/src/api/routes/users/onboarding.py
# Add decorator before line 62:
@router.post("/update", response_model=OnboardingResponse, status_code=status.HTTP_200_OK)
@require_permissions("user.update", workspace_scoped=False)
async def update_onboarding_step(
    step_update: OnboardingStepUpdate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    current_user: Annotated[Auth.types.MinimalUserDict, Depends(get_current_user)],
):
```

Note: The `request: Request` parameter must be added to the function signature because `@require_permissions` requires it for logging and context.

### Step 2: Add `@require_permissions` to the complete endpoint

```python
# File: rext-backend/src/api/routes/users/onboarding.py
# Add decorator before line 105:
@router.post("/complete", response_model=OnboardingResponse, status_code=status.HTTP_200_OK)
@require_permissions("user.update", workspace_scoped=False)
async def complete_onboarding(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    current_user: Annotated[Auth.types.MinimalUserDict, Depends(get_current_user)],
):
```

### Step 3: Add `@require_permissions` to the reset endpoint

```python
# File: rext-backend/src/api/routes/users/onboarding.py
# Add decorator before line 129:
@router.post("/reset", response_model=OnboardingResponse, status_code=status.HTTP_200_OK)
@require_permissions("user.update", workspace_scoped=False)
async def reset_onboarding(
    reset_data: OnboardingReset,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    current_user: Annotated[Auth.types.MinimalUserDict, Depends(get_current_user)],
):
```

### Step 4: Add `@require_permissions` to the marketing endpoint

```python
# File: rext-backend/src/api/routes/users/onboarding.py
# Add decorator before line 188:
@router.post("/marketing", response_model=OnboardingResponse, status_code=status.HTTP_200_OK)
@require_permissions("user.update", workspace_scoped=False)
async def update_marketing_data(
    marketing_data: OnboardingMarketingData,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    current_user: Annotated[Auth.types.MinimalUserDict, Depends(get_current_user)],
):
```

### Step 5: Add the `Request` import

```python
# File: rext-backend/src/api/routes/users/onboarding.py
# Update line 6 to add Request:
from fastapi import APIRouter, Depends, HTTPException, Request, status
```

### Important Notes:

- The `require_permissions` import already exists at line 20 — no new import needed for the decorator.
- The two GET endpoints (`get_onboarding_status` and `should_show_onboarding`) should NOT get `@require_permissions` because they use optional authentication by design.
- The `"user.update"` permission is consistent with what other user self-modification endpoints use (e.g., profile update, notification preferences update).
- `workspace_scoped=False` is required because onboarding is user-level, not workspace-level.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/utils/route_decorators.py` | `236-423` | Definition of `require_permissions` decorator — no changes needed |
| `rext-backend/src/api/routes/users/profile.py` | `28, 95, 168, 363, 478, 522` | Examples of correct `@require_permissions` usage for reference |
| `rext-backend/src/api/routes/users/sessions.py` | `21` | Example of `workspace_scoped=False` usage |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Create a test user with minimal permissions (e.g., only `user.read`, no `user.update`).
2. Authenticate and obtain a JWT token.
3. Call `POST /onboarding/update` with a valid step update payload.
4. Observe that the request succeeds even though the user lacks `user.update` permission.

### After Fix (Verify the Solution):
1. Using the same minimal-permission user, call `POST /onboarding/update`.
2. Verify the request is rejected with a 403 Forbidden response and an appropriate `INSUFFICIENT_PERMISSIONS` error code.
3. Create a user with `user.update` permission.
4. Call `POST /onboarding/update` — verify it succeeds.
5. Call `POST /onboarding/complete` — verify it succeeds.
6. Call `POST /onboarding/reset` with `{"confirm": true}` — verify it succeeds.
7. Call `POST /onboarding/marketing` with valid marketing data — verify it succeeds.
8. Call `GET /onboarding` without authentication — verify it still returns 401 (not 403) as before.
9. Call `GET /onboarding/should-show` without authentication — verify it returns `{"should_show": false}` as before.

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "onboarding" -v
```

---

## Acceptance Criteria

- [ ] `@require_permissions("user.update", workspace_scoped=False)` is added to `POST /onboarding/update`
- [ ] `@require_permissions("user.update", workspace_scoped=False)` is added to `POST /onboarding/complete`
- [ ] `@require_permissions("user.update", workspace_scoped=False)` is added to `POST /onboarding/reset`
- [ ] `@require_permissions("user.update", workspace_scoped=False)` is added to `POST /onboarding/marketing`
- [ ] `GET /onboarding` and `GET /onboarding/should-show` remain unchanged (no permission decorator)
- [ ] `Request` import and parameter is added to all 4 modified endpoints
- [ ] Users without `user.update` permission receive 403 on the 4 POST endpoints
- [ ] Users with `user.update` permission can still access all endpoints normally
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [FastAPI Dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/) — FastAPI's dependency injection pattern for middleware-like route guards
- **Security Advisory:** N/A (authorization gap, not a CVE-tracked vulnerability)
- **Migration Guide:** N/A
- **Best Practice Reference:** [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) — recommends enforcing authorization at every layer, not relying solely on authentication
- **Related Issues/PRs:** None identified

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-072 (error handling patterns — onboarding.py also needs `@db_transaction_handler` for consistent error handling, which could be done at the same time), TASK-008 (commented-out workspace validation in route decorators)
