# Task 070: Route Layer Calls Non-Existent `_get_role_or_404()` on RoleService

## Metadata
- **Task ID:** TASK-070
- **Source:** B3 - User Management (Finding #14 under P1 High)
- **Audit Report:** `audit-reports/backend-user-management.md`
- **Priority:** P1 High
- **Category:** bug
- **Effort Estimate:** small (< 1 hour)

---

## Description

The user roles route file `src/api/routes/users/roles.py` calls `service._get_role_or_404()` at lines 62 and 114 on a `RoleService` instance. However, `RoleService` (defined in `src/services/role_service.py`) does **not** have a `_get_role_or_404()` method. This method only exists on `PermissionService` (defined in `src/services/permission_service.py` at line 340). Since `RoleService` does not inherit from `PermissionService`, these calls will raise an `AttributeError` at runtime every time a role is assigned or revoked via these endpoints.

This is worse than just a private-method encapsulation violation — it is an outright runtime crash bug. The `assign_role_to_user` endpoint (line 23) and `revoke_role_from_user` endpoint (line 87) will both fail when they attempt to fetch role details for the success response. The role assignment/revocation itself likely succeeds (since `service.assign_role()` and `service.revoke_role()` are valid methods), but the response construction crashes before the client receives a proper response.

`RoleService` does have a functionally equivalent **public** method called `get_role_by_id()` (line 706 of `role_service.py`) that queries a role by UUID and raises `ResourceNotFoundException` if not found. This is the correct method to call.

The same `_get_role_or_404()` pattern appears in three additional locations in `src/api/routes/roles/modules/role_crud.py` (lines 107, 251, 350), but those files import and instantiate the correct `PermissionService` class where the method actually exists. However, they still violate Python encapsulation by calling a private (underscore-prefixed) method from outside the class.

---

## Current Code

```python
# File: rext-backend/src/api/routes/users/roles.py
# Line 62 (inside assign_role_to_user):
    role = await service._get_role_or_404(assignment_data.role_id)
```

```python
# File: rext-backend/src/api/routes/users/roles.py
# Lines 111-114 (inside revoke_role_from_user):
    service = RoleService(db)

    # Get role for response before revoking
    role = await service._get_role_or_404(UUID(role_id))
```

---

## Why This Matters (Context & Reasoning)

The `assign_role_to_user` and `revoke_role_from_user` endpoints are used by administrators to manage user permissions within the application. When an admin assigns or revokes a role, the system needs to return the role's display name in the success response. The call to `_get_role_or_404()` fetches the role details for this purpose.

Because `RoleService` doesn't have this method, the endpoints crash after the business operation (assign/revoke) has already been committed to the database. This means the database state changes successfully, but the client receives a 500 error — creating a confusing experience where the admin thinks the operation failed but it actually succeeded. This is particularly dangerous for destructive operations like role revocation, where the admin might retry the operation.

Additionally, the `@db_transaction_handler` decorator wrapping these endpoints may roll back the transaction when it catches the `AttributeError`, meaning the assign/revoke may also fail to persist. The behavior depends on whether `auto_commit=True` commits before or after the response construction.

---

## Impact

- **Severity:** Runtime `AttributeError` crash on both role assignment and role revocation endpoints. These endpoints are non-functional.
- **Affected Users/Flows:** Admin users managing role assignments. `POST /{user_id}/roles` and `DELETE /{user_id}/roles/{role_id}` endpoints are broken.
- **Blast Radius:** Limited to role assignment/revocation via the user routes. The `GET /{user_id}/roles` endpoint (line 135) does not call this method and works correctly.

---

## Recommended Solution

### Step 1: Replace `_get_role_or_404()` with `get_role_by_id()` in the assign endpoint

```python
# File: rext-backend/src/api/routes/users/roles.py
# Replace line 62:
# OLD: role = await service._get_role_or_404(assignment_data.role_id)
# NEW:
    role = await service.get_role_by_id(assignment_data.role_id)
```

### Step 2: Replace `_get_role_or_404()` with `get_role_by_id()` in the revoke endpoint

```python
# File: rext-backend/src/api/routes/users/roles.py
# Replace line 114:
# OLD: role = await service._get_role_or_404(UUID(role_id))
# NEW:
    role = await service.get_role_by_id(UUID(role_id))
```

Both methods perform the same operation — query the `Role` table by ID and raise `ResourceNotFoundException` if not found. No behavior change is expected.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/api/routes/roles/modules/role_crud.py` | `107, 251, 350` | Calls `service._get_role_or_404()` on a `PermissionService` instance — method exists but is private. Should use public API. |
| `rext-backend/src/services/permission_service.py` | `217, 281` | Internal calls to `self._get_role_or_404()` — valid private method usage within the owning class. No change needed. |
| `rext-backend/src/services/role_service.py` | `706` | Public `get_role_by_id()` method that should be used as the replacement. |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Log in as an admin user with `user.manage_roles` permission.
2. Send a `POST` request to `/api/users/{user_id}/roles` with a valid role assignment payload.
3. Observe that the request returns a 500 Internal Server Error with an `AttributeError: 'RoleService' object has no attribute '_get_role_or_404'` in the server logs.
4. Similarly, send a `DELETE` request to `/api/users/{user_id}/roles/{role_id}` and observe the same crash.

### After Fix (Verify the Solution):
1. Repeat the role assignment `POST` request.
2. Verify it returns a 200 response with the role details including `role_name` and `role_display_name`.
3. Repeat the role revocation `DELETE` request.
4. Verify it returns a 200 response with the revoked role name.
5. Verify the database state matches the expected changes (role assigned/revoked).

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "role" -v
```

---

## Acceptance Criteria

- [ ] `service._get_role_or_404()` on line 62 is replaced with `service.get_role_by_id()`
- [ ] `service._get_role_or_404()` on line 114 is replaced with `service.get_role_by_id()`
- [ ] `POST /{user_id}/roles` endpoint returns 200 with role details on success
- [ ] `DELETE /{user_id}/roles/{role_id}` endpoint returns 200 with role name on success
- [ ] No `AttributeError` in server logs for these endpoints
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Python Name Mangling / Private Methods](https://docs.python.org/3.11/tutorial/classes.html#private-variables) — conventions for private methods in Python
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [Python Naming Conventions — PEP 8](https://peps.python.org/pep-0008/#method-names-and-instance-variables) — single underscore prefix indicates "internal use" and should not be accessed from outside the class
- **Related Issues/PRs:** None identified

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** None — the `role_crud.py` occurrences use `PermissionService` where the method exists (different class, different scope)
