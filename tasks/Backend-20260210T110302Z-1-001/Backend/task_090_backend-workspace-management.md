# Task 090: Missing Soft-Delete Filter in Workspace Resolvers

## Metadata
- **Task ID:** TASK-090
- **Source:** B4 - Workspace Management (Finding #2 under P0 Critical)
- **Audit Report:** `audit-reports/backend-workspace-management.md`
- **Priority:** P0 Critical
- **Category:** security
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `async_resolve_workspace()` function in `src/utils/workspace_utils.py` (lines 73-97) resolves a workspace by UUID or slug but does **not** filter out soft-deleted workspaces. It queries `WorkspaceModel` by `id` or `slug` without adding a `.where(WorkspaceModel.deleted_at.is_(None))` clause. This means any code path using this function can successfully resolve a workspace that has been soft-deleted (i.e., has a non-null `deleted_at` timestamp).

The `WorkspaceModel` in `src/api/models/workspace_models/workspace_model.py` clearly has a `deleted_at` column (line 23: `deleted_at = Column(DateTime(timezone=True), nullable=True)`) and a `deleted_by` column (line 24), confirming that soft-delete is an intentional pattern. However, the comment on line 84 of `workspace_utils.py` incorrectly states: `"Note: WorkspaceModel doesn't have soft delete (deleted_at), so all workspaces are returned."` This comment is factually wrong and may have prevented developers from adding the necessary filter.

The `async_resolve_workspace` function is called by `async_get_workspace_id_from_identifier` (line 111) which is in turn called by `resolve_and_verify_workspace` (line 195) — the primary workspace resolution function used across the entire codebase. A grep of the codebase shows `resolve_and_verify_workspace` is called from **28+ route handlers** across workspace core, members, invitations, personas, brand voice, knowledge bases, sites, and content modules. Every single one of these endpoints can currently access soft-deleted workspaces.

The sync version `resolve_workspace()` (lines 35-55) has the same issue but is likely unused (async equivalents exist). The `verify_workspace_membership` function (lines 115-160) also lacks a `deleted_at` filter on the `WorkspaceModel` join.

---

## Current Code

```python
# File: src/utils/workspace_utils.py
# Lines: 73-97
async def async_resolve_workspace(db: AsyncSession, identifier: str) -> Optional[WorkspaceModel]:
    """
    Async version: Resolve a workspace by either UUID or slug

    Args:
        db: Async database session
        identifier: Either a workspace UUID or slug

    Returns:
        WorkspaceModel if found, None otherwise

    Note: WorkspaceModel doesn't have soft delete (deleted_at), so all workspaces are returned.
    """
    if is_valid_uuid(identifier):
        # It's a UUID, query by ID
        result = await db.execute(
            select(WorkspaceModel).where(WorkspaceModel.id == UUID(identifier))
        )
        return result.scalar_one_or_none()
    else:
        # It's a slug, query by slug
        result = await db.execute(
            select(WorkspaceModel).where(WorkspaceModel.slug == identifier)
        )
        return result.scalar_one_or_none()
```

```python
# File: src/utils/workspace_utils.py
# Lines: 115-160 (verify_workspace_membership — also missing deleted_at filter)
async def verify_workspace_membership(
    db: AsyncSession,
    workspace_id: UUID,
    user_id: UUID,
    check_active: bool = True
) -> tuple:
    workspace_query = (
        select(WorkspaceModel, WorkspaceMembers)
        .join(WorkspaceMembers, WorkspaceMembers.workspace_id == WorkspaceModel.id)
        .where(
            WorkspaceModel.id == workspace_id,
            WorkspaceMembers.user_id == user_id
            # Missing: WorkspaceModel.deleted_at.is_(None)
        )
    )
```

---

## Why This Matters (Context & Reasoning)

Workspace soft-deletion is designed to provide a 30-day recovery period before permanent deletion (see `workspace_service.py:862-893`). During this period, the workspace data remains in the database with a `deleted_at` timestamp set. Users should not be able to access, modify, or interact with soft-deleted workspaces — the intent is that the workspace appears "gone" to all users until either recovered by an admin or permanently deleted after 30 days.

Because the workspace resolver does not check `deleted_at`, all 28+ endpoints that use `resolve_and_verify_workspace` will happily return data from deleted workspaces. This means:
- Users can continue to view, edit, and interact with "deleted" workspaces
- Content can be created, personas can be managed, and members can be added to deleted workspaces
- The entire soft-delete mechanism is undermined
- Authorization checks that depend on workspace resolution pass for deleted workspaces

---

## Impact

- **Severity:** Users can access and modify soft-deleted workspaces, completely bypassing the deletion workflow. Data that was intended to be inaccessible remains available through all workspace-scoped endpoints.
- **Affected Users/Flows:** Every workspace-scoped API endpoint (28+ handlers) across workspace CRUD, members, invitations, personas, brand voice, knowledge, sites, and content.
- **Blast Radius:** System-wide — every endpoint using `resolve_and_verify_workspace` is affected.

---

## Recommended Solution

### Step 1: Fix `async_resolve_workspace` to filter soft-deleted workspaces

```python
# File: src/utils/workspace_utils.py
# Replace lines 73-97 with:
async def async_resolve_workspace(db: AsyncSession, identifier: str) -> Optional[WorkspaceModel]:
    """
    Async version: Resolve a workspace by either UUID or slug.
    Excludes soft-deleted workspaces (where deleted_at is not NULL).

    Args:
        db: Async database session
        identifier: Either a workspace UUID or slug

    Returns:
        WorkspaceModel if found and not deleted, None otherwise
    """
    if is_valid_uuid(identifier):
        result = await db.execute(
            select(WorkspaceModel).where(
                WorkspaceModel.id == UUID(identifier),
                WorkspaceModel.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()
    else:
        result = await db.execute(
            select(WorkspaceModel).where(
                WorkspaceModel.slug == identifier,
                WorkspaceModel.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()
```

### Step 2: Fix `verify_workspace_membership` to filter soft-deleted workspaces

```python
# File: src/utils/workspace_utils.py
# Replace lines 138-145 in verify_workspace_membership with:
    workspace_query = (
        select(WorkspaceModel, WorkspaceMembers)
        .join(WorkspaceMembers, WorkspaceMembers.workspace_id == WorkspaceModel.id)
        .where(
            WorkspaceModel.id == workspace_id,
            WorkspaceModel.deleted_at.is_(None),
            WorkspaceMembers.user_id == user_id,
        )
    )
```

### Step 3: Fix the sync `resolve_workspace` function (or remove it)

Since the async equivalents exist, verify that the sync functions are unused and remove them. If they are still used somewhere:

```python
# File: src/utils/workspace_utils.py
# Replace lines 35-55 with:
def resolve_workspace(db: Session, identifier: str) -> Optional[WorkspaceModel]:
    """
    Resolve a workspace by either UUID or slug.
    Excludes soft-deleted workspaces.
    """
    if is_valid_uuid(identifier):
        return db.query(WorkspaceModel).filter(
            WorkspaceModel.id == UUID(identifier),
            WorkspaceModel.deleted_at.is_(None),
        ).first()
    else:
        return db.query(WorkspaceModel).filter(
            WorkspaceModel.slug == identifier,
            WorkspaceModel.deleted_at.is_(None),
        ).first()
```

### Step 4: Remove the incorrect comment

Delete the comment on line 84: `Note: WorkspaceModel doesn't have soft delete (deleted_at), so all workspaces are returned.`

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/utils/route_decorators.py` | `95-97` | `require_permissions` decorator calls `resolve_and_verify_workspace` — now correctly filters deleted workspaces |
| `src/api/routes/workspaces/workspace_core.py` | `237` | Update route uses `resolve_and_verify_workspace` |
| `src/api/routes/workspaces/workspace_members.py` | `162, 196, 245, 348` | 4 member management endpoints |
| `src/api/routes/workspaces/workspace_invitations.py` | `127, 183, 328, 483, 602` | 5 invitation endpoints |
| `src/api/routes/workspaces/workspace_personas.py` | `39, 70, 105, 149, 196` | 5 persona endpoints |
| `src/api/routes/workspaces/workspace_brand_voice.py` | `50` | Brand voice endpoint |
| `src/api/routes/content/modules/sites.py` | `35, 59, 107, 134, 168, 195, 221, 249` | 8 site management endpoints |
| `src/api/routes/content/modules/publish_content.py` | `118, 167, 238, 318, 365` | 5 content publishing endpoints |
| `src/api/routes/content/modules/content_retrieval.py` | `46, 86` | 2 content retrieval endpoints |
| `src/api/routes/workspaces/workspace_knowledge.py` | `111` | Knowledge base endpoint |
| `src/api/routes/workspaces/workspace_knowledge_bases.py` | `49` | Knowledge bases endpoint |
| `src/services/workspace_permission_service.py` | `41-44` | Permission service workspace check — also missing `deleted_at` filter (see B4 Finding 22) |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Create a workspace via the API
2. Note the workspace ID and slug
3. Delete the workspace via `DELETE /workspaces/{id}` (soft-delete)
4. Verify `deleted_at` is set in the database: `SELECT id, deleted_at FROM workspace WHERE id = '<id>'`
5. Call `GET /workspaces/{id}` or `GET /workspaces/slug/{slug}` — workspace data is returned despite being deleted

### After Fix (Verify the Solution):
1. Create a workspace and note its ID/slug
2. Delete the workspace via `DELETE /workspaces/{id}`
3. Call `GET /workspaces/{id}` — should return 404 "Workspace not found"
4. Call `GET /workspaces/slug/{slug}` — should return 404 "Workspace not found"
5. Verify all member, invitation, persona, and content endpoints also return 404 for the deleted workspace
6. Verify non-deleted workspaces still resolve correctly

### Run Existing Tests:
```bash
cd rext-backend
pytest tests/ -v -k "workspace"
```

---

## Acceptance Criteria

- [ ] `async_resolve_workspace` filters by `WorkspaceModel.deleted_at.is_(None)`
- [ ] `verify_workspace_membership` filters by `WorkspaceModel.deleted_at.is_(None)`
- [ ] Sync `resolve_workspace` either filters by `deleted_at` or is removed if unused
- [ ] The incorrect comment on line 84 is removed
- [ ] Soft-deleted workspaces return 404 from all workspace-scoped endpoints
- [ ] Non-deleted workspaces continue to resolve correctly
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [SQLAlchemy 2.0 — Using SELECT Statements](https://docs.sqlalchemy.org/en/20/tutorial/data_select.html#the-where-clause)
- **Security Advisory:** N/A (authorization bypass via missing filter)
- **Migration Guide:** N/A
- **Best Practice Reference:** [SQLAlchemy 2.0 — ORM Querying Guide](https://docs.sqlalchemy.org/en/20/orm/queryguide/select.html)
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-092 (B4 Finding 22: Missing `deleted_at` Filter in Permission Service — same pattern in `workspace_permission_service.py`)
