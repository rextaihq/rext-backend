# Task 104: Replace HTTPException with Custom Exception Hierarchy in Workspace Routes

## Metadata
- **Task ID:** TASK-104
- **Source:** Backend Workspace Management Audit (Finding #20 under P2 Medium)
- **Audit Report:** `audit-reports/backend-workspace-management.md`
- **Priority:** P2 Medium
- **Category:** bug
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The workspace routes module uses two conflicting error handling patterns. Some routes raise FastAPI's built-in `HTTPException` directly (in `workspace_permissions.py` and `workspace_personas.py`), while the rest of the workspace routes use the project's custom exception hierarchy (`ResourceNotFoundException`, `RextValidationException`, `DuplicateResourceException`, etc.) defined in `src/api/middleware/exceptions.py`. The custom exceptions are caught by a global error handler middleware and converted to structured JSON responses with `error_code`, `error_severity`, and `context` fields. In contrast, `HTTPException` produces a different response shape (`{"detail": "..."}`) that lacks these structured fields.

Specifically, `workspace_permissions.py` has three catch-all `except Exception` blocks (lines 110-121, 197-209, 334-346) that catch any exception, log it, and re-raise as `HTTPException(status_code=500, detail="...")`. This pattern is problematic because: (1) it swallows the original exception type and stack trace from the client perspective, (2) it produces a `{"detail": "..."}` response instead of the structured `{"success": false, "message": "...", "error_code": "...", "error_severity": "..."}` format the frontend expects, and (3) it catches `ValueError` exceptions from `WorkspacePermissionService` and converts them to generic 500 errors when they should be 404s or 403s.

Additionally, `workspace_personas.py` raises `HTTPException(status_code=404, detail="Persona not found")` at lines 82-85, 161-164, and 208-211 for "not found" scenarios instead of using `ResourceNotFoundException`. This means persona 404 errors have a different response format than workspace 404 errors, making frontend error parsing unreliable.

The `WorkspacePermissionService` (in `src/services/workspace_permission_service.py`) compounds the issue by raising `ValueError` (lines 47 and 97) for "workspace not found" and "user has no access" scenarios, rather than using the custom exception hierarchy. These `ValueError` exceptions are then caught by the route-level catch-all blocks and converted to `HTTPException(500)`, which masks a 404 or 403 error as a 500 Internal Server Error.

According to FastAPI best practices, applications should define a consistent exception hierarchy and use a global exception handler to convert these to HTTP responses. The project already has this infrastructure in place — the custom exceptions in `src/api/middleware/exceptions.py` are designed for exactly this purpose. The workspace permission and persona routes simply need to be updated to use them.

---

## Current Code

```python
# File: src/api/routes/workspaces/workspace_permissions.py
# Lines: 108-121 (first occurrence of the pattern)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error retrieving workspace permissions: {str(e)}",
            extra={
                "user_id": user.get("identity"),
                "workspace_id": workspace_id
            }
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve workspace permissions"
        )
```

```python
# File: src/api/routes/workspaces/workspace_personas.py
# Lines: 81-85 (persona not found pattern)
    if not persona:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Persona not found"
        )
```

```python
# File: src/services/workspace_permission_service.py
# Lines: 46-47 (ValueError for workspace not found)
        if not workspace:
            raise ValueError(f"Workspace {workspace_id} not found")
```

```python
# File: src/services/workspace_permission_service.py
# Lines: 96-97 (ValueError for access denied)
        if not user_role_data:
            raise ValueError(f"User {user_id} does not have access to workspace {workspace_id}")
```

---

## Why This Matters (Context & Reasoning)

The workspace permission endpoints are critical for the frontend permission system. Every workspace page load calls `GET /{workspace_id}/permissions/me` to determine what the user can see and do. The persona endpoints are used for managing AI-generated content personas in workspace settings.

When these endpoints return errors in a different format than all other endpoints, the frontend error handling code must implement special-case logic, or worse, fails to display meaningful error messages. A "workspace not found" error from the permission service currently returns HTTP 500 with `{"detail": "Failed to retrieve workspace permissions"}` instead of HTTP 404 with the structured error format. This makes it impossible for the frontend to distinguish between "workspace doesn't exist" (redirect to workspace list) and "server error" (show retry button).

The risk of not fixing this is continued frontend error handling fragility and misleading 500 errors in production monitoring dashboards that should actually be 404s or 403s.

---

## Impact

- **Severity:** Frontend receives inconsistent error response formats from workspace endpoints, making reliable error handling impossible. True 404/403 errors are masked as 500 errors, inflating server error metrics and hiding real issues.
- **Affected Users/Flows:** All users loading workspace pages (permission check), all users managing personas. Frontend permission guards depend on these responses.
- **Blast Radius:** Affects 6 route handlers across 2 files, plus the permission service. Frontend error handling code for all workspace-related features is affected.

---

## Recommended Solution

### Step 1: Update `WorkspacePermissionService` to raise custom exceptions instead of `ValueError`

```python
# File: src/services/workspace_permission_service.py
# Replace lines 1-14 (imports section) with:
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
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    RextAuthorizationException,
)
from src.utils.logger import logger
```

```python
# File: src/services/workspace_permission_service.py
# Replace line 47:
#   raise ValueError(f"Workspace {workspace_id} not found")
# With:
            raise ResourceNotFoundException(
                resource_type="workspace",
                resource_id=str(workspace_id),
            )
```

```python
# File: src/services/workspace_permission_service.py
# Replace line 97:
#   raise ValueError(f"User {user_id} does not have access to workspace {workspace_id}")
# With:
            raise RextAuthorizationException(
                message=f"User does not have access to workspace",
                resource=f"workspace:{workspace_id}",
            )
```

```python
# File: src/services/workspace_permission_service.py
# Replace line 154:
#   raise ValueError(f"Workspace with slug '{workspace_slug}' not found")
# With:
            raise ResourceNotFoundException(
                message=f"Workspace with slug '{workspace_slug}' not found",
                resource_type="workspace",
            )
```

### Step 2: Remove try/except catch-all blocks from `workspace_permissions.py`

The custom exceptions will propagate to the global error handler middleware automatically. Remove the try/except blocks from all three route handlers.

```python
# File: src/api/routes/workspaces/workspace_permissions.py
# Replace the entire get_my_workspace_permissions function (lines 34-121) with:
@router.get("/{workspace_id}/permissions/me")
@require_permissions("member.read", workspace_scoped=True)
async def get_my_workspace_permissions(
    workspace_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get current user's permissions in a specific workspace.
    """
    user_id = UUID(user["identity"])

    # Resolve workspace ID (handles both UUID and slug)
    try:
        workspace_uuid = UUID(workspace_id)
    except ValueError:
        workspace_uuid = await async_get_workspace_id_from_identifier(db, workspace_id)

    # Use WorkspacePermissionService — exceptions propagate to global handler
    result = await WorkspacePermissionService.get_user_workspace_permissions(
        db, user_id, workspace_uuid
    )

    logger.info(
        "Retrieved workspace permissions",
        extra={
            "user_id": str(user_id),
            "workspace_id": str(workspace_uuid),
            "permission_count": len(result["permissions"]),
            "user_role": result["user_role"]
        }
    )

    return success(
        data=result,
        message="Workspace permissions retrieved successfully"
    )
```

```python
# File: src/api/routes/workspaces/workspace_permissions.py
# Replace the entire check_workspace_permission function (lines 124-209) with:
@router.get("/{workspace_id}/permissions/check")
@require_permissions("member.read", workspace_scoped=True)
async def check_workspace_permission(
    workspace_id: str,
    permission: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Check if current user has a specific permission in a workspace.
    """
    user_id = UUID(user["identity"])

    # Resolve workspace ID
    try:
        workspace_uuid = UUID(workspace_id)
    except ValueError:
        workspace_uuid = await async_get_workspace_id_from_identifier(db, workspace_id)

    # Use WorkspacePermissionService
    has_permission = await WorkspacePermissionService.check_user_permission(
        db, user_id, workspace_uuid, permission
    )

    logger.debug(
        "Permission check completed",
        extra={
            "user_id": str(user_id),
            "permission": permission,
            "workspace_id": str(workspace_uuid),
            "result": has_permission,
        }
    )

    return success(
        data={
            "has_permission": has_permission,
            "permission": permission,
            "workspace_id": str(workspace_uuid)
        },
        message="Permission check completed"
    )
```

```python
# File: src/api/routes/workspaces/workspace_permissions.py
# Replace the entire get_member_workspace_permissions function (lines 247-346) with:
@router.get("/{workspace_id}/members/{user_id}/permissions")
@require_permissions("member.read", workspace_scoped=True)
async def get_member_workspace_permissions(
    workspace_id: str,
    user_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get a specific workspace member's permissions.
    """
    current_user_id = UUID(current_user["identity"])
    target_user_id = UUID(user_id)

    # Resolve workspace ID
    try:
        workspace_uuid = UUID(workspace_id)
    except ValueError:
        workspace_uuid = await async_get_workspace_id_from_identifier(db, workspace_id)

    # Check if current user has permission to view other members' permissions
    from src.utils.rbac_utils import require_permission
    await require_permission(
        db,
        current_user_id,
        "workspace:manage_members",
        workspace_uuid,
        "workspace members"
    )

    # Get target user's permissions
    permissions = await get_user_permissions(db, target_user_id, workspace_uuid)
    roles_with_context = await get_user_roles(db, target_user_id, workspace_uuid)

    roles = [
        {
            "name": role.name,
            "display_name": role.display_name,
            "workspace_scoped": ws_id is not None,
            "workspace_id": str(ws_id) if ws_id else None
        }
        for role, ws_id in roles_with_context
    ]

    logger.info(
        "Admin viewed member permissions",
        extra={
            "current_user_id": str(current_user_id),
            "target_user_id": str(target_user_id),
            "workspace_id": str(workspace_uuid),
        }
    )

    return success(
        data={
            "user_id": str(target_user_id),
            "workspace_id": str(workspace_uuid),
            "roles": roles,
            "permissions": list(permissions)
        },
        message="Member permissions retrieved successfully"
    )
```

### Step 3: Remove unused `HTTPException` import from `workspace_permissions.py`

```python
# File: src/api/routes/workspaces/workspace_permissions.py
# Replace line 11:
#   from fastapi import APIRouter, Depends, HTTPException, status
# With:
from fastapi import APIRouter, Depends
```

### Step 4: Replace `HTTPException` with `ResourceNotFoundException` in `workspace_personas.py`

```python
# File: src/api/routes/workspaces/workspace_personas.py
# Add import at top (after line 13):
from src.api.middleware.exceptions import ResourceNotFoundException
```

```python
# File: src/api/routes/workspaces/workspace_personas.py
# Replace lines 81-85 in get_persona:
    if not persona:
        raise ResourceNotFoundException(
            resource_type="persona",
            resource_id=persona_id,
        )
```

```python
# File: src/api/routes/workspaces/workspace_personas.py
# Replace lines 160-164 in update_persona:
    if not persona:
        raise ResourceNotFoundException(
            resource_type="persona",
            resource_id=persona_id,
        )
```

```python
# File: src/api/routes/workspaces/workspace_personas.py
# Replace lines 207-211 in delete_persona:
    if not persona:
        raise ResourceNotFoundException(
            resource_type="persona",
            resource_id=persona_id,
        )
```

```python
# File: src/api/routes/workspaces/workspace_personas.py
# Update line 4 import to remove HTTPException and status:
#   from fastapi import APIRouter, Depends, Request, HTTPException, status
# With:
from fastapi import APIRouter, Depends, Request, status
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/middleware/error_handler.py` | N/A | Global error handler that catches `RextAPIException` subclasses — no changes needed, already handles the custom exceptions |
| `src/services/workspace_permission_service.py` | 179-184 | `check_user_permission()` catches `ValueError` — after Step 1, it should catch `ResourceNotFoundException` and `RextAuthorizationException` instead |
| `src/api/routes/workspaces/workspace_permissions.py` | 242-244 | `refresh_workspace_permissions()` delegates to `get_my_workspace_permissions()` — will inherit the fix automatically |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Call `GET /api/v1/workspaces/nonexistent-uuid/permissions/me` with a valid auth token
2. Observe HTTP 500 response with `{"detail": "Failed to retrieve workspace permissions"}`
3. Call `GET /api/v1/workspaces/{valid-id}/personas/nonexistent-uuid` with a valid auth token
4. Observe HTTP 404 response with `{"detail": "Persona not found"}` (no structured error fields)

### After Fix (Verify the Solution):
1. Call `GET /api/v1/workspaces/nonexistent-uuid/permissions/me` with a valid auth token
2. Expect HTTP 404 with structured response: `{"success": false, "message": "Workspace with ID 'nonexistent-uuid' not found", "error_code": "RESOURCE_NOT_FOUND", ...}`
3. Call `GET /api/v1/workspaces/{valid-id}/personas/nonexistent-uuid`
4. Expect HTTP 404 with structured response: `{"success": false, "message": "Persona with ID 'nonexistent-uuid' not found", "error_code": "RESOURCE_NOT_FOUND", ...}`
5. Verify that a user without workspace access gets HTTP 403 (not 500) from permission endpoints

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "workspace" -v
```

---

## Acceptance Criteria

- [ ] All `HTTPException` usage removed from `workspace_permissions.py` and `workspace_personas.py`
- [ ] `WorkspacePermissionService` raises `ResourceNotFoundException` instead of `ValueError` for missing workspaces
- [ ] `WorkspacePermissionService` raises `RextAuthorizationException` instead of `ValueError` for access denied
- [ ] All workspace error responses follow the structured format: `{"success": false, "message": "...", "error_code": "...", "error_severity": "..."}`
- [ ] "Workspace not found" errors return HTTP 404, not 500
- [ ] "Access denied" errors return HTTP 403, not 500
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [FastAPI Handling Errors](https://fastapi.tiangolo.com/tutorial/handling-errors/) — documents `HTTPException` vs custom exception handlers
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [FastAPI Advanced Exception Handling](https://fastapi.tiangolo.com/advanced/custom-exception-handlers/) — recommends registering custom exception handlers for application-specific exception classes
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-064 (B3: Internal Error Details Leaked to Clients via `str(e)` — same pattern of catching exceptions and re-raising as HTTPException), TASK-072 (B3: 5 Different Error Handling Patterns Across Routes)
