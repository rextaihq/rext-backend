# Task 095: Fix Owner Removal Protection — Replace Fragile `is_default` Check with Role-Based Ownership Verification

## Metadata
- **Task ID:** TASK-095
- **Source:** Backend Workspace Management (Finding #9 under P1 High)
- **Audit Report:** `audit-reports/backend-workspace-management.md`
- **Priority:** P1 High
- **Category:** security
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `remove_workspace_member` endpoint in `src/api/routes/workspaces/workspace_members.py` (line 256) uses the `member.is_default` boolean flag to determine whether a member is the workspace owner and should be protected from removal. This check is semantically incorrect and fragile for three reasons:

1. **`is_default` means "default workspace for user", not "owner."** The `WorkspaceMembers.is_default` column (defined in `src/api/models/workspace_models/workspace_member.py:20`) is a `Boolean` with `default=False`. It is set to `True` when a workspace is designated as a user's default workspace — not when the user is the owner. These are fundamentally different concepts: a user can have a default workspace they don't own, and an owner might not have their owned workspace set as default.

2. **If `is_default` is accidentally unset, the owner loses protection.** Any code path or manual database change that sets `is_default = False` on the owner's membership record would allow the owner to be removed from their own workspace.

3. **A non-owner could have `is_default = True`.** If a workspace is set as the default for a regular member (e.g., because it's the first workspace they joined), the `is_default` guard would incorrectly prevent removal of a non-owner member.

The correct approach is to query the `user_roles` table joined with `roles` to check if the member being removed has the `workspace_owner` role in that workspace. The `UserRole` model (`src/api/models/user_models/user_roles.py`) already stores workspace-scoped role assignments via `user_id`, `role_id`, and `workspace_id` columns, and the `Role` model (`src/api/models/user_models/roles.py`) has a `name` column that stores role identifiers like `workspace_owner`.

---

## Current Code

```python
# File: src/api/routes/workspaces/workspace_members.py
# Lines: 255-264
    # Validate member can be removed
    if member.is_default:
        raise RextValidationException(
            message="Cannot remove workspace owner",
            field_errors={
                "member_id": ["This member is the workspace owner and cannot be removed"]
            },
            error_code=ErrorCode.VALIDATION_ERROR,
            error_severity=ErrorSeverity.ERROR,
        )
```

```python
# File: src/api/models/workspace_models/workspace_member.py
# Lines: 19-20
    status = Column(String(50), default="pending")  # active, inactive, pending
    is_default = Column(Boolean, default=False)
```

---

## Why This Matters (Context & Reasoning)

Workspace ownership is a critical authorization concept. The owner is the user who created the workspace and has ultimate control over its settings, members, and lifecycle. Removing the owner from a workspace would leave it in an orphaned state with no one able to perform owner-level actions (like deleting the workspace or managing billing).

The current `is_default` check provides only accidental protection — it happens to work in the common case where the owner's workspace is also their default, but it's not a reliable guard. In production, edge cases like workspace transfers, re-ordering defaults, or data migrations could easily break this assumption, leading to an irreversible state where the owner is removed.

---

## Impact

- **Severity:** Workspace owner could potentially be removed from their own workspace if `is_default` state diverges from actual ownership. This would leave the workspace in an orphaned state.
- **Affected Users/Flows:** The "Remove Member" action on workspace member management pages. Any admin or user with `member.remove` permission could trigger this.
- **Blast Radius:** Isolated to the `DELETE /workspaces/{workspace_id}/members/{member_id}` endpoint, but the consequences (orphaned workspace) affect the entire workspace.

---

## Recommended Solution

### Step 1: Add imports for UserRole and Role models

```python
# File: src/api/routes/workspaces/workspace_members.py
# Add to the existing imports at the top of the file (around lines 1-20):
from src.api.models.user_models.user_roles import UserRole
from src.api.models.user_models.roles import Role
from sqlalchemy import select
```

### Step 2: Replace the `is_default` check with a role-based ownership query

```python
# File: src/api/routes/workspaces/workspace_members.py
# Replace lines 255-264 with:

    # Validate member can be removed — check if they are the workspace owner by role
    owner_check = await db.execute(
        select(UserRole)
        .join(Role, Role.id == UserRole.role_id)
        .where(
            UserRole.user_id == member.user_id,
            UserRole.workspace_id == workspace.id,
            Role.name == "workspace_owner",
        )
    )
    if owner_check.scalar_one_or_none() is not None:
        raise RextValidationException(
            message="Cannot remove workspace owner",
            field_errors={
                "member_id": ["This member is the workspace owner and cannot be removed"]
            },
            error_code=ErrorCode.VALIDATION_ERROR,
            error_severity=ErrorSeverity.ERROR,
        )
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/routes/workspaces/workspace_members.py` | `126` | `is_default` is also serialized in the member list response — this is informational and correct to keep |
| `src/services/workspace_service.py` | `verify_user_is_workspace_owner()` | Existing method that checks ownership by querying `WorkspaceModel.user_id` — consider using this instead or ensuring consistency |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Create a workspace as User A (owner).
2. Set User A's `is_default = False` for that workspace membership (e.g., via direct DB update: `UPDATE workspace_members SET is_default = false WHERE user_id = '<user_a_id>' AND workspace_id = '<workspace_id>'`).
3. As another admin user, attempt to remove User A via `DELETE /workspaces/{workspace_id}/members/{member_id}`.
4. Observe that the removal succeeds (no protection) — **this is the bug**.

### After Fix (Verify the Solution):
1. Repeat steps 1-3 above with `is_default = False`.
2. Observe that the removal is blocked with the error "Cannot remove workspace owner" — because the check now queries the `user_roles` table for the `workspace_owner` role.
3. Verify that non-owner members (even those with `is_default = True`) can still be removed.
4. Verify that the workspace owner with `is_default = True` is also correctly protected (regression test).

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/unit/routes/ -k "workspace_member" -v
cd rext-backend && python -m pytest tests/security/ -k "workspace" -v
```

---

## Acceptance Criteria

- [ ] Owner removal protection uses `user_roles` + `roles` tables instead of `is_default` flag
- [ ] Workspace owner cannot be removed regardless of `is_default` value
- [ ] Non-owner members can still be removed normally
- [ ] Non-owner members with `is_default = True` can be removed (they are not falsely protected)
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [SQLAlchemy 2.0 — Joins](https://docs.sqlalchemy.org/en/20/tutorial/data_select.html#explicit-from-clauses-and-joins) — documentation on using `.join()` with `select()` for querying related tables
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [OWASP Access Control Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Access_Control_Cheat_Sheet.html) — recommends role-based access control (RBAC) over attribute-based checks for authorization decisions
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-090 (Missing Soft-Delete Filter in Workspace Resolvers) — another workspace authorization issue in B4
