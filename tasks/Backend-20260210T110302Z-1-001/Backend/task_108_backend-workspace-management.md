# Task 108: Remove Orphaned Synchronous Workspace Utility Functions

## Metadata
- **Task ID:** TASK-108
- **Source:** Backend Workspace Management Audit (Finding #18 under P2 Medium)
- **Audit Report:** `audit-reports/backend-workspace-management.md`
- **Priority:** P2 Medium
- **Category:** code-quality
- **Effort Estimate:** small (< 1 hour)

---

## Description

The file `src/utils/workspace_utils.py` contains two synchronous functions — `resolve_workspace()` (lines 35-55) and `get_workspace_id_from_identifier()` (lines 58-70) — that use the legacy synchronous SQLAlchemy `db.query()` API with a synchronous `Session` object. These functions have fully equivalent async counterparts defined in the same file: `async_resolve_workspace()` (lines 73-97) and `async_get_workspace_id_from_identifier()` (lines 100-112).

A codebase-wide search for `resolve_workspace(` (excluding the async variant) and `get_workspace_id_from_identifier(` (excluding the async variant) confirms that neither sync function is called from anywhere outside the file itself. The only references are:
- The function definitions themselves (lines 35 and 58)
- `get_workspace_id_from_identifier()` calls `resolve_workspace()` internally (line 69)

Meanwhile, the async variants are used extensively:
- `async_get_workspace_id_from_identifier()` is called in `route_decorators.py:371`, `workspace_permissions.py:86,174,291`, `user_permissions.py:90`, and `workspace_utils.py:195`
- `async_resolve_workspace()` is called in `workspace_utils.py:111`

The sync functions use `db.query(WorkspaceModel).filter(...)` which is the SQLAlchemy 1.x "legacy" query API. This project uses SQLAlchemy 2.0+ with the modern `select()` API throughout. The sync functions also accept `Session` (synchronous) from `sqlalchemy.orm` while the entire application uses `AsyncSession` from `sqlalchemy.ext.asyncio`. If a sync function were ever accidentally called from an async route handler, it would block the event loop and could cause request timeouts under load.

Additionally, neither sync function filters by `deleted_at.is_(None)`, meaning they would return soft-deleted workspaces — the same bug identified in Finding #2 (TASK-090) for the async variant. Since these functions are dead code, the fix is to remove them entirely rather than fix the missing filter.

The `Session` import from `sqlalchemy.orm` on line 6 is only used by these sync functions and can also be removed.

---

## Current Code

```python
# File: src/utils/workspace_utils.py
# Lines: 6 (import used only by sync functions)
from sqlalchemy.orm import Session

# Lines: 35-55 (sync resolve_workspace)
def resolve_workspace(db: Session, identifier: str) -> Optional[WorkspaceModel]:
    """
    Resolve a workspace by either UUID or slug

    Args:
        db: Database session
        identifier: Either a workspace UUID or slug

    Returns:
        WorkspaceModel if found, None otherwise
    """
    if is_valid_uuid(identifier):
        # It's a UUID, query by ID
        return db.query(WorkspaceModel).filter(
            WorkspaceModel.id == UUID(identifier)
        ).first()
    else:
        # It's a slug, query by slug
        return db.query(WorkspaceModel).filter(
            WorkspaceModel.slug == identifier
        ).first()


# Lines: 58-70 (sync get_workspace_id_from_identifier)
def get_workspace_id_from_identifier(db: Session, identifier: str) -> Optional[UUID]:
    """
    Get workspace UUID from either a UUID string or slug

    Args:
        db: Database session
        identifier: Either a workspace UUID or slug

    Returns:
        UUID of the workspace if found, None otherwise
    """
    workspace = resolve_workspace(db, identifier)
    return workspace.id if workspace else None
```

---

## Why This Matters (Context & Reasoning)

Dead code creates confusion for developers who may assume these functions are part of the active API surface. A developer working on workspace features might use the sync variants instead of the async ones, introducing an event-loop-blocking bug that only manifests under load.

The sync functions also use the legacy `db.query()` API (SQLAlchemy 1.x style), which is inconsistent with the modern `select()` API used everywhere else. Removing them improves code consistency and reduces the maintenance surface.

Additionally, the unused `from sqlalchemy.orm import Session` import signals that synchronous database access is part of the workspace utilities contract, which is misleading — the workspace system is fully async.

---

## Impact

- **Severity:** Low immediate impact (dead code), but creates risk of accidental misuse that would block the async event loop. Also creates developer confusion about whether sync database access is supported.
- **Affected Users/Flows:** None directly — these functions are not called. Removal prevents future misuse.
- **Blast Radius:** Isolated to `src/utils/workspace_utils.py`. No callers will be affected.

---

## Recommended Solution

### Step 1: Remove the synchronous `Session` import

```python
# File: src/utils/workspace_utils.py
# Remove line 6:
#   from sqlalchemy.orm import Session
```

### Step 2: Remove `resolve_workspace()` function

```python
# File: src/utils/workspace_utils.py
# Delete lines 35-55 (the entire resolve_workspace function)
```

### Step 3: Remove `get_workspace_id_from_identifier()` function

```python
# File: src/utils/workspace_utils.py
# Delete lines 58-70 (the entire get_workspace_id_from_identifier function)
```

The resulting file should start with:

```python
# File: src/utils/workspace_utils.py (after cleanup)
"""
Workspace utility functions for handling workspace resolution
"""
from uuid import UUID
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.middleware.exceptions import ResourceNotFoundException


def is_valid_uuid(value) -> bool:
    """
    Check if a value is a valid UUID or UUID object

    Args:
        value: String or UUID object to check

    Returns:
        True if valid UUID, False otherwise
    """
    # Already a UUID object
    if isinstance(value, UUID):
        return True

    # Try to parse as UUID string
    try:
        UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


async def async_resolve_workspace(db: AsyncSession, identifier: str) -> Optional[WorkspaceModel]:
    # ... rest of the file remains unchanged
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| None | N/A | No files call the sync functions. Verified via codebase-wide search for `resolve_workspace(` and `get_workspace_id_from_identifier(` — only the async variants are used. |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Open `src/utils/workspace_utils.py`
2. Confirm `resolve_workspace()` and `get_workspace_id_from_identifier()` exist at lines 35-70
3. Run a codebase-wide search for callers: `grep -rn "resolve_workspace\b" src/ --include="*.py" | grep -v "async_resolve_workspace" | grep -v "def resolve_workspace" | grep -v "_resolve_workspace"`
4. Confirm zero callers outside the file itself

### After Fix (Verify the Solution):
1. Verify `resolve_workspace()` and `get_workspace_id_from_identifier()` no longer exist in the file
2. Verify `from sqlalchemy.orm import Session` import is removed
3. Verify all async functions (`async_resolve_workspace`, `async_get_workspace_id_from_identifier`, `verify_workspace_membership`, `resolve_and_verify_workspace`) still exist and work correctly
4. Run the full test suite to confirm no breakage

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "workspace" -v
```

---

## Acceptance Criteria

- [ ] `resolve_workspace()` function is removed from `workspace_utils.py`
- [ ] `get_workspace_id_from_identifier()` function is removed from `workspace_utils.py`
- [ ] `from sqlalchemy.orm import Session` import is removed
- [ ] All async utility functions remain intact and functional
- [ ] No callers are broken (verified by codebase search showing zero callers)
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [SQLAlchemy 2.0 Migration — Legacy vs Modern Query API](https://docs.sqlalchemy.org/en/20/changelog/migration_20.html#migration-orm-usage) — documents the deprecation of `Session.query()` in favor of `select()`
- **Security Advisory:** N/A
- **Migration Guide:** [SQLAlchemy 2.0 ORM Query Migration](https://docs.sqlalchemy.org/en/20/changelog/migration_20.html#migration-20-query-usage) — official migration guide for moving from `db.query()` to `select()`
- **Best Practice Reference:** N/A
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-090 (B4: Missing Soft-Delete Filter in Workspace Resolvers — the async variants in the same file have this bug, which was already extracted as a separate task), TASK-057 (B2: Legacy db.query() API in Sync Utilities — same pattern of sync SQLAlchemy usage being removed)
