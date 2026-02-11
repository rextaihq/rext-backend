# Task 103: Missing `deleted_at` Filter in Permission Service Allows Permission Loading for Soft-Deleted Workspaces

## Metadata
- **Task ID:** TASK-103
- **Source:** B4 - Workspace Management (Finding #22 under P2 Medium)
- **Audit Report:** `audit-reports/backend-workspace-management.md`
- **Priority:** P2 Medium
- **Category:** security
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `WorkspacePermissionService` in `src/services/workspace_permission_service.py` queries the `WorkspaceModel` table to verify workspace existence before loading permissions, but none of its workspace queries include a `deleted_at.is_(None)` filter. This means permissions can be successfully loaded for soft-deleted workspaces — workspaces that have been "deleted" by their owner and are in the 30-day recovery period before permanent deletion.

Specifically, there are two affected queries:

1. **`get_user_workspace_permissions()` line 42:** The workspace existence check `select(WorkspaceModel).where(WorkspaceModel.id == workspace_id)` does not filter out soft-deleted workspaces. If a workspace has `deleted_at` set (meaning it was soft-deleted), the query still returns it as valid, and the method proceeds to load and return the user's permissions for that deleted workspace.

2. **`get_user_workspace_permissions_by_slug()` line 149:** Similarly, `select(WorkspaceModel).where(WorkspaceModel.slug == workspace_slug)` does not filter by `deleted_at`, allowing permission lookups for deleted workspaces by slug.

The `WorkspaceModel` has a `deleted_at` column (defined at `workspace_model.py:23`) that is set to the current timestamp when a workspace is soft-deleted via `WorkspaceService.delete_workspace()` (at `workspace_service.py:887`). The soft-delete design intent is that deleted workspaces should be invisible to users for 30 days (recovery period) and then permanently deleted. However, the permission service bypasses this by not checking the soft-delete flag.

This is related to but separate from TASK-090 (Missing Soft-Delete Filter in Workspace Resolvers in `workspace_utils.py`). While TASK-090 addresses the general workspace resolution utilities, this task specifically addresses the permission service, which is a security-sensitive component — it controls what users are authorized to do within a workspace.

According to SQLAlchemy soft-delete best practices, every query that reads workspace data should include a `deleted_at IS NULL` filter unless specifically designed to access deleted records (e.g., admin recovery endpoints). The `sqlalchemy-easy-softdelete` library and SQLAlchemy's own `do_orm_execute` event hook can automate this, but the simplest fix is adding the filter explicitly to the affected queries.

---

## Current Code

```python
# File: rext-backend/src/services/workspace_permission_service.py
# Lines: 40-47 — Missing deleted_at filter on workspace existence check
        # Check if workspace exists
        workspace_result = await db.execute(
            select(WorkspaceModel).where(WorkspaceModel.id == workspace_id)
        )
        workspace = workspace_result.scalar_one_or_none()

        if not workspace:
            raise ValueError(f"Workspace {workspace_id} not found")
```

```python
# File: rext-backend/src/services/workspace_permission_service.py
# Lines: 147-154 — Missing deleted_at filter on workspace slug lookup
        # Get workspace by slug
        workspace_result = await db.execute(
            select(WorkspaceModel).where(WorkspaceModel.slug == workspace_slug)
        )
        workspace = workspace_result.scalar_one_or_none()

        if not workspace:
            raise ValueError(f"Workspace with slug '{workspace_slug}' not found")
```

---

## Why This Matters (Context & Reasoning)

The `WorkspacePermissionService` is called by three permission-related endpoints in `workspace_permissions.py`:

1. `GET /{workspace_id}/permissions/me` — loads the current user's permissions for a workspace
2. `GET /{workspace_id}/permissions/check` — checks if the user has a specific permission
3. `POST /{workspace_id}/permissions/refresh` — refreshes permissions (delegates to `get_my_workspace_permissions`)

These endpoints are critical for the multi-tenant permission model. The frontend calls `GET /permissions/me` on every workspace page load to determine what UI elements to show and what actions to allow. If a user can load permissions for a deleted workspace:

1. **The frontend may render a workspace that should be inaccessible.** If the workspace detail endpoint (which does have soft-delete filtering via `workspace_utils.py`) returns 404 but the permission endpoint returns valid permissions, the frontend state becomes inconsistent.
2. **Permission checks return `true` for deleted workspaces.** An API consumer could check `GET /{deleted_workspace_id}/permissions/check?permission=content.create` and receive `has_permission: true`, which is incorrect — no one should have any permissions on a deleted workspace.
3. **Super admin check returns all permissions for deleted workspaces.** The super admin codepath on lines 60-85 returns all permissions without checking workspace deletion state, meaning super admins appear to have full access to deleted workspaces.

---

## Impact

- **Severity:** Users can query and receive valid permission data for workspaces that have been soft-deleted, bypassing the intended deletion behavior.
- **Affected Users/Flows:** All permission-related API calls: `GET /permissions/me`, `GET /permissions/check`, `POST /permissions/refresh`.
- **Blast Radius:** Moderate — affects all 3 permission endpoints. The same missing filter pattern exists in other services (see Other Affected Locations).

---

## Recommended Solution

Add `WorkspaceModel.deleted_at.is_(None)` to both workspace queries in the permission service. This ensures soft-deleted workspaces are treated as non-existent for permission purposes.

### Step 1: Fix the workspace ID lookup in `get_user_workspace_permissions()`

```python
# File: rext-backend/src/services/workspace_permission_service.py
# Replace lines 40-44 with:
        # Check if workspace exists (exclude soft-deleted)
        workspace_result = await db.execute(
            select(WorkspaceModel).where(
                WorkspaceModel.id == workspace_id,
                WorkspaceModel.deleted_at.is_(None),
            )
        )
        workspace = workspace_result.scalar_one_or_none()
```

### Step 2: Fix the workspace slug lookup in `get_user_workspace_permissions_by_slug()`

```python
# File: rext-backend/src/services/workspace_permission_service.py
# Replace lines 147-151 with:
        # Get workspace by slug (exclude soft-deleted)
        workspace_result = await db.execute(
            select(WorkspaceModel).where(
                WorkspaceModel.slug == workspace_slug,
                WorkspaceModel.deleted_at.is_(None),
            )
        )
        workspace = workspace_result.scalar_one_or_none()
```

### Full updated file for reference:

```python
# File: rext-backend/src/services/workspace_permission_service.py
"""Service for managing workspace-specific permissions."""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.user_models.permissions import Permission
from src.api.models.user_models.role_permissions import RolePermission
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.utils.logger import logger


class WorkspacePermissionService:
    """Service for workspace permission operations."""

    @staticmethod
    async def get_user_workspace_permissions(
        db: AsyncSession,
        user_id: UUID,
        workspace_id: UUID
    ) -> dict:
        """
        Get user's role and permissions for a specific workspace.

        Args:
            db: Database session
            user_id: User ID
            workspace_id: Workspace ID

        Returns:
            Dict with workspace_id, workspace_slug, user_role, and permissions list

        Raises:
            ValueError: If workspace not found or user doesn't have access
        """
        # Check if workspace exists (exclude soft-deleted)
        workspace_result = await db.execute(
            select(WorkspaceModel).where(
                WorkspaceModel.id == workspace_id,
                WorkspaceModel.deleted_at.is_(None),
            )
        )
        workspace = workspace_result.scalar_one_or_none()

        if not workspace:
            raise ValueError(f"Workspace {workspace_id} not found")

        # Check if user is super_admin FIRST (super_admin has access to all workspaces)
        super_admin_check = await db.execute(
            select(UserRole, Role)
            .join(Role, Role.id == UserRole.role_id)
            .where(UserRole.user_id == user_id)
            .where(UserRole.workspace_id == None)
            .where(Role.name == 'super_admin')
        )
        is_super_admin = super_admin_check.first() is not None

        if is_super_admin:
            # Super admin gets all permissions
            all_permissions_result = await db.execute(
                select(Permission.name)
                .where(Permission.resource.in_([
                    'workspace', 'content', 'topic', 'knowledge', 'member'
                ]))
            )
            all_permissions = [row[0] for row in all_permissions_result.all()]

            logger.info(
                f"Super admin access granted for user {user_id} in workspace {workspace_id}",
                extra={
                    "user_id": str(user_id),
                    "workspace_id": str(workspace_id),
                    "role": "super_admin",
                    "permission_count": len(all_permissions)
                }
            )

            return {
                "workspace_id": str(workspace_id),
                "workspace_slug": workspace.slug,
                "user_role": "super_admin",
                "permissions": all_permissions
            }

        # Get user's workspace-specific role
        user_role_result = await db.execute(
            select(UserRole, Role)
            .join(Role, Role.id == UserRole.role_id)
            .where(UserRole.user_id == user_id)
            .where(UserRole.workspace_id == workspace_id)
        )
        user_role_data = user_role_result.first()

        if not user_role_data:
            raise ValueError(f"User {user_id} does not have access to workspace {workspace_id}")

        user_role, role = user_role_data

        # Get permissions for the user's workspace role
        permissions_result = await db.execute(
            select(Permission.name)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role.id)
            .distinct()
        )
        permissions = [row[0] for row in permissions_result.all()]

        logger.info(
            f"Loaded workspace permissions for user {user_id} in workspace {workspace_id}",
            extra={
                "user_id": str(user_id),
                "workspace_id": str(workspace_id),
                "role": role.name,
                "permission_count": len(permissions)
            }
        )

        return {
            "workspace_id": str(workspace_id),
            "workspace_slug": workspace.slug,
            "user_role": role.name,
            "permissions": permissions
        }

    @staticmethod
    async def get_user_workspace_permissions_by_slug(
        db: AsyncSession,
        user_id: UUID,
        workspace_slug: str
    ) -> dict:
        """
        Get user's permissions for workspace by slug.

        Args:
            db: Database session
            user_id: User ID
            workspace_slug: Workspace slug

        Returns:
            Dict with workspace permissions

        Raises:
            ValueError: If workspace not found or user doesn't have access
        """
        # Get workspace by slug (exclude soft-deleted)
        workspace_result = await db.execute(
            select(WorkspaceModel).where(
                WorkspaceModel.slug == workspace_slug,
                WorkspaceModel.deleted_at.is_(None),
            )
        )
        workspace = workspace_result.scalar_one_or_none()

        if not workspace:
            raise ValueError(f"Workspace with slug '{workspace_slug}' not found")

        return await WorkspacePermissionService.get_user_workspace_permissions(
            db, user_id, workspace.id
        )

    @staticmethod
    async def check_user_permission(
        db: AsyncSession,
        user_id: UUID,
        workspace_id: UUID,
        permission: str
    ) -> bool:
        """
        Check if user has specific permission in workspace.

        Args:
            db: Database session
            user_id: User ID
            workspace_id: Workspace ID
            permission: Permission name (e.g., "topic.create")

        Returns:
            True if user has permission, False otherwise
        """
        try:
            perms = await WorkspacePermissionService.get_user_workspace_permissions(
                db, user_id, workspace_id
            )
            return permission in perms["permissions"]
        except ValueError:
            return False
```

---

## Other Affected Locations

The same missing `deleted_at` filter pattern exists in several other services that query `WorkspaceModel` without soft-delete filtering:

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/utils/workspace_utils.py` | `89, 95` | `async_resolve_workspace()` — addressed in TASK-090 |
| `rext-backend/src/services/member_service.py` | `79` | `select(WorkspaceModel).where(WorkspaceModel.id == workspace_id)` — no deleted_at filter |
| `rext-backend/src/services/role_service.py` | `366` | `select(WorkspaceModel).where(WorkspaceModel.id == workspace_id)` — no deleted_at filter |
| `rext-backend/src/services/invitation_service.py` | `119` | `select(WorkspaceModel).where(WorkspaceModel.id == workspace_id)` — no deleted_at filter |
| `rext-backend/src/services/knowledge_service.py` | `678` | `select(WorkspaceModel).where(WorkspaceModel.id == workspace_id)` — no deleted_at filter |
| `rext-backend/src/api/routes/users/invitations.py` | `296` | `select(WorkspaceModel).where(WorkspaceModel.id == invitation.workspace_id)` — no deleted_at filter |
| `rext-backend/src/api/routes/users/roles.py` | `70` | `select(WorkspaceModel).where(WorkspaceModel.id == assignment_data.workspace_id)` — no deleted_at filter |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Create a workspace and note its UUID.
2. Call `GET /api/v1/workspaces/{workspace_id}/permissions/me` — observe valid permissions returned.
3. Soft-delete the workspace via `DELETE /api/v1/workspaces/{workspace_id}`.
4. Call `GET /api/v1/workspaces/{workspace_id}/permissions/me` again — observe that permissions are **still returned** (this is the bug).

### After Fix (Verify the Solution):
1. Create a workspace and note its UUID.
2. Call `GET /api/v1/workspaces/{workspace_id}/permissions/me` — observe valid permissions returned.
3. Soft-delete the workspace via `DELETE /api/v1/workspaces/{workspace_id}`.
4. Call `GET /api/v1/workspaces/{workspace_id}/permissions/me` again — should now return an error (workspace not found / no access).
5. Call `GET /api/v1/workspaces/{workspace_id}/permissions/check?permission=content.create` — should return `has_permission: false` or an error.

### Edge Cases:
- Test with a super admin user — should also fail for deleted workspaces.
- Test workspace lookup by slug after soft-deletion.
- Test the `check_user_permission()` method — should return `False` for deleted workspaces.

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "permission" -v
```

---

## Acceptance Criteria

- [ ] `get_user_workspace_permissions()` includes `WorkspaceModel.deleted_at.is_(None)` in its workspace query
- [ ] `get_user_workspace_permissions_by_slug()` includes `WorkspaceModel.deleted_at.is_(None)` in its workspace query
- [ ] Permission lookups for soft-deleted workspaces return an error (not valid permissions)
- [ ] `check_user_permission()` returns `False` for soft-deleted workspaces
- [ ] Super admin permission checks also respect soft-delete (cannot get permissions for deleted workspaces)
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [SQLAlchemy WHERE Clauses](https://docs.sqlalchemy.org/en/20/tutorial/data_select.html#the-where-clause) — demonstrates proper use of `.where()` with multiple conditions
- **Security Advisory:** N/A (no CVE, but relates to authorization bypass on deleted resources)
- **Migration Guide:** N/A
- **Best Practice Reference:** [Mastering Soft Delete: Advanced SQLAlchemy Techniques](https://theshubhendra.medium.com/mastering-soft-delete-advanced-sqlalchemy-techniques-4678f4738947) — recommends always filtering by `deleted_at IS NULL` in production queries
- **Related Issues/PRs:** [SQLAlchemy Issue #7973 — Best practice for soft-delete filters with asyncio API](https://github.com/sqlalchemy/sqlalchemy/issues/7973) — discusses automatic soft-delete filtering approaches

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-090 (Missing Soft-Delete Filter in Workspace Resolvers in `workspace_utils.py` — same pattern, different file)
