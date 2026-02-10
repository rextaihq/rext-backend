# Task 181: Extract Duplicated Site Fetch Pattern into Reusable Helper Function

## Metadata
- **Task ID:** TASK-181
- **Source:** Backend Content Management Audit (Finding #17 under P2 Medium)
- **Audit Report:** `audit-reports/backend-content-management.md`
- **Priority:** P2 Medium
- **Category:** code-quality
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The `sites.py` routes file at `src/api/routes/content/modules/sites.py` contains a site-fetching-and-validation pattern that is repeated 6 times across different endpoint handlers. Each occurrence performs the same sequence: construct a `select(WorkspaceIntegration).where(...)` query filtered by `site_id` and `workspace_id`, execute it, extract the scalar result, and raise `RextValidationException` if not found.

The 6 identical occurrences are in:
1. **`get_site_details()`** — lines 109-117
2. **`update_site()`** — lines 136-144
3. **`delete_site()`** — lines 170-178
4. **`activate_site()`** — lines 197-205
5. **`deactivate_site()`** — lines 223-231
6. **`publish_to_site()`** — lines 252-260

Each occurrence is 8-9 lines of identical boilerplate code: the same query construction, execution, null check, and exception raising. This amounts to approximately 50 lines of duplicated code that could be replaced by a single 10-line helper function called from each endpoint.

This is a textbook DRY (Don't Repeat Yourself) violation. The duplicated code creates maintenance risk: if the query needs to change (e.g., adding a `deleted_at` filter, changing the exception type from `RextValidationException` to `ResourceNotFoundException`, or adding eager loading), the change must be applied in 6 places. Missing even one creates inconsistent behavior.

Notably, the audit report also identified (in the "Consistent Error Handling" section) that these endpoints use `RextValidationException` for "not found" errors instead of the more semantically correct `ResourceNotFoundException`. This is an additional issue that becomes trivially fixable once the logic is centralized in a helper function.

---

## Current Code

```python
# File: src/api/routes/content/modules/sites.py
# Lines: 109-117 (in get_site_details)
    query = select(WorkspaceIntegration).where(
        WorkspaceIntegration.id == site_id,
        WorkspaceIntegration.workspace_id == workspace.id
    )
    result = await db.execute(query)
    site = result.scalar_one_or_none()

    if not site:
        raise RextValidationException(message="Site not found", context={"site_id": str(site_id)})
```

```python
# File: src/api/routes/content/modules/sites.py
# Lines: 136-144 (in update_site — identical)
    query = select(WorkspaceIntegration).where(
        WorkspaceIntegration.id == site_id,
        WorkspaceIntegration.workspace_id == workspace.id
    )
    result = await db.execute(query)
    site = result.scalar_one_or_none()

    if not site:
        raise RextValidationException(message="Site not found", context={"site_id": str(site_id)})
```

```python
# File: src/api/routes/content/modules/sites.py
# Lines: 170-178 (in delete_site — identical)
    query = select(WorkspaceIntegration).where(
        WorkspaceIntegration.id == site_id,
        WorkspaceIntegration.workspace_id == workspace.id
    )
    result = await db.execute(query)
    site = result.scalar_one_or_none()

    if not site:
        raise RextValidationException(message="Site not found", context={"site_id": str(site_id)})
```

```python
# File: src/api/routes/content/modules/sites.py
# Lines: 197-205 (in activate_site — identical)
    query = select(WorkspaceIntegration).where(
        WorkspaceIntegration.id == site_id,
        WorkspaceIntegration.workspace_id == workspace.id
    )
    result = await db.execute(query)
    site = result.scalar_one_or_none()

    if not site:
        raise RextValidationException(message="Site not found", context={"site_id": str(site_id)})
```

```python
# File: src/api/routes/content/modules/sites.py
# Lines: 223-231 (in deactivate_site — identical)
    query = select(WorkspaceIntegration).where(
        WorkspaceIntegration.id == site_id,
        WorkspaceIntegration.workspace_id == workspace.id
    )
    result = await db.execute(query)
    site = result.scalar_one_or_none()

    if not site:
        raise RextValidationException(message="Site not found", context={"site_id": str(site_id)})
```

```python
# File: src/api/routes/content/modules/sites.py
# Lines: 252-260 (in publish_to_site — identical)
    site_query = select(WorkspaceIntegration).where(
        WorkspaceIntegration.id == site_id,
        WorkspaceIntegration.workspace_id == workspace.id
    )
    site_result = await db.execute(site_query)
    site = site_result.scalar_one_or_none()

    if not site:
        raise RextValidationException(message="Site not found", context={"site_id": str(site_id)})
```

---

## Why This Matters (Context & Reasoning)

The `sites.py` file manages WordPress site connections — listing, connecting, updating, deleting, activating, deactivating, and publishing to connected sites. Every endpoint that operates on a specific site (all except `list_connected_sites` and `connect_site`) needs to fetch the site by ID and verify it belongs to the current workspace. This is a cross-cutting concern that should be abstracted.

The duplication is particularly problematic because:
1. **Error handling inconsistency risk:** If one occurrence is updated to use `ResourceNotFoundException` (the project's intended "not found" exception), the other 5 might be missed.
2. **Security filter risk:** If a `deleted_at` filter needs to be added (for soft-delete support on integrations), missing one occurrence could leak deleted sites.
3. **Code readability:** Each endpoint has 9 lines of boilerplate before its actual business logic, making the file unnecessarily long (304 lines → could be ~260 lines).

This is the same pattern that `ContentService._get_content_or_404()` (line 224) already implements for content — a dedicated helper that fetches-or-raises. The sites module should follow the same pattern.

---

## Impact

- **Severity:** No runtime bugs currently, but 50 lines of duplicated code increase maintenance cost and risk of inconsistent changes.
- **Affected Users/Flows:** All site management endpoints (get, update, delete, activate, deactivate, publish).
- **Blast Radius:** Contained within `sites.py`. The helper function is internal to this module.

---

## Recommended Solution

### Step 1: Add the helper function at the top of `sites.py`

Add the helper function after the imports and before the first route definition. Use `ResourceNotFoundException` instead of `RextValidationException` for semantic correctness (this is a "not found" error, not a validation error).

```python
# File: src/api/routes/content/modules/sites.py
# Add after line 23 (after router = APIRouter()):

from src.api.middleware.exceptions import ResourceNotFoundException


async def _get_site_or_404(
    db: AsyncSession, site_id: UUID, workspace_id: UUID
) -> WorkspaceIntegration:
    """Fetch a WorkspaceIntegration by ID within a workspace, or raise 404."""
    query = select(WorkspaceIntegration).where(
        WorkspaceIntegration.id == site_id,
        WorkspaceIntegration.workspace_id == workspace_id,
    )
    result = await db.execute(query)
    site = result.scalar_one_or_none()
    if not site:
        raise ResourceNotFoundException(
            resource_type="Site",
            resource_id=str(site_id),
        )
    return site
```

### Step 2: Add `ResourceNotFoundException` to imports

```python
# File: src/api/routes/content/modules/sites.py
# Replace line 11:
from src.api.middleware.exceptions import RextValidationException

# With:
from src.api.middleware.exceptions import RextValidationException, ResourceNotFoundException
```

### Step 3: Replace each occurrence with the helper call

**In `get_site_details()` (replace lines 109-117):**
```python
# File: src/api/routes/content/modules/sites.py
# Replace the query block with:
    site = await _get_site_or_404(db, site_id, workspace.id)
```

**In `update_site()` (replace lines 136-144):**
```python
    site = await _get_site_or_404(db, site_id, workspace.id)
```

**In `delete_site()` (replace lines 170-178):**
```python
    site = await _get_site_or_404(db, site_id, workspace.id)
```

**In `activate_site()` (replace lines 197-205):**
```python
    site = await _get_site_or_404(db, site_id, workspace.id)
```

**In `deactivate_site()` (replace lines 223-231):**
```python
    site = await _get_site_or_404(db, site_id, workspace.id)
```

**In `publish_to_site()` (replace lines 252-260):**
```python
    site = await _get_site_or_404(db, site_id, workspace.id)
```

### Step 4: Verify `RextValidationException` is still needed

After replacing all 6 site-fetch occurrences, check if `RextValidationException` is still used elsewhere in `sites.py`. It is still used in:
- `connect_site()` (line 75-78) for validation errors
- `publish_to_site()` (line 271, 301, 303) for content not found and publishing errors

So the `RextValidationException` import should be kept.

### Complete refactored `get_site_details()` example:

```python
# File: src/api/routes/content/modules/sites.py
@router.get("/{site_id}")
@require_permissions("content.read", workspace_scoped=True)
async def get_site_details(
    site_id: UUID,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """Get details of a specific connected site"""
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))
    site = await _get_site_or_404(db, site_id, workspace.id)
    return {"site": site.to_dict()}
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/middleware/exceptions.py` | Various | `ResourceNotFoundException` class — verify it exists and has `resource_type` and `resource_id` parameters |
| `src/services/content_service.py` | `224-229` | `_get_content_or_404()` — same pattern, already extracted for content. Confirms this is an established project convention. |
| `src/utils/route_decorators.py` | Various | `db_transaction_handler` must handle `ResourceNotFoundException` and return appropriate HTTP 404 response |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Count the lines in `sites.py`: `wc -l src/api/routes/content/modules/sites.py` — should be ~304 lines.
2. Search for the pattern: `grep -c "scalar_one_or_none" src/api/routes/content/modules/sites.py` — should return 6.
3. Call `GET /api/v1/content/sites/{nonexistent-uuid}` and note the error response format.

### After Fix (Verify the Solution):
1. Count the lines — should be reduced by ~40 lines.
2. Search for the pattern — `scalar_one_or_none` should appear only once (in the helper).
3. Call `GET /api/v1/content/sites/{nonexistent-uuid}` — should return a `ResourceNotFoundException`-formatted response.
4. Call `PATCH /api/v1/content/sites/{nonexistent-uuid}` — same error format.
5. Call `DELETE /api/v1/content/sites/{nonexistent-uuid}` — same error format.
6. Call `POST /api/v1/content/sites/{nonexistent-uuid}/activate` — same error format.
7. Call `POST /api/v1/content/sites/{nonexistent-uuid}/deactivate` — same error format.
8. Call `POST /api/v1/content/sites/{nonexistent-uuid}/publish/{content-uuid}` — same error format.
9. Call all endpoints with a **valid** site ID and verify they still work correctly.

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "site" -v
```

---

## Acceptance Criteria

- [ ] A `_get_site_or_404()` helper function is added to `sites.py`
- [ ] All 6 site-fetch-and-validate blocks are replaced with calls to `_get_site_or_404()`
- [ ] The helper uses `ResourceNotFoundException` (not `RextValidationException`) for "not found" errors
- [ ] `ResourceNotFoundException` is imported in `sites.py`
- [ ] Each endpoint still correctly fetches the site and operates on it
- [ ] Error responses for non-existent sites are consistent across all 6 endpoints
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [FastAPI Dependencies documentation](https://fastapi.tiangolo.com/tutorial/dependencies/) — The helper could alternatively be implemented as a FastAPI dependency, but a plain async function is simpler and sufficient here.
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [The DRY Principle — Wikipedia](https://en.wikipedia.org/wiki/Don%27t_repeat_yourself) — "Every piece of knowledge must have a single, unambiguous, authoritative representation within a system"
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None (but verify `ResourceNotFoundException` exists in `src/api/middleware/exceptions.py` and is handled by `db_transaction_handler`)
- **Blocks:** None
- **Related:** TASK-180 (DRY violation — title uniqueness check duplication, same architectural concern in the same module), TASK-170 (WorkspaceIntegration response schema includes credentials — the `to_dict()` call in the helper's callers still returns credentials, which is a separate issue)
