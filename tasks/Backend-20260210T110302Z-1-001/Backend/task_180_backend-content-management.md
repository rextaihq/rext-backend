# Task 180: Eliminate Title Uniqueness Check Duplication Across Routes and Service

## Metadata
- **Task ID:** TASK-180
- **Source:** Backend Content Management Audit (Finding #16 under P2 Medium)
- **Audit Report:** `audit-reports/backend-content-management.md`
- **Priority:** P2 Medium
- **Category:** code-quality
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The title uniqueness check for content is duplicated 4 times across the routes and service layers. The same query pattern — `select(Content).where(Content.workspace_id == ..., Content.title == ..., Content.deleted_at == None)` — appears in:

1. **`publish_content.py:121-131`** — In `save_content()` route, checks title uniqueness before calling `ContentService.create_content()`.
2. **`publish_content.py:170-180`** — In `save_and_publish()` route, same check before calling `ContentService.create_content()`.
3. **`publish_content.py:321-333`** — In `update_content()` route, checks title uniqueness before calling `ContentService.update_content()`.
4. **`content_service.py:43-54`** — In `ContentService.create_content()`, the service method itself performs the same title uniqueness check.

This means that for the `save_content()` and `save_and_publish()` endpoints, the title uniqueness check is executed **twice** — once in the route and once in the service. This is both a DRY violation and a performance waste (two identical database queries per request). For `update_content()`, the route check is also redundant because `ContentService.update_content()` performs its own title uniqueness check at lines 119-133, including the proper `Content.id != content_id` exclusion.

The root cause is that the route layer does not trust the service layer to handle validation. In a well-structured application, business validation (like uniqueness constraints) belongs exclusively in the service layer. The route layer should only handle request parsing, authentication, and response formatting. Duplicating validation in routes creates maintenance risk — if the uniqueness logic changes (e.g., adding case-insensitive comparison), it must be updated in 4 places instead of 1.

Additionally, the route-level checks raise `HTTPException` directly (lines 128-131, 177-180, 330-333), while the service uses the project's custom `DuplicateResourceException` (line 50). This inconsistency means the error response format differs depending on which check triggers first. The service's approach using custom exceptions is correct, as these exceptions are caught by the `db_transaction_handler` decorator and converted to consistent API responses.

---

## Current Code

```python
# File: src/api/routes/content/modules/publish_content.py
# Lines: 121-131 (in save_content route)
    # Check if title already exists in workspace
    title_query = select(Content).where(
        Content.workspace_id == workspace.id,
        Content.title == data.title,
        Content.deleted_at == None
    )
    existing_result = await db.execute(title_query)
    if existing_result.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"Content with title '{data.title}' already exists in this workspace."
        )
```

```python
# File: src/api/routes/content/modules/publish_content.py
# Lines: 170-180 (in save_and_publish route — identical pattern)
    # Check if title already exists in workspace
    title_query = select(Content).where(
        Content.workspace_id == workspace.id,
        Content.title == data.title,
        Content.deleted_at == None
    )
    existing_result = await db.execute(title_query)
    if existing_result.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"Content with title '{data.title}' already exists in this workspace."
        )
```

```python
# File: src/api/routes/content/modules/publish_content.py
# Lines: 321-333 (in update_content route)
    # Check for duplicate title if title is being updated
    if data.title:
        title_query = select(Content).where(
            Content.workspace_id == workspace.id,
            Content.title == data.title,
            Content.deleted_at == None,
            Content.id != content_id
        )
        existing_result = await db.execute(title_query)
        if existing_result.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail=f"Content with title '{data.title}' already exists in this workspace."
            )
```

```python
# File: src/services/content_service.py
# Lines: 43-54 (in create_content — the authoritative check)
        # Check for duplicate title within the same workspace
        existing_query = select(Content).where(
            Content.workspace_id == workspace_id,
            Content.title == data.title,
            Content.deleted_at == None
        )
        existing_content = (await self.db.execute(existing_query)).scalar_one_or_none()
        if existing_content:
            raise DuplicateResourceException(
                resource_type="Content",
                conflicting_field="title",
                conflicting_value=data.title
            )
```

---

## Why This Matters (Context & Reasoning)

The Content Management module is the core of Rext AI's value proposition — users create and publish content. The `save_content`, `save_and_publish`, and `update_content` endpoints are high-traffic paths. Each redundant database query adds latency to these endpoints.

More importantly, the duplication creates a maintenance hazard. If a developer adds case-insensitive title matching, a `workspace.deleted_at` check, or changes the error message, they must remember to update all 4 locations. If even one is missed, the system exhibits inconsistent behavior. The fact that routes use `HTTPException` while the service uses `DuplicateResourceException` is already an example of this divergence.

The service layer's `DuplicateResourceException` is the correct approach because:
1. It integrates with the `db_transaction_handler` decorator's error handling
2. It uses structured error context (`resource_type`, `conflicting_field`, `conflicting_value`)
3. It can be caught and handled consistently across all entry points (API, Celery tasks, CLI)

---

## Impact

- **Severity:** Redundant database queries on every content creation/update request (2x queries instead of 1x). Inconsistent error responses depending on which check triggers. Maintenance risk from duplicated validation logic.
- **Affected Users/Flows:** All content creation (`/save`, `/publish`) and update (`PATCH /{content_id}`) flows.
- **Blast Radius:** Changes affect `publish_content.py` routes and rely on `content_service.py` handling validation correctly (which it already does).

---

## Recommended Solution

### Step 1: Remove the title uniqueness check from `save_content()` route

```python
# File: src/api/routes/content/modules/publish_content.py
# Remove lines 120-131 from save_content(). The function should go directly from
# workspace resolution to service call:

@router.post("/save", response_model=ContentResponse)
@db_transaction_handler("save content", "Content saved successfully")
@require_permissions("content.create", workspace_scoped=True)
async def save_content(
    data: ContentCreate,
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Save content as draft without publishing.

    Use this to save work in progress. To publish,
    use the /publish endpoint.
    """
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    # Force draft status
    data.status = "draft"

    service = ContentService(db)
    content = await service.create_content(
        workspace_id=workspace.id,
        user_id=UUID(user_id),
        data=data
    )

    return content.to_dict()
```

### Step 2: Remove the title uniqueness check from `save_and_publish()` route

```python
# File: src/api/routes/content/modules/publish_content.py
# Remove lines 169-180 from save_and_publish(). The function should go directly from
# workspace resolution to service call:

@router.post("/publish")
@db_transaction_handler("publish content", "Content published successfully")
@require_permissions("content.create", workspace_scoped=True)
async def save_and_publish(
    data: ContentCreate,
    request: Request,
    workspace_id: str,
    publish_status: str = "publish",
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Save content AND publish to all active WordPress sites.

    This is the primary endpoint for direct publishing.
    Content is saved to database and published to all active sites.
    """
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    # Save content first
    service = ContentService(db)
    content = await service.create_content(
        workspace_id=workspace.id,
        user_id=UUID(user_id),
        data=data
    )

    # Publish to all active sites
    results = await _publish_to_all_sites(
        db=db,
        workspace_id=workspace.id,
        content_data=data,
        status=publish_status
    )

    # Update content with first successful publish info
    successful_results = [r for r in results if r.success]
    if successful_results:
        first_success = successful_results[0]
        content.wordpress_post_id = first_success.wordpress_post_id
        content.wordpress_url = first_success.wordpress_url
        content.wordpress_published_at = datetime.now(timezone.utc)
        content.status = "published"

    return {
        "content": content.to_dict(),
        "publish_results": {
            "total_sites": len(results),
            "successful": len(successful_results),
            "failed": len(results) - len(successful_results),
            "results": [r.model_dump() for r in results]
        }
    }
```

### Step 3: Remove the title uniqueness check from `update_content()` route

```python
# File: src/api/routes/content/modules/publish_content.py
# Remove lines 320-333 from update_content(). The service already handles this:

@router.patch("/{content_id}", response_model=ContentResponse)
@db_transaction_handler("update content", "Content updated successfully")
@require_permissions("content.update", workspace_scoped=True)
async def update_content(
    content_id: UUID,
    data: ContentUpdate,
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Update existing content.

    Allows partial updates of content fields, SEO data, and media links.
    """
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    service = ContentService(db)
    content = await service.update_content(
        content_id=content_id,
        workspace_id=workspace.id,
        user_id=UUID(user_id),
        data=data
    )

    return content.to_dict(include_relationships=["seo_data"])
```

### Step 4: Remove unused imports from `publish_content.py`

After removing the route-level title checks, the `select` import from `sqlalchemy` and the `Content` model import may no longer be needed in the routes file (verify by checking other usages in the file first — `_publish_to_all_sites` still uses `select` and `WorkspaceIntegration`).

```python
# File: src/api/routes/content/modules/publish_content.py
# Check if these imports are still needed after removal:
# from sqlalchemy import select  -- still needed for _publish_to_all_sites
# from src.api.models.content_models import Content  -- check if used elsewhere in file
```

The `Content` import at line 23 is still used in `publish_existing_content()` (indirectly via the service), so it can remain. However, if the only direct usage of `Content` in the routes file was in the title uniqueness checks, it can be removed.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/services/content_service.py` | `43-54` | The authoritative title uniqueness check — this stays as-is |
| `src/services/content_service.py` | `119-133` | The title uniqueness check in `update_content` — this stays as-is |
| `src/api/middleware/exceptions.py` | Various | `DuplicateResourceException` class used by the service — verify error response format |
| `src/utils/route_decorators.py` | Various | `db_transaction_handler` must properly catch and format `DuplicateResourceException` |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Set a breakpoint or add logging in both `publish_content.py:121` and `content_service.py:43`.
2. Call `POST /api/v1/content/save` with a unique title.
3. Observe that the title uniqueness query executes twice — once in the route, once in the service.
4. Call with a duplicate title and observe the `HTTPException` from the route (not the `DuplicateResourceException` from the service).

### After Fix (Verify the Solution):
1. Call `POST /api/v1/content/save` with a unique title — should succeed as before.
2. Call `POST /api/v1/content/save` with a duplicate title — should return an error from `DuplicateResourceException` (handled by `db_transaction_handler`).
3. Call `POST /api/v1/content/publish` with a duplicate title — same error behavior.
4. Call `PATCH /api/v1/content/{id}` with a duplicate title — same error behavior.
5. Call `PATCH /api/v1/content/{id}` with the same title as the content being updated — should succeed (not a duplicate of itself).
6. Verify the error response format is consistent across all three endpoints.

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/unit/services/test_content_service.py -v
```

---

## Acceptance Criteria

- [ ] Title uniqueness check is removed from `save_content()` route
- [ ] Title uniqueness check is removed from `save_and_publish()` route
- [ ] Title uniqueness check is removed from `update_content()` route
- [ ] `ContentService.create_content()` still performs title uniqueness validation
- [ ] `ContentService.update_content()` still performs title uniqueness validation (excluding current content)
- [ ] `DuplicateResourceException` errors are properly formatted by `db_transaction_handler`
- [ ] Error responses for duplicate titles are consistent across all three endpoints
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [FastAPI Bigger Applications - Structure](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [Clean Architecture by Robert C. Martin](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html) — Business validation belongs in the service/use-case layer, not in controllers/routes
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None (but verify that `db_transaction_handler` properly handles `DuplicateResourceException` before removing route-level checks)
- **Blocks:** None
- **Related:** TASK-169 (WordPress publishing logic in routes instead of service — same architectural concern of business logic leaking into the route layer)
