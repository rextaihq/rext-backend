# Task 097: Fix Update Route Bypassing Pydantic Validation — Replace `request.json()` with Typed Schema

## Metadata
- **Task ID:** TASK-097
- **Source:** Backend Workspace Management (Finding #12 under P1 High)
- **Audit Report:** `audit-reports/backend-workspace-management.md`
- **Priority:** P1 High
- **Category:** security
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `PUT /{workspace_id}` endpoint in `src/api/routes/workspaces/workspace_core.py` (line 230) reads the request body using `body = await request.json()` instead of declaring a Pydantic model as a function parameter. This bypasses all FastAPI input validation — no type checking, no field validation, no maximum length enforcement, and no automatic OpenAPI documentation generation.

FastAPI's core value proposition is that request body parameters declared as Pydantic models are automatically validated before the route handler executes. When `request.json()` is used instead, the raw JSON is parsed into an untyped `dict`, and any arbitrary keys/values can reach the service layer. This opens the door to:

1. **Type confusion:** Non-string values for `title`, `slug`, or `description` fields won't be rejected.
2. **Injection of unexpected fields:** Arbitrary keys in the JSON body are silently accepted and passed to `body.get()`.
3. **Missing OpenAPI documentation:** The endpoint's request body is undocumented in the auto-generated API docs, making it harder for frontend developers to use correctly.
4. **No field-level error messages:** Pydantic provides structured validation errors (field name + error message), while `request.json()` provides none.

This is compounded by TASK-091 (the same endpoint passes wrong keyword arguments to the service), but even after TASK-091 is fixed, the lack of input validation remains a separate issue.

A `WorkspaceSchema` already exists in `src/api/schema/workspace_schema.py` with `name`, `timezone`, and `url` fields, but it also contains brand voice fields (`about`, `customer_profile`, etc.) that are irrelevant for workspace updates. A dedicated `WorkspaceUpdateSchema` should be created for this endpoint.

Note: This same anti-pattern (`await request.json()`) exists in 6 other routes across the codebase (see Other Affected Locations), but this task addresses only the workspace update endpoint.

---

## Current Code

```python
# File: src/api/routes/workspaces/workspace_core.py
# Lines: 199-254
@router.put("/{workspace_id}")
@require_permissions("workspace.update", workspace_scoped=True)
@db_transaction_handler("update workspace", auto_commit=True)
async def update_workspace_endpoint(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Update workspace details.
    ...
    """
    user_id = user.get("identity")
    db_user = await verify_current_user(db, user_id)

    # Parse request body
    body = await request.json()

    # Use workspace service
    workspace_service = WorkspaceService(db)

    # Get workspace first to verify access
    from src.utils.workspace_utils import resolve_and_verify_workspace
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    # Update workspace
    updated_workspace = await workspace_service.update_workspace(
        workspace.id,
        title=body.get("title"),
        slug=body.get("slug"),
        description=body.get("description"),
        url=body.get("url")
    )

    logger.info(
        f"Workspace updated: {workspace.id}",
        extra={"workspace_id": str(workspace.id), "user_id": user_id}
    )

    # Return raw data - decorator handles success response
    return {"workspace": updated_workspace}
```

---

## Why This Matters (Context & Reasoning)

The workspace update endpoint allows users to change their workspace name, timezone, and URL. These are user-facing settings that affect workspace identity and navigation (slugs are used in URLs). Without input validation:

- A user could submit a workspace name with 10,000 characters, potentially causing UI issues or database errors.
- A user could submit an invalid URL format, which would be stored and later cause errors when the system tries to use it.
- A user could submit an invalid timezone string, which would be stored and cause errors in any timezone-dependent logic.

FastAPI's official documentation explicitly recommends using Pydantic models for request body validation. The `request.json()` pattern is an escape hatch for edge cases where the body structure is truly dynamic — it should not be used for structured CRUD endpoints with known fields.

---

## Impact

- **Severity:** No input validation on workspace update fields. Arbitrary JSON data reaches the service layer. Missing OpenAPI documentation for the request body.
- **Affected Users/Flows:** Any user updating workspace settings (name, timezone, URL) through the workspace settings page.
- **Blast Radius:** Isolated to the `PUT /workspaces/{workspace_id}` endpoint, but the stored invalid data could affect downstream consumers of workspace data.

---

## Recommended Solution

### Step 1: Create a dedicated `WorkspaceUpdateSchema` in the workspace schema file

```python
# File: src/api/schema/workspace_schema.py
# Add after the existing WorkspaceSchema class (after line 42):

class WorkspaceUpdateSchema(BaseModel):
    """Request body for updating workspace details."""
    name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
        description="New workspace name",
    )
    timezone: Optional[str] = Field(
        None,
        max_length=50,
        description="IANA timezone identifier (e.g., 'America/New_York', 'UTC')",
    )
    url: Optional[HttpUrl] = Field(
        None,
        description="Workspace website URL",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "My Workspace",
                "timezone": "America/New_York",
                "url": "https://example.com",
            }
        }
    }
```

### Step 2: Update the route handler to use the Pydantic schema

```python
# File: src/api/routes/workspaces/workspace_core.py
# Add import at the top of the file (around line 13):
from src.api.schema.workspace_schema import WorkspaceUpdateSchema

# Replace lines 199-254 with:
@router.put("/{workspace_id}")
@require_permissions("workspace.update", workspace_scoped=True)
@db_transaction_handler("update workspace", auto_commit=True)
async def update_workspace_endpoint(
    workspace_id: str,
    body: WorkspaceUpdateSchema,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """
    Update workspace details.

    Accepts optional fields: name, timezone, url.
    Only provided fields will be updated.

    Args:
        workspace_id: Workspace UUID or slug
        body: WorkspaceUpdateSchema with optional update fields
    """
    user_id = user.get("identity")
    db_user = await verify_current_user(db, user_id)

    # Use workspace service
    workspace_service = WorkspaceService(db)

    # Get workspace first to verify access
    from src.utils.workspace_utils import resolve_and_verify_workspace
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    # Update workspace — pass only the fields that match the service method signature
    updated_workspace = await workspace_service.update_workspace(
        workspace.id,
        name=body.name,
        tz=body.timezone,
        url=str(body.url) if body.url else None,
    )

    logger.info(
        "Workspace updated",
        extra={"workspace_id": str(workspace.id), "user_id": user_id},
    )

    # Return raw data - decorator handles success response
    return {"workspace": updated_workspace}
```

Note: This fix also addresses the wrong keyword arguments issue from TASK-091 (Finding #5). The `title=`, `slug=`, `description=` kwargs are replaced with the correct `name=`, `tz=`, `url=` kwargs that match the `update_workspace()` method signature.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/routes/users/password.py` | `309` | `await request.json()` used instead of Pydantic schema — same anti-pattern |
| `src/api/routes/users/auth.py` | `585, 733, 812, 951` | `await request.json()` used in 4 auth routes — same anti-pattern |
| `src/api/routes/users/invitations.py` | `288` | `await request.json()` used — same anti-pattern |
| `src/api/schema/workspace_schema.py` | `29-41` | Existing `WorkspaceSchema` mixes workspace and brand voice fields (see Finding #31 / P3) |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Send a `PUT /workspaces/{workspace_id}` request with an invalid body:
   ```json
   {"title": 12345, "slug": null, "random_field": "injected", "description": true}
   ```
2. Observe that the request is accepted (no 422 validation error) and reaches the service layer.
3. Check the OpenAPI docs at `/docs` — the PUT endpoint shows no request body schema.

### After Fix (Verify the Solution):
1. Send the same invalid request as above.
2. Observe a `422 Unprocessable Entity` response with Pydantic validation error details.
3. Send a valid request:
   ```json
   {"name": "Updated Workspace", "timezone": "UTC", "url": "https://example.com"}
   ```
4. Observe a `200 OK` response with the updated workspace data.
5. Send a request with only some fields:
   ```json
   {"name": "New Name"}
   ```
6. Observe that only the name is updated, timezone and URL remain unchanged.
7. Check `/docs` — the PUT endpoint now shows the `WorkspaceUpdateSchema` as the request body with field descriptions.

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/unit/routes/ -k "workspace" -v
```

---

## Acceptance Criteria

- [ ] `PUT /workspaces/{workspace_id}` uses a Pydantic `WorkspaceUpdateSchema` parameter instead of `request.json()`
- [ ] Invalid input types are rejected with 422 validation errors
- [ ] The correct kwargs (`name=`, `tz=`, `url=`) are passed to `update_workspace()` (also fixes TASK-091)
- [ ] OpenAPI docs show the request body schema for this endpoint
- [ ] Partial updates work (only provided fields are updated)
- [ ] `HttpUrl` validation rejects malformed URLs
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [FastAPI — Request Body](https://fastapi.tiangolo.com/tutorial/body/) — official tutorial showing how to declare Pydantic models as request body parameters
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [FastAPI — Body - Updates — Partial Updates with PATCH](https://fastapi.tiangolo.com/tutorial/body-updates/#partial-updates-with-patch) — official guide on handling optional fields for update endpoints using `exclude_unset`
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-091 (Update Route Passes Wrong Keyword Arguments) — this fix also resolves the wrong kwargs issue since the Pydantic schema maps fields to the correct service method parameters
