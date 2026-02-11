# Task 083: Remove Redundant Permission Check in Delete User Endpoint

## Metadata
- **Task ID:** TASK-083
- **Source:** B3 - User Management (Finding #24 under P2 Medium)
- **Audit Report:** `audit-reports/backend-user-management.md`
- **Priority:** P2 Medium
- **Category:** code-quality
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `delete_user` endpoint in `src/api/routes/users/management.py` (lines 134-206) performs the same authorization check twice: once via the `@require_permissions("user.delete")` decorator (line 135) and again manually inside the handler body via `service.check_user_permission(current_user_id, "user.delete")` (lines 153-156).

The `@require_permissions` decorator (defined in `src/utils/route_decorators.py`, lines 236-423) executes **before** the handler function runs. It calls `rbac_utils.check_all_permissions()`, which delegates to `rbac_utils.check_permission()`, which loads the user's permission set (Redis-cached with a 5-minute TTL) and checks whether `"user.delete"` is present. If the user lacks the permission, the decorator raises `RextAuthorizationException` and the handler never executes. By the time the handler body runs, the authorization has already been verified.

The manual `service.check_user_permission()` call inside the handler performs the same logical check --- it queries `Permission JOIN RolePermission JOIN UserRole WHERE user_id = X AND permission.name = "user.delete"` --- but does so via a direct, uncached database query (3-table JOIN). This query will always return `True` for any request that reaches the handler, because the decorator already blocked all unauthorized requests. The manual check is therefore purely redundant: it executes an unnecessary database query and has a dead `if not has_permission` branch that can never be reached.

### Addressing the "Defense in Depth" Argument

One might argue that double-checking permissions is a valid "defense in depth" security measure. However, defense in depth applies when **different layers protect against different failure modes** --- for example, a firewall rule AND an application-level check, or an authentication check AND an authorization check. In this case, the decorator and the manual check:

1. **Check the exact same permission** (`"user.delete"`) for the **exact same user** (`current_user_id`).
2. **Query the same underlying data** (the `Permission -> RolePermission -> UserRole` join chain).
3. **Run in the same request context** --- there is no possibility that the user's permissions change between the decorator check and the manual check within the same request lifecycle.
4. **Have no independent failure modes** --- if the decorator's check were to silently fail (which would be a bug in `rbac_utils`), the manual check uses a different code path (`UserService.check_user_permission`) but queries the same tables, so it would also fail for the same structural reasons (e.g., database schema issues).

A genuine defense-in-depth measure would check at a **different layer** (e.g., a database-level row policy) or check a **different condition** (e.g., verifying the target user is not a super_admin before deleting). The manual check here is not defense in depth; it is a redundant duplicate of the same check at the same layer.

Additionally, the dead code branch (lines 158-166) uses `ErrorCode.AUTHORIZATION_ERROR`, which is a non-existent `ErrorCode` enum value. If this branch could somehow be reached, it would crash with an `AttributeError` rather than returning a 403 response. This non-existent enum value is already tracked in TASK-059 (Finding #1, P0 Critical), but since this task removes the entire block, TASK-059 does not need to fix this specific occurrence.

---

## Current Code

```python
# File: src/api/routes/users/management.py
# Lines: 134-206

@router.delete("/delete/{user_id}")
@require_permissions("user.delete")  # <-- Checks permission BEFORE handler executes
async def delete_user(
    user_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Soft delete a user by setting deleted_at timestamp.
    Thin controller - permission check inline, deletion logic simple.
    Requires user.delete permission (super_admin only).
    """
    try:
        service = UserService(db)
        current_user_id = UUID(current_user.get("identity"))

        # REDUNDANT: This permission check is already done by @require_permissions("user.delete")
        has_permission = await service.check_user_permission(
            user_id=current_user_id,
            permission_name="user.delete"
        )

        if not has_permission:
            return error(
                message="Missing required permission: user.delete",
                code=ErrorCode.AUTHORIZATION_ERROR,  # <-- Non-existent enum value (TASK-059)
                status_code=403,
                severity=ErrorSeverity.HIGH,
                context={"required_permission": "user.delete"},
                request=request
            )

        # Delete workspace memberships if any
        memberships = await db.execute(
            select(WorkspaceMembers).where(WorkspaceMembers.user_id == UUID(user_id))
        )
        membership_list = memberships.scalars().all()
        if membership_list:
            await db.execute(
                delete(WorkspaceMembers).where(WorkspaceMembers.user_id == UUID(user_id))
            )
            logger.info(f"Deleted {len(membership_list)} workspace memberships for user {user_id}")
            await db.commit()

        # Delete user via service (includes validation)
        db_user = await service.delete_user(UUID(user_id))
        return success(
            data={"id": str(db_user.id)},
            request=request,
            message="User deleted successfully"
        )

    except ResourceNotFoundException:
        return error(
            message="User not found",
            code=ErrorCode.NOT_FOUND,  # <-- Non-existent enum value (TASK-059)
            status_code=404,
            severity=ErrorSeverity.MEDIUM,
            request=request
        )
    except RextValidationException as e:
        return error(
            message=str(e),
            code=ErrorCode.DEPENDENCY_ERROR,
            status_code=400,
            severity=ErrorSeverity.MEDIUM,
            request=request
        )
    except Exception as e:
        logger.error(f"Failed to delete user {user_id}: {str(e)}")
        raise
```

---

## Why This Matters (Context & Reasoning)

The `@require_permissions` decorator is the project's standard, centralized mechanism for enforcing RBAC on route handlers. It is used consistently across admin endpoints and integrates with `rbac_utils`, which provides Redis-cached permission lookups. The manual `service.check_user_permission()` call bypasses the cache entirely and issues a raw 3-table JOIN query against the database. On every single user deletion request, this adds one unnecessary database round-trip.

Beyond performance, the redundant code is actively harmful to maintainability:

1. **Dead code branch:** The `if not has_permission` block (lines 158-166) can never execute. Dead code confuses future developers who must determine whether it serves a purpose.
2. **Broken error handling in dead code:** The dead branch uses `ErrorCode.AUTHORIZATION_ERROR`, a non-existent enum value that would crash if reached. This obscures the real error handling bugs tracked by TASK-059.
3. **Misleading docstring:** The docstring says "permission check inline, deletion logic simple," implying the inline check is intentional. This teaches the wrong pattern to developers reading the code as an example.
4. **Unused variable:** `current_user_id` is only used for the redundant permission check. After removal, this variable can also be removed.

The decorator's permission flow is:
- `@require_permissions("user.delete")` -> `rbac_utils.check_all_permissions(db, user_id, ["user.delete"], workspace_uuid)` -> `rbac_utils.check_permission(db, user_id, "user.delete", workspace_uuid)` -> `get_user_permissions(db, user_id, workspace_uuid)` (Redis-cached, 5-min TTL) -> checks if `"user.delete" in permissions_set`

The manual service check's flow is:
- `service.check_user_permission(current_user_id, "user.delete")` -> `SELECT Permission ... JOIN RolePermission JOIN UserRole WHERE user_id = X AND permission.name = "user.delete"` (uncached, direct DB query)

Both check the same data, but the decorator does it more efficiently (cached) and at the correct architectural layer (before handler execution).

---

## Impact

- **Severity:** One redundant uncached 3-table JOIN database query per user deletion request. Dead code branch with a non-existent `ErrorCode` value that would crash if reached.
- **Affected Users/Flows:** Admin users deleting user accounts via `DELETE /api/v1/user/delete/{user_id}`.
- **Blast Radius:** Isolated to the `delete_user` endpoint in `management.py`. No other endpoints or callers are affected by this change.

---

## Recommended Solution

### Step 1: Remove the redundant permission check and dead code branch

Remove lines 149-166 (the `current_user_id` assignment, `check_user_permission` call, and the `if not has_permission` block):

```python
# File: src/api/routes/users/management.py
# Replace the entire delete_user function (lines 134-206) with:

@router.delete("/delete/{user_id}")
@require_permissions("user.delete")
async def delete_user(
    user_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Soft delete a user by setting deleted_at timestamp.
    Requires user.delete permission (super_admin only).
    Permission enforced by @require_permissions decorator.
    """
    try:
        service = UserService(db)

        # Delete workspace memberships if any
        memberships = await db.execute(
            select(WorkspaceMembers).where(WorkspaceMembers.user_id == UUID(user_id))
        )
        membership_list = memberships.scalars().all()
        if membership_list:
            await db.execute(
                delete(WorkspaceMembers).where(WorkspaceMembers.user_id == UUID(user_id))
            )
            logger.info(f"Deleted {len(membership_list)} workspace memberships for user {user_id}")
            await db.commit()

        # Delete user via service (includes validation)
        db_user = await service.delete_user(UUID(user_id))
        return success(
            data={"id": str(db_user.id)},
            request=request,
            message="User deleted successfully"
        )

    except ResourceNotFoundException:
        return error(
            message="User not found",
            code=ErrorCode.RESOURCE_NOT_FOUND,
            status_code=404,
            severity=ErrorSeverity.MEDIUM,
            request=request
        )
    except RextValidationException as e:
        return error(
            message=str(e),
            code=ErrorCode.DEPENDENCY_ERROR,
            status_code=400,
            severity=ErrorSeverity.MEDIUM,
            request=request
        )
    except Exception as e:
        logger.error(f"Failed to delete user {user_id}: {str(e)}")
        raise
```

**What changed:**
1. Removed `current_user_id = UUID(current_user.get("identity"))` (only used by the removed check).
2. Removed `has_permission = await service.check_user_permission(...)` call (redundant with decorator).
3. Removed the entire `if not has_permission: return error(...)` block (dead code with broken `ErrorCode.AUTHORIZATION_ERROR`).
4. Updated docstring to clarify that the decorator handles permission enforcement.
5. Changed `ErrorCode.NOT_FOUND` to `ErrorCode.RESOURCE_NOT_FOUND` in the `ResourceNotFoundException` handler (fixes the TASK-059 issue for this specific occurrence).

**Note:** The `ErrorCode.NOT_FOUND` -> `ErrorCode.RESOURCE_NOT_FOUND` fix at line 191 is technically part of TASK-059, but since we are modifying this function anyway, it is included here for convenience. If TASK-059 is completed first, this line will already be correct and this step is a no-op for that specific change.

**Note:** The `await db.commit()` at line 178 (committing workspace membership deletion before the user delete) is a separate transaction boundary issue. It is not addressed in this task to keep the scope focused.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/routes/users/user_status.py` | 48, 145, 240 | Same pattern: `is_admin(current_user)` check alongside `@require_permissions("user.update")` decorator -- redundant but uses `is_admin()` instead of `check_user_permission()`. Different implementation, same principle. (TASK-081) |
| `src/services/user_service.py` | 391-425 | `check_user_permission()` method definition -- still used by `workspace_permissions.py`, do NOT remove the method itself |
| `src/api/routes/workspaces/workspace_permissions.py` | 177 | Uses `WorkspacePermissionService.check_user_permission()` (different service, different purpose -- not redundant in that context) |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Enable SQL query logging by setting `SQLALCHEMY_ECHO=true` or adding `echo=True` to the engine configuration
2. Call `DELETE /api/v1/user/delete/{user_id}` as a super_admin user with a valid auth token
3. Observe SQL logs: you will see **two** permission-related queries:
   - First query from the `@require_permissions` decorator (via `rbac_utils.get_user_permissions`)
   - Second query from `service.check_user_permission()` (the redundant 3-table JOIN)
4. Confirm both queries check `"user.delete"` for the same user

### After Fix (Verify the Solution):
1. Call `DELETE /api/v1/user/delete/{user_id}` as a super_admin user
2. Verify SQL logs show only **one** permission-related query (from the decorator)
3. Verify the user is successfully soft-deleted (check `deleted_at` is set in the database)
4. Verify the response body is `{"data": {"id": "<user_id>"}, "message": "User deleted successfully"}`
5. Call `DELETE /api/v1/user/delete/{user_id}` as a non-admin user (no `user.delete` permission)
6. Verify a 403 Forbidden response is returned by the decorator (with `RextAuthorizationException`)
7. Call `DELETE /api/v1/user/delete/{non_existent_id}` as a super_admin user
8. Verify a 404 response with `"code": "resource_not_found"` is returned
9. Call `DELETE /api/v1/user/delete/{user_with_workspaces}` to verify workspace memberships are still cleaned up before deletion

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "delete_user or management" -v
```

---

## Acceptance Criteria

- [ ] Redundant `service.check_user_permission()` call removed from the `delete_user` handler
- [ ] Dead code branch with `ErrorCode.AUTHORIZATION_ERROR` removed
- [ ] Unused `current_user_id` variable removed
- [ ] `@require_permissions("user.delete")` decorator remains as the sole permission enforcement mechanism
- [ ] Docstring updated to reference the decorator as the permission check
- [ ] `ErrorCode.NOT_FOUND` corrected to `ErrorCode.RESOURCE_NOT_FOUND` in the `ResourceNotFoundException` handler
- [ ] User deletion still works correctly for authorized super_admin users
- [ ] Unauthorized users still receive 403 Forbidden from the decorator
- [ ] Workspace membership cleanup still executes before user deletion
- [ ] One fewer database query per delete request (the redundant 3-table JOIN is gone)
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [FastAPI -- Dependencies in Path Operation Decorators](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-in-path-operation-decorators/)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [OWASP -- Access Control Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Access_Control_Cheat_Sheet.html) -- recommends centralized access control mechanisms, not redundant inline checks
- **Defense in Depth:** [OWASP -- Defense in Depth](https://owasp.org/www-community/Defense_in_depth) -- defense in depth means multiple **independent** security layers, not duplicating the same check at the same layer
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None (but if TASK-059 is completed first, the `ErrorCode.NOT_FOUND` -> `ErrorCode.RESOURCE_NOT_FOUND` fix at line 191 will already be done)
- **Blocks:** None
- **Related:**
  - TASK-059 (P0 Critical: non-existent `ErrorCode` enum values -- this task removes the `ErrorCode.AUTHORIZATION_ERROR` occurrence and fixes the `ErrorCode.NOT_FOUND` occurrence)
  - TASK-081 (P2 Medium: redundant `is_admin()` checks alongside `@require_permissions` in `user_status.py` -- same principle, different implementation)
