# Task 081: Extract Shared Logic from Duplicate Suspend/Ban Endpoints

## Metadata
- **Task ID:** TASK-081
- **Source:** B3 - User Management (Finding #18 under P2 Medium)
- **Audit Report:** `audit-reports/backend-user-management.md`
- **Priority:** P2 Medium
- **Category:** code-quality
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The `suspend_user` endpoint (lines 28–122) and `ban_user` endpoint (lines 220–314) in `src/api/routes/users/user_status.py` are nearly identical copy-paste implementations totaling ~180 lines of duplicated logic. The two functions differ only in three string values: the target status (`"suspended"` vs `"banned"`), the audit action name (`"user.suspend"` vs `"user.ban"`), and the log/success message wording. Every other aspect — the redundant `is_admin()` check, user lookup via `UserService`, direct ORM status mutation, `db.flush()`, admin user lookup for audit logging, `create_audit_log_async()` call, `UserStatusResponse` construction, `success()` response wrapping, and all error handling — is duplicated verbatim.

This is a textbook DRY (Don't Repeat Yourself) violation. The project's `UserService` already establishes the correct pattern: `deactivate_account()` (line 207 of `user_service.py`) and `reactivate_account()` (line 238) encapsulate status changes in the service layer, and the `activate_user` route endpoint (lines 125–217 of `user_status.py`) correctly delegates to `service.reactivate_account()`. The suspend and ban endpoints are the only status-change endpoints that bypass the service layer and mutate ORM models directly in the route handler.

Both endpoints also contain a redundant `is_admin(current_user)` check (lines 48 and 240) that duplicates the `@require_permissions("user.update")` decorator already applied to each endpoint. The decorator executes before the handler, loading user permissions via Redis-cached `rbac_utils.check_all_permissions()` and raising `RextAuthorizationException` if the user lacks `"user.update"`. The manual `is_admin()` check inside the handler is therefore dead code — it can never reach the `return error(...)` branch because the decorator already blocked unauthorized requests. OWASP's Access Control Cheat Sheet recommends centralizing access control logic in a single enforcement point, not duplicating it at the same layer (see References). This redundant check also uses `ErrorCode.PERMISSION_DENIED`, a non-existent enum value (covered by TASK-059).

Additionally, both endpoints use `datetime.utcnow()` (deprecated since Python 3.12 per PEP 587) instead of `datetime.now(timezone.utc)`. The `UserService` already uses `datetime.now(timezone.utc)` consistently (see `user_service.py` lines 143, 197, 198, 228, 229, 260, 296). This deprecation is addressed by TASK-079 but the new `change_user_status()` service method should use the correct API from the start.

The project uses FastAPI `>=0.116.1`, SQLAlchemy async with `asyncpg>=0.30.0`, and Python `>=3.11,<3.12` (per `pyproject.toml`). The recommended solution follows the established service-layer pattern already used by `deactivate_account()` and `reactivate_account()`, and aligns with current FastAPI service layer architecture best practices that recommend keeping routes as thin controllers delegating all business logic to services.

---

## Current Code

```python
# File: rext-backend/src/api/routes/users/user_status.py
# Lines: 28-122 (suspend_user endpoint)
@router.post("/{user_id}/suspend", response_model=UserStatusResponse)
@require_permissions("user.update")
async def suspend_user(
    user_id: str,
    request: Request,
    status_data: UserStatusRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Suspend a user account (admin only).
    Thin controller - business logic should be in service.
    """
    try:
        # Check if current user is admin  ← REDUNDANT: decorator already checks
        if not is_admin(current_user):
            return error(
                message="Insufficient permissions. Admin role required.",
                code=ErrorCode.PERMISSION_DENIED,  # ← Non-existent enum value (TASK-059)
                status_code=403,
                severity=ErrorSeverity.HIGH,
                request=request
            )

        service = UserService(db)
        target_user = await service.get_user_by_id(UUID(user_id))
        old_status = target_user.status

        # Update status directly (could be extracted to service method)
        target_user.status = "suspended"
        target_user.updated_at = datetime.utcnow()  # ← Deprecated (TASK-079)
        await db.flush()

        admin_user_id = UUID(current_user.get("identity"))
        admin_user = await service.get_user_by_id(admin_user_id)

        await create_audit_log_async(
            db=db, user_id=str(admin_user_id), action="user.suspend",
            resource_type="user", resource_id=str(user_id),
            old_values={"status": old_status},
            new_values={"status": "suspended", "reason": status_data.reason},
            request=request,
            full_name=admin_user.full_name if admin_user else None,
            user_email=admin_user.email if admin_user else None
        )

        logger.info(f"User {user_id} suspended by admin {admin_user_id}")

        response_data = UserStatusResponse(
            user_id=str(target_user.id),
            full_name=target_user.full_name or target_user.display_name or target_user.email,
            email=target_user.email, old_status=old_status, new_status="suspended",
            changed_by=admin_user.full_name or admin_user.display_name or admin_user.email if admin_user else "unknown",
            reason=status_data.reason,
            changed_at=target_user.updated_at.isoformat()
        )

        return success(
            data=response_data.model_dump(), request=request,
            message=f"User {target_user.full_name or target_user.email} suspended successfully"
        )

    except ResourceNotFoundException:
        return error(message="User not found", code=ErrorCode.RESOURCE_NOT_FOUND,
                     status_code=404, severity=ErrorSeverity.MEDIUM, request=request)
    except Exception as e:
        logger.error(f"Error suspending user {user_id}: {str(e)}")
        return error(message="Failed to suspend user", code=ErrorCode.INTERNAL_SERVER_ERROR,
                     status_code=500, severity=ErrorSeverity.HIGH,
                     context={"error_details": str(e)}, request=request)
```

```python
# File: rext-backend/src/api/routes/users/user_status.py
# Lines: 220-314 (ban_user — nearly identical, only "banned"/"user.ban" differ)
@router.post("/{user_id}/ban", response_model=UserStatusResponse)
@require_permissions("user.update")
async def ban_user(
    user_id: str,
    request: Request,
    status_data: UserStatusRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    # ... identical structure, "banned" instead of "suspended", "user.ban" instead of "user.suspend"
    try:
        if not is_admin(current_user):  # ← Same redundant check
            return error(
                message="Insufficient permissions. Admin role required.",
                code=ErrorCode.PERMISSION_DENIED,  # ← Same non-existent enum
                status_code=403, severity=ErrorSeverity.HIGH, request=request
            )

        service = UserService(db)
        target_user = await service.get_user_by_id(UUID(user_id))
        old_status = target_user.status

        target_user.status = "banned"
        target_user.updated_at = datetime.utcnow()  # ← Same deprecated call
        await db.flush()

        # ... identical admin lookup, audit log, response building, error handling
```

For comparison, the `activate_user` endpoint (lines 125–217) correctly delegates to `service.reactivate_account()` — this is the pattern suspend and ban should follow.

---

## Why This Matters (Context & Reasoning)

User status management (suspend, ban, activate) is a critical admin operation that controls user access to the platform. The `UserService` already establishes the architectural convention that status changes belong in the service layer: `deactivate_account()` at line 207 and `reactivate_account()` at line 238 both encapsulate status mutation, timestamp updates, and logging. The `activate_user` route endpoint correctly delegates to `service.reactivate_account()`.

The suspend and ban endpoints are the only status-change routes that bypass the service layer and mutate ORM models directly in the route handler. This breaks the project's stated architecture (the `UserService` docstring explicitly says routes should "NOT commit transactions" and "NOT handle business logic").

Beyond the immediate code quality concern, the duplication actively discourages future improvements. Adding features like status transition validation (e.g., preventing suspended→banned without reactivating first), email notifications on status change, webhook events, or rate limiting requires implementing the change twice and keeping both copies synchronized. Historical evidence in codebases shows one copy often gets fixed while the other does not, leading to behavioral drift.

The redundant `is_admin()` checks compound the problem: they use `ErrorCode.PERMISSION_DENIED` (a non-existent enum value), meaning if the decorator somehow failed, the fallback error handling would itself crash with `AttributeError`. This dead code creates false confidence in defense-in-depth while providing none.

---

## Impact

- **Severity:** No immediate runtime bug, but any future modification to suspend/ban logic must be applied to two separate ~90-line functions. The redundant `is_admin()` checks use a non-existent `ErrorCode` value that would crash if somehow reached.
- **Affected Users/Flows:** Admin users suspending or banning platform users. Behavioral drift between the two endpoints would confuse admins and affected users.
- **Blast Radius:** Isolated to `src/api/routes/users/user_status.py` and `src/services/user_service.py`. No external API contract changes — both endpoints keep the same URL paths, request/response schemas, and HTTP status codes.

---

## Recommended Solution

### Step 1: Add a `change_user_status()` method to `UserService`

This follows the established pattern of `deactivate_account()` (line 207) and `reactivate_account()` (line 238). The method validates the new status, fetches the user, captures the old status, and applies the change. It does NOT commit — consistent with the service's docstring: "Does NOT commit transactions (that's decorators/routes)."

```python
# File: rext-backend/src/services/user_service.py
# Add after the reactivate_account() method (after line 267), before cleanup_deactivated_accounts():

    async def change_user_status(
        self,
        user_id: UUID,
        new_status: str,
    ) -> tuple[Users, str]:
        """
        Change a user's status to a specified value.

        Validates that the new status is one of the allowed values,
        fetches the user, records the old status, and updates.

        Args:
            user_id: User UUID
            new_status: New status value (e.g., "suspended", "banned", "active", "inactive")

        Returns:
            Tuple of (updated Users object, old_status string)

        Raises:
            ResourceNotFoundException: If user not found
            RextValidationException: If new_status is not a valid status
        """
        valid_statuses = {"active", "inactive", "suspended", "banned"}
        if new_status not in valid_statuses:
            raise RextValidationException(
                message=f"Invalid status: {new_status}. Must be one of: {', '.join(sorted(valid_statuses))}"
            )

        user = await self.get_user_by_id(user_id)
        old_status = user.status

        user.status = new_status
        user.updated_at = datetime.now(timezone.utc)

        logger.info(
            f"User status changed: {user_id} ({old_status} -> {new_status})",
            extra={
                "user_id": str(user_id),
                "old_status": old_status,
                "new_status": new_status,
            }
        )

        return user, old_status
```

No new imports needed — `RextValidationException` is already imported at line 31 of `user_service.py`, and `datetime` + `timezone` are already imported at line 21.

### Step 2: Create a shared `_handle_status_change()` helper in the route file

This helper encapsulates the HTTP-layer concerns (admin user lookup for audit, audit log creation, response schema building) that were duplicated between the two endpoints. It stays in the route file because it depends on HTTP-specific types (`Request`, response utilities).

```python
# File: rext-backend/src/api/routes/users/user_status.py
# Add after the router definition (after line 25), before the suspend_user endpoint:

async def _handle_status_change(
    user_id: str,
    new_status: str,
    action_name: str,
    request: Request,
    status_data: UserStatusRequest,
    current_user: dict,
    db: AsyncSession,
):
    """
    Shared logic for admin-initiated user status changes (suspend, ban, etc.).

    Delegates the actual status mutation to UserService.change_user_status(),
    then handles audit logging, response building, and success messaging.

    Args:
        user_id: Target user ID string
        new_status: Status to set (e.g., "suspended", "banned")
        action_name: Audit action name (e.g., "user.suspend", "user.ban")
        request: FastAPI Request object for audit/response context
        status_data: Request body with optional reason
        current_user: Authenticated admin user dict from JWT
        db: Async database session

    Returns:
        Success response dict via success() utility
    """
    service = UserService(db)

    # Delegate status change to service layer
    target_user, old_status = await service.change_user_status(
        UUID(user_id), new_status
    )

    # Get admin user details for audit log
    admin_user_id = UUID(current_user.get("identity"))
    admin_user = await service.get_user_by_id(admin_user_id)

    # Create audit log
    await create_audit_log_async(
        db=db,
        user_id=str(admin_user_id),
        action=action_name,
        resource_type="user",
        resource_id=str(user_id),
        old_values={"status": old_status},
        new_values={"status": new_status, "reason": status_data.reason},
        request=request,
        full_name=admin_user.full_name if admin_user else None,
        user_email=admin_user.email if admin_user else None,
    )

    logger.info(f"User {user_id} {new_status} by admin {admin_user_id}")

    # Build response
    response_data = UserStatusResponse(
        user_id=str(target_user.id),
        full_name=target_user.full_name or target_user.display_name or target_user.email,
        email=target_user.email,
        old_status=old_status,
        new_status=new_status,
        changed_by=(
            admin_user.full_name or admin_user.display_name or admin_user.email
            if admin_user else "unknown"
        ),
        reason=status_data.reason,
        changed_at=target_user.updated_at.isoformat(),
    )

    return success(
        data=response_data.model_dump(),
        request=request,
        message=f"User {target_user.full_name or target_user.email} {new_status} successfully",
    )
```

### Step 3: Simplify the `suspend_user` endpoint

Replace lines 28–122 with a thin handler that delegates to the shared helper. The redundant `is_admin()` check and direct ORM mutation are removed.

```python
# File: rext-backend/src/api/routes/users/user_status.py
# Replace lines 28-122:

@router.post("/{user_id}/suspend", response_model=UserStatusResponse)
@require_permissions("user.update")
async def suspend_user(
    user_id: str,
    request: Request,
    status_data: UserStatusRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Suspend a user account (admin only).

    - **user_id**: ID of the user to suspend
    - **reason**: Optional reason for suspension

    Permission enforced by @require_permissions decorator.
    """
    try:
        return await _handle_status_change(
            user_id=user_id,
            new_status="suspended",
            action_name="user.suspend",
            request=request,
            status_data=status_data,
            current_user=current_user,
            db=db,
        )
    except ResourceNotFoundException:
        return error(
            message="User not found",
            code=ErrorCode.RESOURCE_NOT_FOUND,
            status_code=404,
            severity=ErrorSeverity.MEDIUM,
            request=request,
        )
    except Exception as e:
        logger.error(f"Error suspending user {user_id}: {str(e)}")
        return error(
            message="Failed to suspend user",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request,
        )
```

### Step 4: Simplify the `ban_user` endpoint

Replace lines 220–314 with the same thin handler pattern:

```python
# File: rext-backend/src/api/routes/users/user_status.py
# Replace lines 220-314:

@router.post("/{user_id}/ban", response_model=UserStatusResponse)
@require_permissions("user.update")
async def ban_user(
    user_id: str,
    request: Request,
    status_data: UserStatusRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Ban a user account (admin only).

    - **user_id**: ID of the user to ban
    - **reason**: Optional reason for ban

    Permission enforced by @require_permissions decorator.
    """
    try:
        return await _handle_status_change(
            user_id=user_id,
            new_status="banned",
            action_name="user.ban",
            request=request,
            status_data=status_data,
            current_user=current_user,
            db=db,
        )
    except ResourceNotFoundException:
        return error(
            message="User not found",
            code=ErrorCode.RESOURCE_NOT_FOUND,
            status_code=404,
            severity=ErrorSeverity.MEDIUM,
            request=request,
        )
    except Exception as e:
        logger.error(f"Error banning user {user_id}: {str(e)}")
        return error(
            message="Failed to ban user",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request,
        )
```

### Step 5: Remove the `is_admin` import if no longer needed

After the refactor, the `is_admin` function is still used in the `activate_user` endpoint at line 145. If `activate_user` is also refactored to use `_handle_status_change()` (separate task), the import can be removed. For now, leave it.

```python
# File: rext-backend/src/api/routes/users/user_status.py
# Line 20: from src.api.middleware.permissions import is_admin
# KEEP this import — still used by activate_user at line 145
```

### Step 6: Remove `context={"error_details": str(e)}` from error responses

The refactored error handlers in Steps 3 and 4 intentionally omit `context={"error_details": str(e)}` from the generic `Exception` handler. This is aligned with TASK-064 (B3 Finding #10 — internal error details leaked to clients). The error is still logged via `logger.error()`.

### Design Decision: Why both a service method AND a route helper?

- **`UserService.change_user_status()`**: Business logic (status validation, ORM mutation, timestamp update). Reusable by CLI scripts, background jobs, or other routes without duplicating validation.
- **`_handle_status_change()`**: HTTP-layer concerns (admin user lookup for audit, audit log creation, response schema building). Stays in the route file because it depends on `Request`, `success()`, `UserStatusResponse` — concepts that should not exist in the service layer.

This follows the project's established separation: `deactivate_account()` is in the service, but the route handler for `/deactivate` still handles its own audit logging and response building.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/services/user_service.py` | After line 267 | Add `change_user_status()` method here, before `cleanup_deactivated_accounts()` |
| `rext-backend/src/api/routes/users/user_status.py` | 125-217 | `activate_user` endpoint — has the same redundant `is_admin()` check at line 145 and same audit/response pattern. Could be refactored to use `_handle_status_change()` in a follow-up task, but uses `service.reactivate_account()` rather than `change_user_status()` so it's a separate concern |
| `rext-backend/src/api/routes/users/user_status.py` | 317-470 | `deactivate_account` endpoint — different flow (self-deactivation, not admin-initiated), subscription cancellation logic. Not a candidate for the shared helper |
| `rext-backend/src/api/routes/users/user_status.py` | 20 | `from src.api.middleware.permissions import is_admin` — still used by `activate_user` at line 145, keep for now |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Open `rext-backend/src/api/routes/users/user_status.py` and visually compare `suspend_user` (lines 28–122) with `ban_user` (lines 220–314) — note the logic is identical apart from three string values.
2. Verify both endpoints work correctly before making changes:
   ```bash
   # As an admin user, suspend a user:
   curl -X POST http://localhost:8000/api/v1/user/{user_id}/suspend \
     -H "Authorization: Bearer <admin-token>" \
     -H "Content-Type: application/json" \
     -d '{"reason": "Test suspension"}'

   # As an admin user, ban a user:
   curl -X POST http://localhost:8000/api/v1/user/{user_id}/ban \
     -H "Authorization: Bearer <admin-token>" \
     -H "Content-Type: application/json" \
     -d '{"reason": "Test ban"}'
   ```
3. Record the exact response structure and HTTP status codes for comparison after the refactor.

### After Fix (Verify the Solution):
1. Call `POST /{user_id}/suspend` with valid admin credentials — verify user status changes to `"suspended"` and the response body matches the pre-refactor format exactly.
2. Call `POST /{user_id}/ban` with valid admin credentials — verify user status changes to `"banned"` and the response body matches the pre-refactor format exactly.
3. Verify audit logs are created correctly for both operations — check `old_status`, `new_status`, `action`, and `reason` fields.
4. Test with a non-existent `user_id` — verify 404 response with `"User not found"` message.
5. Test with a non-admin user (no `user.update` permission) — verify the `@require_permissions` decorator returns 403 before the handler executes.
6. Verify `UserService.change_user_status()` rejects invalid status values by calling it in a test with an invalid status string and confirming `RextValidationException` is raised.
7. Verify the `old_status` field in the response and audit log correctly reflects the status before the change (not the new status).
8. Confirm `context={"error_details": str(e)}` is no longer present in error responses (no internal details leaked).

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "suspend or ban or user_status" -v
```

---

## Acceptance Criteria

- [ ] `change_user_status()` method added to `UserService` in `rext-backend/src/services/user_service.py`
- [ ] Method returns `tuple[Users, str]` containing the updated user and the old status
- [ ] Method validates `new_status` against `{"active", "inactive", "suspended", "banned"}` and raises `RextValidationException` for invalid values
- [ ] Method uses `datetime.now(timezone.utc)` (not `datetime.utcnow()`) for the `updated_at` timestamp
- [ ] Shared `_handle_status_change()` helper created in `rext-backend/src/api/routes/users/user_status.py`
- [ ] `suspend_user` endpoint refactored to use `_handle_status_change()` with `new_status="suspended"` and `action_name="user.suspend"`
- [ ] `ban_user` endpoint refactored to use `_handle_status_change()` with `new_status="banned"` and `action_name="user.ban"`
- [ ] Redundant `is_admin(current_user)` checks removed from both endpoints
- [ ] Direct `db.flush()` call removed from the route handlers (service layer handles ORM mutation)
- [ ] `context={"error_details": str(e)}` removed from error responses (no internal details leaked)
- [ ] Both endpoints produce identical HTTP responses, status codes, and audit log entries as before the refactor
- [ ] `old_status` is correctly captured before the status change (not after)
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [FastAPI — Dependencies in path operation decorators](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-in-path-operation-decorators/) — explains how decorator-level dependencies execute before the handler
- **Official Docs:** [SQLAlchemy 2.0 — Session Basics (flush vs commit)](https://docs.sqlalchemy.org/en/20/orm/session_basics.html) — guidance on transaction management and why services should use `flush()` not `commit()`
- **Official Docs:** [SQLAlchemy 2.0 — AsyncIO Extension](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html) — async session patterns for the project's stack
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [OWASP — Access Control Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Access_Control_Cheat_Sheet.html) — recommends centralized access control mechanisms, not redundant inline checks
- **Best Practice Reference:** [FastAPI Service Layer Architecture Best Practices (2025)](https://medium.com/@abhinav.dobhal/building-production-ready-fastapi-applications-with-service-layer-architecture-in-2025-f3af8a6ac563) — recommends thin route handlers delegating to service layer
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None (but applying TASK-079 and TASK-059 first avoids merge conflicts in `user_status.py`)
- **Blocks:** None
- **Related:**
  - TASK-059 (B3 Finding #1, P0 Critical — `ErrorCode.PERMISSION_DENIED` at lines 51, 148, 243 does not exist in the enum; the refactored endpoints remove these occurrences entirely)
  - TASK-079 (B3 Finding #20, P2 Medium — `datetime.utcnow()` deprecation at lines 65, 257; the new `change_user_status()` method uses `datetime.now(timezone.utc)` correctly)
  - TASK-064 (B3 Finding #10, P1 High — `str(e)` leaked to clients; the refactored error handlers omit `context={"error_details": str(e)}`)
