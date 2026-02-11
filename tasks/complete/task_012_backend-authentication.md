# Task 012: Refactor PermissionChecker to Delegate to Cached rbac_utils

## Metadata
- **Task ID:** TASK-012
- **Source:** Backend Authentication & Authorization Audit (Finding #7 under P1 High)
- **Audit Report:** `audit-reports/backend-authentication.md`
- **Priority:** P1 High
- **Category:** code-quality
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The codebase has two independent implementations of the same permission-fetching logic. `PermissionChecker._get_user_permissions()` in `src/api/middleware/permissions.py` (lines 186-230) directly queries the database for user permissions via a join chain (`Permission → RolePermission → UserRole`), while `rbac_utils.get_user_permissions()` in `src/utils/rbac_utils.py` (lines 200-267) performs the identical query but wraps it with Redis caching using a 5-minute TTL. Both implementations are actively used in the codebase through different mechanisms: `PermissionChecker` as a FastAPI dependency injected via `Depends(require_permissions(...))` or `Depends(is_admin)`, and `rbac_utils` via the `@require_permissions` decorator in `src/utils/route_decorators.py`.

This duplication means the same permission check takes different code paths depending on which mechanism protects the endpoint. Routes using `PermissionChecker` always hit the database, while routes using the `@require_permissions` decorator benefit from Redis caching. This creates inconsistent performance characteristics and a subtle correctness issue: `PermissionChecker` uses `UserRole.workspace_id == None` (Python equality comparison) instead of `UserRole.workspace_id.is_(None)` (proper SQLAlchemy NULL comparison). While SQLAlchemy typically auto-converts `== None` to `IS NULL`, using `.is_(None)` is the recommended and explicit approach per SQLAlchemy documentation.

The fix is to make `PermissionChecker._get_user_permissions()` delegate to `rbac_utils.get_user_permissions()`, establishing a single source of truth with consistent caching.

---

## Current Code

```python
# File: src/api/middleware/permissions.py
# Lines: 185-230
    @staticmethod
    async def _get_user_permissions(
        db: Session,
        user_id: str,
        workspace_id: Optional[str] = None
    ) -> set:
        """
        Get all permissions for a user.
        ...
        """
        from sqlalchemy import select, or_

        # Query to get all permissions for user via their roles
        query = (
            select(Permission.name)
            .select_from(Permission)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(UserRole, UserRole.role_id == RolePermission.role_id)
            .where(UserRole.user_id == user_id)
        )

        # If workspace-scoped, filter by workspace or global roles (workspace_id = NULL)
        if workspace_id:
            query = query.where(
                or_(
                    UserRole.workspace_id == workspace_id,
                    UserRole.workspace_id == None  # Should be .is_(None)
                )
            )
        else:
            # Only global permissions (not workspace-specific)
            query = query.where(UserRole.workspace_id == None)  # Should be .is_(None)

        result = await db.execute(query)
        permissions = result.scalars().all()
        return {perm for perm in permissions}
```

```python
# File: src/utils/rbac_utils.py
# Lines: 200-267
async def get_user_permissions(
    db: AsyncSession,
    user_id: UUID,
    workspace_id: Optional[UUID] = None
) -> List[str]:
    """
    Get all permissions for a user (cached).
    ...
    """
    # Try cache first
    from src.api.cache.redis_client import cache
    cache_key = f"user:permissions:{user_id}:{workspace_id or 'global'}"

    if cache.is_enabled:
        cached_perms = await cache.get(cache_key)
        if cached_perms is not None:
            return cached_perms

    # Cache miss - query database
    query = (
        select(Permission.name)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user_id)
        .distinct()
    )

    if workspace_id:
        query = query.where(
            (UserRole.workspace_id == workspace_id) | (UserRole.workspace_id.is_(None))
        )
    else:
        query = query.where(UserRole.workspace_id.is_(None))

    result = await db.execute(query)
    permissions = result.scalars().all()
    permissions_list = list(permissions)

    # Cache the result for 5 minutes
    if cache.is_enabled:
        await cache.set(cache_key, permissions_list, ttl=300)

    return permissions_list
```

---

## Why This Matters (Context & Reasoning)

The RBAC system is the security backbone of the application — it governs which users can access which resources. Permission checks occur on nearly every authenticated endpoint, making this a hot path. The `PermissionChecker` dependency is used in admin routes (via `is_admin`), and the `@require_permissions` decorator is used in workspace and content routes.

Having two divergent implementations means: (1) admin routes always incur database queries for permission checks while other routes benefit from Redis caching, (2) any future changes to permission logic must be made in two places, and (3) the `== None` pattern in `PermissionChecker` could theoretically produce incorrect results with certain SQLAlchemy dialects or configurations, though PostgreSQL handles it correctly.

---

## Impact

- **Severity:** Admin and middleware-protected routes hit the database for every permission check instead of using the Redis cache. Under high traffic, this creates unnecessary database load and increased latency.
- **Affected Users/Flows:** All routes protected by `PermissionChecker` or `is_admin` dependency — includes admin endpoints, health checks, impersonation routes, security routes, and customer management routes.
- **Blast Radius:** All admin and permission-checked endpoints. Routes using `@require_permissions` decorator are not affected (they already use the cached version).

---

## Recommended Solution

### Step 1: Refactor `_get_user_permissions` to delegate to `rbac_utils.get_user_permissions()`

```python
# File: src/api/middleware/permissions.py
# Replace lines 185-230 with:
    @staticmethod
    async def _get_user_permissions(
        db: Session,
        user_id: str,
        workspace_id: Optional[str] = None
    ) -> set:
        """
        Get all permissions for a user.

        Delegates to rbac_utils.get_user_permissions() which provides
        Redis caching with a 5-minute TTL for consistent performance.

        Args:
            db: Database session
            user_id: User ID (UUID as string)
            workspace_id: Optional workspace ID for workspace-scoped permissions

        Returns:
            Set of permission names (e.g., {"user.read", "user.write"})
        """
        from uuid import UUID as UUIDType
        from src.utils.rbac_utils import get_user_permissions

        # Convert string IDs to UUID objects as expected by rbac_utils
        user_uuid = UUIDType(user_id) if isinstance(user_id, str) else user_id
        workspace_uuid = UUIDType(workspace_id) if workspace_id and isinstance(workspace_id, str) else workspace_id

        permissions_list = await get_user_permissions(db, user_uuid, workspace_uuid)
        return set(permissions_list)
```

### Step 2: Remove unused imports from permissions.py

After the refactor, the following imports in `permissions.py` are no longer needed by `_get_user_permissions` (verify they aren't used elsewhere in the file before removing):

- `RolePermission` (line 26) — check if used in `_is_super_admin` or `_validate_workspace_membership`
- `Permission` (line 27) — check if used elsewhere
- The inline `from sqlalchemy import select, or_` (line 205) — no longer needed in this method

Only remove imports that are truly unused after verifying all methods in the file.

### Step 3: Update the type annotation for `db` parameter

```python
# File: src/api/middleware/permissions.py
# Line 20: The import of `from sqlalchemy.orm import Session` is misleading since
# the actual db object passed is an AsyncSession from get_async_db.
# Update the import and type hints:

# Replace line 20:
from sqlalchemy.ext.asyncio import AsyncSession

# Update the __call__ method signature (line 70):
        db: AsyncSession = Depends(get_db)

# Update _get_user_permissions signature:
        db: AsyncSession,
```

Note: Also update `_is_super_admin` and `_validate_workspace_membership` type annotations if they use `Session`.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/utils/route_decorators.py` | 341 | Uses `rbac_utils.check_all_permissions` / `check_any_permission` — the decorator-based permission checking (already cached) |
| `src/api/routes/users/user_permissions.py` | 15 | Imports `get_user_permissions` from `rbac_utils` directly |
| `src/api/routes/workspaces/workspace_permissions.py` | 18, 294 | Imports and uses `rbac_utils` functions directly |
| `src/api/routes/health.py` | 20 | Uses `is_admin` from permissions middleware |
| `src/api/routes/users/impersonation.py` | 11 | Uses `is_admin` from permissions middleware |
| `src/api/routes/users/admin.py` | 6 | Uses `is_admin` from permissions middleware |
| `src/api/routes/security/security_routes.py` | 15 | Uses `is_admin` from permissions middleware |
| `src/api/routes/admin/customer_routes.py` | 19 | Uses `is_admin` from permissions middleware |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Add logging to both `PermissionChecker._get_user_permissions()` and `rbac_utils.get_user_permissions()` to track which path is taken
2. Make an admin API call (e.g., `GET /health` with admin credentials) — observe the DB query is made directly without checking Redis cache
3. Make the same call multiple times — each call hits the database

### After Fix (Verify the Solution):
1. Make an admin API call — verify the first call queries the DB and populates the Redis cache
2. Make the same call again within 5 minutes — verify the second call hits the Redis cache (no DB query)
3. Verify Redis cache key format: `user:permissions:{user_id}:{workspace_id or 'global'}`
4. Test workspace-scoped permission checks to ensure UUID conversion works correctly
5. Test the super_admin bypass still works (it checks permissions before `_get_user_permissions` is called)

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -v -k "permission or rbac" --no-header
```

---

## Acceptance Criteria

- [ ] `PermissionChecker._get_user_permissions()` delegates to `rbac_utils.get_user_permissions()`
- [ ] String user IDs and workspace IDs are correctly converted to `UUID` objects before passing to `rbac_utils`
- [ ] Redis caching is now active for all permission checks (both dependency and decorator paths)
- [ ] The `== None` SQL comparison issue is resolved (rbac_utils uses `.is_(None)`)
- [ ] Type annotation for `db` parameter updated from `Session` to `AsyncSession`
- [ ] All admin and permission-protected routes still function correctly
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [SQLAlchemy — Using IS NULL](https://docs.sqlalchemy.org/en/20/core/sqlelement.html#sqlalchemy.sql.expression.ColumnElement.is_) — documents the `.is_(None)` pattern for NULL comparisons
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [FastAPI Dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/) — dependency injection patterns for FastAPI
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-008 (commented-out workspace validation in route decorators), TASK-009 (test stub bypasses permission checks) — all three touch the permission-checking infrastructure
