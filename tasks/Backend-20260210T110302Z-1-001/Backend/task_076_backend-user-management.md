# Task 076: Remove Duplicate Deactivation Endpoint in profile.py

## Metadata
- **Task ID:** TASK-076
- **Source:** B3 - User Management (Finding #16 under P2 Medium)
- **Audit Report:** `audit-reports/backend-user-management.md`
- **Priority:** P2 Medium
- **Category:** bug
- **Effort Estimate:** small (< 1 hour)

---

## Description

Two `POST /deactivate` endpoints are registered in the user routes: one in `src/api/routes/users/profile.py` (line 619) and another in `src/api/routes/users/user_status.py` (line 317). Both files' routers are included in the parent router via `src/api/routes/users/__init__.py`, where `profile.router` is included first at line 30 and `user_status.router` is included second at line 34. In FastAPI (built on Starlette), route matching is performed in registration order -- the first route that matches a given path and HTTP method is the one that handles the request. This means the simpler `profile.py` version at line 619 is the one that actually handles `POST /deactivate` requests, while the more complete `user_status.py` version at line 317 is silently shadowed and never reached.

The `profile.py` version is a simpler implementation: it handles deactivation inline with direct `datetime.utcnow()` calls, sets `user.status = "inactive"` and `user.deactivated_at = now` directly, includes an optional `cancel_subscriptions` flag with inline subscription cancellation logic, uses `workspace_scoped=False` in its `@require_permissions("user.update", workspace_scoped=False)` decorator, and produces no audit log entry. The `user_status.py` version is significantly more complete: it delegates to `UserService.deactivate_account()` following the proper service-layer pattern, creates an audit log entry via `create_audit_log_async()`, checks for active subscriptions with a confirmation flow before proceeding, returns a typed `DeactivateAccountResponse` with a scheduled deletion date, and uses proper error handling through the `error()` utility function.

The consequence is that the production system currently runs the simpler implementation, which means account deactivations do not generate audit log entries, do not calculate or return a scheduled deletion date, and do not use the proper service-layer abstraction. Any bug fixes or enhancements made to the `user_status.py` version will have no effect because that endpoint is unreachable. The frontend at `rext-admin/lib/api-client/profile.ts` line 147 calls `POST /api/v1/user/deactivate` expecting well-defined behavior, but is unknowingly hitting the incomplete implementation.

---

## Current Code

### Router inclusion order (`src/api/routes/users/__init__.py`):

```python
# File: src/api/routes/users/__init__.py
# Lines 30 and 34 — profile.router is included FIRST, so its /deactivate wins
router.include_router(profile.router)        # Line 30 — FIRST (active)
# ... other routers ...
router.include_router(user_status.router)     # Line 34 — SECOND (shadowed)
```

### Simpler duplicate in profile.py (lines 619-735) -- this is the one currently active:

```python
# File: src/api/routes/users/profile.py
# Lines: 619-735
@router.post("/deactivate")
@require_permissions("user.update", workspace_scoped=False)
async def deactivate_account(
    request: Request,
    deactivate_request: DeactivateAccountRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Deactivate current user's account."""
    try:
        from datetime import timedelta
        from src.api.models.subscription_models.subscriptions import UserSubscription
        user_id = current_user.get("identity")
        service = UserService(db)
        # ... simple deactivation with inline subscription cancel
        # Uses datetime.utcnow() directly
        # Sets user.status = "inactive", user.deactivated_at = now
        # No audit log
        # Has cancel_subscriptions option
```

### Complete version in user_status.py (lines 317-470) -- this is shadowed and unreachable:

```python
# File: src/api/routes/users/user_status.py
# Lines: 317-470
@router.post("/deactivate", response_model=DeactivateAccountResponse)
@require_permissions("user.update")
async def deactivate_account(
    request: Request,
    deactivation_data: DeactivateAccountRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Deactivate user's own account."""
    try:
        user_id = UUID(current_user.get("identity"))
        service = UserService(db)
        # ... more complete version:
        # Uses UserService.deactivate_account() (proper service pattern)
        # Creates audit log via create_audit_log_async()
        # Checks active subscriptions and optionally auto-cancels
        # Returns typed DeactivateAccountResponse
        # Proper error handling with error() utility
```

---

## Why This Matters (Context & Reasoning)

Account deactivation is a critical, destructive user-facing operation that involves subscription cancellation, audit logging, and scheduling permanent account deletion. It is an action that users perform from the Settings page and is one of the most consequential actions a user can take on the platform. Having two competing implementations creates a hidden behavioral dependency on router inclusion order in `__init__.py` -- an ordering that could change during any refactor without anyone realizing the deactivation behavior has silently switched.

The current situation is particularly dangerous because the active implementation (the simpler `profile.py` version) lacks audit logging. If a user disputes their account deactivation or if there is a compliance investigation, there would be no audit trail of the action. Additionally, the simpler version does not return a `DeactivateAccountResponse` with a scheduled deletion date, so the frontend may not be able to display the expected deletion timeline to the user.

From a code maintenance perspective, a developer looking at `user_status.py` would reasonably assume that its `deactivate_account` endpoint is the live production code and might make changes to it (bug fixes, security patches, new features) that would never take effect, creating a false sense of security.

---

## Impact
- **Severity:** The simpler endpoint silently shadows the complete one. Production deactivations skip audit logging, skip proper service-layer delegation, and may not handle subscription cancellation correctly. If the wrong implementation is active (which is the current state), deactivation behavior is degraded without any visible error.
- **Affected Users/Flows:** All users deactivating their own accounts via the Settings page. The frontend call at `rext-admin/lib/api-client/profile.ts:147` is the primary trigger for this endpoint.
- **Blast Radius:** Isolated to the deactivation flow, but the downstream consequences are significant: missing audit trail for compliance, potential subscription leaks if cancellation logic differs between implementations, and incorrect API response schema if the frontend expects `DeactivateAccountResponse` fields.

---

## Recommended Solution

### Step 1: Remove the deactivation endpoint from `profile.py`

Delete the entire `deactivate_account` function and its route decorator from `src/api/routes/users/profile.py` (lines 619 through approximately 735). This eliminates the simpler duplicate and leaves the more complete `user_status.py` version as the sole implementation.

```python
# File: src/api/routes/users/profile.py
# DELETE the following block entirely (lines 619-735):

# Remove this:
@router.post("/deactivate")
@require_permissions("user.update", workspace_scoped=False)
async def deactivate_account(
    request: Request,
    deactivate_request: DeactivateAccountRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Deactivate current user's account."""
    # ... entire function body through line ~735
```

### Step 2: Verify `user_status.py` version includes password verification (if required)

The `profile.py` version may include password verification before deactivation (e.g., calling `verify_user_password`). Check whether the `DeactivateAccountRequest` schema includes a `password` field and whether password verification is a business requirement for deactivation. If so, add password verification to the `user_status.py` version:

```python
# File: src/api/routes/users/user_status.py
# Inside deactivate_account(), after retrieving the user, add password verification if needed:

        # Verify password before proceeding with deactivation
        if deactivation_data.password:
            user = await service.get_user_by_id(user_id)
            if not user or not verify_password(deactivation_data.password, user.hashed_password):
                return error("Invalid password", status_code=401)
```

### Step 3: Clean up unused imports in `profile.py`

After removing the deactivation endpoint, check whether any imports in `profile.py` are now unused (e.g., `DeactivateAccountRequest`, `UserSubscription`, `timedelta` if imported at module level). Remove unused imports to keep the module clean.

```python
# File: src/api/routes/users/profile.py
# Review and remove any imports that were only used by the deleted deactivate_account function.
# For example, if DeactivateAccountRequest is no longer referenced:
# Remove: from src.api.schema.user_schema import DeactivateAccountRequest
```

### Step 4: Verify the endpoint path matches frontend expectations

Confirm that the `user_status.py` endpoint resolves to the same path the frontend expects. Since both files use the same `router` prefix and both define `@router.post("/deactivate")`, the path will be identical after the duplicate is removed. The frontend at `rext-admin/lib/api-client/profile.ts:147` calls `POST /api/v1/user/deactivate`, which should continue to work.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/routes/users/__init__.py` | 30, 34 | Imports and includes both route files; inclusion order determines which endpoint wins |
| `src/api/routes/users/profile.py` | 619-735 | Contains the simpler duplicate endpoint to be removed |
| `src/api/routes/users/user_status.py` | 317-470 | Contains the complete endpoint that should be the sole implementation |
| `rext-admin/lib/api-client/profile.ts` | 147 | Frontend calls `POST /api/v1/user/deactivate`; verify no changes needed |
| `src/api/schema/user_schema.py` | Various | `DeactivateAccountRequest` and `DeactivateAccountResponse` schemas used by both endpoints |
| `src/services/user_service.py` | Various | `UserService.deactivate_account()` method used by the `user_status.py` version |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Inspect `src/api/routes/users/__init__.py` lines 30 and 34 to confirm `profile.router` is included before `user_status.router`.
2. Start the application and visit the OpenAPI docs at `/docs`. Search for `POST /deactivate` -- FastAPI will show both endpoints registered but only the first one (from `profile.py`) will actually handle requests.
3. Call `POST /api/v1/user/deactivate` with valid credentials and observe the response. Note that the response does NOT match `DeactivateAccountResponse` (no scheduled deletion date) and no audit log entry is created -- confirming the simpler `profile.py` version is active.
4. Add a temporary logging statement to `user_status.py`'s `deactivate_account` function and verify it is never triggered, confirming it is shadowed.

### After Fix (Verify the Solution):
1. Verify that `profile.py` no longer contains a `deactivate_account` function or a `@router.post("/deactivate")` decorator.
2. Search the codebase to confirm only one `POST /deactivate` endpoint exists (in `user_status.py`):
   ```bash
   grep -rn 'post.*"/deactivate"' src/api/routes/users/
   ```
3. Start the application and call `POST /api/v1/user/deactivate` with valid credentials. Verify:
   - The response matches the `DeactivateAccountResponse` schema (includes scheduled deletion date).
   - An audit log entry is created in the database.
   - Subscription cancellation logic executes when the user has active subscriptions.
4. Test the frontend deactivation flow end-to-end from the Settings page.
5. Verify the OpenAPI docs at `/docs` show only a single `POST /deactivate` endpoint.

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "deactivate" -v
cd rext-backend && python -m pytest tests/ -k "profile" -v
cd rext-backend && python -m pytest tests/ -k "user_status" -v
```

---

## Acceptance Criteria

- [ ] Only one `POST /deactivate` endpoint exists across all user route files (in `user_status.py`)
- [ ] The `profile.py` file no longer contains a `deactivate_account` function
- [ ] The remaining endpoint in `user_status.py` includes audit logging via `create_audit_log_async()`
- [ ] The remaining endpoint handles subscription checking and optional auto-cancellation
- [ ] The remaining endpoint returns a typed `DeactivateAccountResponse` with scheduled deletion date
- [ ] Password verification is present in the remaining endpoint if it is a business requirement (verify with product team)
- [ ] Any imports in `profile.py` that were only used by the removed endpoint are cleaned up
- [ ] Frontend deactivation flow at `rext-admin/lib/api-client/profile.ts:147` works correctly end-to-end
- [ ] OpenAPI docs show a single `POST /deactivate` endpoint with the correct response schema
- [ ] No new warnings or errors introduced
- [ ] Existing tests pass (`pytest tests/ -k "deactivate"`)
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [FastAPI - Path Operation Registration Order](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/) -- FastAPI registers routes in inclusion order; the first matching route handles the request.
- **Official Docs:** [FastAPI - Bigger Applications with Multiple Files](https://fastapi.tiangolo.com/tutorial/bigger-applications/) -- Best practices for organizing routes across multiple files using `include_router`.
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [Starlette Routing](https://www.starlette.io/routing/) -- Starlette (FastAPI's underlying framework) resolves routes in the order they are added; the first match wins.

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-059 through TASK-075 (other B3 User Management findings that touch the same route files). Specifically, any tasks modifying `profile.py` or `user_status.py` should be coordinated with this task to avoid merge conflicts.
