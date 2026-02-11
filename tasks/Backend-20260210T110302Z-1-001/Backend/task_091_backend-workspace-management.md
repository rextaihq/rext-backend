# Task 091: Update Route Passes Wrong Keyword Arguments (Broken Endpoint)

## Metadata
- **Task ID:** TASK-091
- **Source:** B4 - Workspace Management (Finding #5 under P0 Critical)
- **Audit Report:** `audit-reports/backend-workspace-management.md`
- **Priority:** P0 Critical
- **Category:** bug
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `PUT /{workspace_id}` route in `src/api/routes/workspaces/workspace_core.py` (lines 240-246) passes keyword arguments `title=`, `slug=`, `description=`, and `url=` to `workspace_service.update_workspace()`. However, the actual service method signature at `src/services/workspace_service.py:815-820` accepts only `workspace_id`, `name=`, `tz=`, and `url=`. The mismatched keyword arguments `title`, `slug`, and `description` will cause a `TypeError: update_workspace() got an unexpected keyword argument 'title'` at runtime, making this endpoint **completely non-functional**.

The route handler also uses `await request.json()` (line 230) to read the request body instead of a Pydantic model parameter, bypassing all FastAPI input validation. This means there is no type checking, no field validation, and the endpoint does not appear correctly in the OpenAPI documentation. According to FastAPI best practices, request bodies should always be declared using Pydantic models that FastAPI validates automatically before the handler is called.

Additionally, the route docstring (lines 213-224) documents a request body with fields `title`, `slug`, `description`, and `url`, but the service only supports updating `name`, `timezone`, and `url`. The `slug` is auto-generated from the name by the service (line 842-845), and `description` is not a field on `WorkspaceModel` at all.

The intermediary method `update_workspace_for_user` at line 275-297 of the service correctly maps `name` and `timezone` parameters and handles name uniqueness checking, but the route handler does not call this method — it calls `update_workspace` directly.

---

## Current Code

```python
# File: src/api/routes/workspaces/workspace_core.py
# Lines: 226-254
    # Parse request body
    body = await request.json()  # <-- No Pydantic validation

    # Use workspace service
    workspace_service = WorkspaceService(db)

    # Get workspace first to verify access
    from src.utils.workspace_utils import resolve_and_verify_workspace
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    # Update workspace
    updated_workspace = await workspace_service.update_workspace(
        workspace.id,
        title=body.get("title"),           # <-- Wrong kwarg, service expects 'name'
        slug=body.get("slug"),             # <-- Wrong kwarg, not in service signature
        description=body.get("description"),# <-- Wrong kwarg, not in service signature
        url=body.get("url")
    )
```

```python
# File: src/services/workspace_service.py
# Lines: 815-860 (actual service method signature)
    async def update_workspace(
        self,
        workspace_id: UUID,
        name: Optional[str] = None,     # <-- Expects 'name', not 'title'
        tz: Optional[str] = None,       # <-- Expects 'tz', not 'slug' or 'description'
        url: Optional[str] = None,
    ) -> WorkspaceModel:
```

---

## Why This Matters (Context & Reasoning)

The `PUT /workspaces/{workspace_id}` endpoint is the primary RESTful endpoint for updating workspace metadata (name, timezone, URL). The frontend uses this endpoint to allow users to modify their workspace settings. With the current implementation, every attempt to update a workspace via this endpoint will crash with an HTTP 500 error (unhandled `TypeError`), providing a poor user experience and potentially exposing internal error details.

The route also bypasses the higher-level `update_workspace_for_user` method which includes important business logic: (1) verifying the user is active, (2) verifying workspace membership, and (3) checking for name uniqueness when the name changes. By calling `update_workspace` directly, these safeguards are skipped (the route does call `resolve_and_verify_workspace` separately, but misses the name uniqueness check).

---

## Impact

- **Severity:** The `PUT /workspaces/{workspace_id}` endpoint crashes with a `TypeError` on every request, making workspace updates completely non-functional via this RESTful endpoint.
- **Affected Users/Flows:** Any user attempting to update workspace name, timezone, or URL via the RESTful API. Frontend workspace settings page if it uses this endpoint.
- **Blast Radius:** Isolated to the single `PUT /{workspace_id}` endpoint, but critical for workspace management functionality.

---

## Recommended Solution

### Step 1: Create a Pydantic schema for workspace updates

```python
# File: src/api/schema/workspace_schema.py
# Add after existing schemas:
from pydantic import BaseModel, Field
from typing import Optional


class WorkspaceUpdateSchema(BaseModel):
    """Schema for updating workspace metadata."""
    name: Optional[str] = Field(None, min_length=1, max_length=255, description="New workspace name")
    timezone: Optional[str] = Field(None, max_length=50, description="IANA timezone identifier (e.g., America/New_York)")
    url: Optional[str] = Field(None, max_length=2048, description="Workspace website URL")
```

### Step 2: Rewrite the update route to use Pydantic validation and the correct service method

```python
# File: src/api/routes/workspaces/workspace_core.py
# Replace lines 200-254 with:

# -------------------------
# Update workspace
# -------------------------
@router.put("/{workspace_id}")
@require_permissions("workspace.update", workspace_scoped=True)
@db_transaction_handler("update workspace", auto_commit=True)
async def update_workspace(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Update workspace details (name, timezone, url).

    Args:
        workspace_id: Workspace UUID or slug

    Body:
        {
          "name": "New Workspace Name",
          "timezone": "America/New_York",
          "url": "https://example.com"
        }
    """
    from src.api.schema.workspace_schema import WorkspaceUpdateSchema

    user_id = user.get("identity")
    db_user = await verify_current_user(db, user_id)

    # Parse and validate request body using Pydantic
    body = await request.json()
    update_data = WorkspaceUpdateSchema(**body)

    # Use workspace service — call the user-facing method with correct parameter names
    workspace_service = WorkspaceService(db)

    # Get workspace first to verify access
    from src.utils.workspace_utils import resolve_and_verify_workspace
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    # Map frontend field names: frontend sends "title", backend uses "name"
    name = update_data.name or body.get("title")

    updated_workspace = await workspace_service.update_workspace_for_user(
        workspace_id=workspace.id,
        user_id=UUID(user_id),
        name=name,
        timezone=update_data.timezone,
        url=update_data.url,
    )

    logger.info(
        "Workspace updated",
        extra={"workspace_id": str(workspace.id), "user_id": user_id}
    )

    return {"workspace": updated_workspace}
```

### Step 3: Verify the `update_workspace_for_user` service method is correct

The existing method at `src/services/workspace_service.py:275-297` already handles the correct mapping:

```python
# File: src/services/workspace_service.py
# Lines: 275-297 (existing — no changes needed)
    async def update_workspace_for_user(
        self,
        workspace_id: UUID,
        user_id: UUID,
        name: Optional[str],
        timezone: Optional[str],
        url: Optional[str],
    ) -> Dict[str, Any]:
        """Update workspace metadata for a member."""
        await self._ensure_active_user(user_id)
        workspace = await self._ensure_membership(workspace_id, user_id)

        if name and name != workspace.name:
            await self._ensure_unique_workspace_name(name, user_id)

        updated = await self.update_workspace(
            workspace_id=workspace_id,
            name=name,
            tz=timezone,
            url=url,
        )
        await self.db.refresh(updated)
        return self._serialize_workspace(updated)
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/routes/workspaces/__init__.py` | N/A | RESTful wrapper may also have a PUT endpoint that delegates to `workspace_core.py` — verify it uses the same corrected route |
| `src/api/routes/workspaces/workspace_route.py` | N/A | Legacy routes may have a separate update endpoint — verify consistency |
| `src/api/schema/workspace_schema.py` | `29-41` | Existing `WorkspaceSchema` mixes workspace and brand voice fields — the new `WorkspaceUpdateSchema` should be separate |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Create a workspace via the API
2. Attempt to update it: `PUT /workspaces/{workspace_id}` with body `{"title": "New Name", "url": "https://new-url.com"}`
3. Observe HTTP 500 error with `TypeError: update_workspace() got an unexpected keyword argument 'title'`

### After Fix (Verify the Solution):
1. Update workspace name: `PUT /workspaces/{workspace_id}` with body `{"name": "New Name"}`
2. Verify response contains updated workspace with new name and auto-generated slug
3. Update timezone: `PUT /workspaces/{workspace_id}` with body `{"timezone": "America/New_York"}`
4. Verify response contains updated timezone
5. Update URL: `PUT /workspaces/{workspace_id}` with body `{"url": "https://new-site.com"}`
6. Verify response contains updated URL
7. Test with `title` field (frontend compatibility): `PUT /workspaces/{workspace_id}` with body `{"title": "New Name"}`
8. Verify name uniqueness check: attempt to set name to another user's existing workspace name

### Edge Cases:
- Empty body `{}` — should succeed with no changes
- Invalid timezone format — Pydantic validation should catch
- Name exceeding max_length — Pydantic validation should catch
- Duplicate workspace name — service should raise appropriate error

### Run Existing Tests:
```bash
cd rext-backend
pytest tests/ -v -k "workspace and update"
```

---

## Acceptance Criteria

- [ ] `PUT /workspaces/{workspace_id}` endpoint no longer crashes with `TypeError`
- [ ] Route uses `update_workspace_for_user` service method (includes name uniqueness check)
- [ ] Request body is validated through Pydantic `WorkspaceUpdateSchema`
- [ ] Correct parameter mapping: `name=` (not `title=`), `timezone=` (not `slug=`)
- [ ] Frontend compatibility maintained (`title` field accepted and mapped to `name`)
- [ ] `slug` is auto-generated from name by the service (not accepted as input)
- [ ] Response returns serialized workspace data
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [FastAPI — Request Body](https://fastapi.tiangolo.com/tutorial/body/)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [FastAPI — Body Updates (PATCH)](https://fastapi.tiangolo.com/tutorial/body-updates/) — covers partial update patterns
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-098 (B4 Finding 12: Update Route Bypasses Pydantic Validation — overlaps with this fix since both address the same route)
