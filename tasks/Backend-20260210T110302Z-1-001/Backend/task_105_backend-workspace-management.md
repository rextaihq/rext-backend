# Task 105: Replace Hardcoded Permission Resources with Dynamic Database Query in Super Admin Check

## Metadata
- **Task ID:** TASK-105
- **Source:** Backend Workspace Management Audit (Finding #21 under P2 Medium)
- **Audit Report:** `audit-reports/backend-workspace-management.md`
- **Priority:** P2 Medium
- **Category:** bug
- **Effort Estimate:** small (< 1 hour)

---

## Description

In `src/services/workspace_permission_service.py` at lines 62-67, the super admin permission resolution hardcodes a list of five resource types: `['workspace', 'content', 'topic', 'knowledge', 'member']`. When a user is identified as a `super_admin`, the code queries the `Permission` table filtering by these five resources to build the "all permissions" list. This means that if any new permission resources are added to the `permissions` table in the database (e.g., `media`, `integration`, `notification`, `billing`, `audit`), the super admin will **not** automatically receive those permissions.

The `Permission` model (`src/api/models/user_models/permissions.py`) has a `resource` column of type `String(50)` and a `name` column of type `String(150)`. Permission names use dot notation (e.g., `content.create`, `topic.read`, `member.invite`). The `resource` field groups permissions by category. New resources can be added via database seeds or migrations without any code changes — except that the super admin check won't pick them up because of this hardcoded list.

This is particularly problematic in a growing application like Rext AI where new features (media management, billing, notifications) are being added regularly and each introduces new permission resources. A super admin who should have unrestricted access would silently lose permissions to manage these new features until a developer remembers to update this hardcoded list.

The correct approach, per RBAC best practices, is to query all distinct permission names from the database, ensuring that super admins always have complete access regardless of what resources exist.

---

## Current Code

```python
# File: src/services/workspace_permission_service.py
# Lines: 60-68
        if is_super_admin:
            # Super admin gets all permissions
            all_permissions_result = await db.execute(
                select(Permission.name)
                .where(Permission.resource.in_([
                    'workspace', 'content', 'topic', 'knowledge', 'member'
                ]))
            )
            all_permissions = [row[0] for row in all_permissions_result.all()]
```

---

## Why This Matters (Context & Reasoning)

The `WorkspacePermissionService.get_user_workspace_permissions()` method is called on every workspace page load from the frontend via `GET /{workspace_id}/permissions/me`. It determines what actions the user can perform in the UI. For super admins (platform-level administrators), this should return **all** permissions for the workspace context, so they can manage all aspects of any workspace.

The current hardcoded list was likely added when the application only had five permission resource types. However, the application has grown to include additional features (media, integrations, billing, notifications, audit logging), each of which likely has its own permission resources in the database. Super admins accessing workspaces would find they cannot manage these newer features from the UI because the permission check returns only the five original resource types.

The risk of not fixing this is that every time a new permission resource is added, a developer must also update this hardcoded list — a maintenance trap that will inevitably be forgotten.

---

## Impact

- **Severity:** Super admins silently lose permissions for any resource types not in the hardcoded list. This manifests as disabled UI controls and blocked API calls for features that super admins should have full access to.
- **Affected Users/Flows:** All super admin users accessing workspace management, content management, and any features backed by permission resources not in the hardcoded list.
- **Blast Radius:** Affects the super admin experience across all workspaces. The issue grows worse as more permission resources are added.

---

## Recommended Solution

### Step 1: Replace the hardcoded resource list with a query for all permission names

```python
# File: src/services/workspace_permission_service.py
# Replace lines 60-68 with:
        if is_super_admin:
            # Super admin gets all permissions — query all from database
            all_permissions_result = await db.execute(
                select(distinct(Permission.name))
            )
            all_permissions = [row[0] for row in all_permissions_result.all()]
```

### Step 2: Add the `distinct` import if not already present

```python
# File: src/services/workspace_permission_service.py
# Update line 6 to include distinct:
from sqlalchemy import select, distinct
```

The full updated imports section should be:

```python
# File: src/services/workspace_permission_service.py
# Lines: 1-15
"""Service for managing workspace-specific permissions."""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.user_models.permissions import Permission
from src.api.models.user_models.role_permissions import RolePermission
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.utils.logger import logger
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/services/workspace_service.py` | 983-989 | `_assign_permissions_to_role()` uses `Permission.resource.in_(resources)` but with a dynamic `resources` parameter — not affected |
| `src/api/routes/workspaces/workspace_permissions.py` | 89-91 | Calls `WorkspacePermissionService.get_user_workspace_permissions()` — will automatically return the expanded permission set after the fix |
| `src/utils/rbac_utils.py` | N/A | Contains separate permission checking logic that may also need review for similar hardcoded lists |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Create a permission in the database with a resource not in the hardcoded list (e.g., `media.create` with resource `media`)
2. Log in as a super admin user
3. Call `GET /api/v1/workspaces/{workspace_id}/permissions/me`
4. Observe that the `permissions` array does NOT include `media.create`

### After Fix (Verify the Solution):
1. With the same setup, call `GET /api/v1/workspaces/{workspace_id}/permissions/me`
2. Observe that the `permissions` array NOW includes `media.create` and all other permissions from the database
3. Verify the response still includes all original permissions (`workspace.*`, `content.*`, `topic.*`, `knowledge.*`, `member.*`)

### Edge Cases:
- Test with an empty `permissions` table (should return empty list, not error)
- Test with a regular (non-super-admin) user (should NOT be affected by this change — regular users get role-based permissions as before)

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "permission" -v
```

---

## Acceptance Criteria

- [ ] The hardcoded resource list `['workspace', 'content', 'topic', 'knowledge', 'member']` is removed from `workspace_permission_service.py`
- [ ] Super admin permission resolution queries all distinct permission names from the database
- [ ] Regular (non-super-admin) users are not affected — their permissions are still resolved by role
- [ ] Adding a new permission resource to the database automatically makes it available to super admins
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [SQLAlchemy `distinct()` function](https://docs.sqlalchemy.org/en/20/core/sqlelement.html#sqlalchemy.sql.expression.distinct) — documentation for querying distinct values
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [OWASP Access Control Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Access_Control_Cheat_Sheet.html) — recommends that admin roles should be derived from the permission store, not hardcoded in application logic
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-103 (B4: Missing `deleted_at` Filter in Permission Service — same file, same method), TASK-012 (B1: `PermissionChecker` Duplicates Permission Query Without Redis Cache)
