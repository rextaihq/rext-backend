# Task 157: Missing Permission Decorator on list_content Endpoint

## Metadata
- **Task ID:** TASK-157
- **Source:** Content Management Audit (Finding #3 under P0 Critical)
- **Audit Report:** `audit-reports/backend-content-management.md`
- **Priority:** P0 Critical
- **Category:** security
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `list_content()` endpoint in `src/api/routes/content/modules/content_retrieval.py` at lines 20-22 is missing the `@require_permissions` decorator that enforces Role-Based Access Control (RBAC). The endpoint currently only uses `@db_transaction_handler("list content", auto_commit=False)`, which provides transaction management but no authorization check beyond basic JWT authentication and workspace membership verification via `resolve_and_verify_workspace()`.

In contrast, the `get_content()` endpoint in the same file at line 71 correctly includes `@require_permissions("content.read", workspace_scoped=True)` before the transaction handler. Every other content endpoint across `publish_content.py` (5 endpoints) and `sites.py` (8 endpoints) also has the `@require_permissions` decorator. The `list_content` endpoint is the only content endpoint missing this critical authorization layer.

The `@require_permissions` decorator enforces fine-grained RBAC by checking that the authenticated user has the specific `content.read` permission for the target workspace. Without it, any authenticated user who is a member of a workspace — regardless of their assigned role or permissions — can list all content in that workspace. This violates the principle of least privilege and means that workspace roles configured to restrict content access (e.g., a "billing-only" role) are not enforced on this endpoint.

According to OWASP API Security Top 10 (API1:2023 Broken Object Level Authorization), endpoints that expose collections of resources must enforce the same authorization policies as endpoints that expose individual resources. The current code enforces permissions when reading a single content item but not when listing all content items, creating an inconsistent security boundary.

---

## Current Code

```python
# File: src/api/routes/content/modules/content_retrieval.py
# Lines: 20-22
@router.get("/")
@db_transaction_handler("list content", auto_commit=False)
async def list_content(
    request: Request,
    workspace_id: str,
    status: Optional[str] = Query(None, description="Filter by status"),
    include_metadata: bool = Query(False, description="Include metadata in response"),
    include_seo: bool = Query(False, description="Include SEO data in response"),
    limit: int = Query(100, le=500, description="Maximum number of items to return"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
```

Compare with the properly protected endpoint in the same file:

```python
# File: src/api/routes/content/modules/content_retrieval.py
# Lines: 70-72
@router.get("/{content_id}")
@require_permissions("content.read", workspace_scoped=True)
@db_transaction_handler("get content", "Content retrieved successfully", auto_commit=False)
async def get_content(
```

---

## Why This Matters (Context & Reasoning)

The content management system is the core feature of Rext AI — it stores all user-generated content including articles, SEO data, and metadata. The RBAC system exists specifically to control which workspace members can access different resources. When one endpoint bypasses this system, it creates a security gap where users with restricted roles can still access content they should not see.

The `resolve_and_verify_workspace()` call only verifies that the user is a member of the workspace — it does not check whether the user's role includes the `content.read` permission. The `@require_permissions` decorator is the layer that performs this check. Without it, role-based restrictions on content access are ineffective for the list endpoint.

This is especially concerning because the list endpoint returns the broadest dataset — up to 500 content items per request — making it the highest-value target for unauthorized access.

---

## Impact

- **Severity:** Any workspace member can list all content regardless of their assigned permissions, bypassing RBAC controls
- **Affected Users/Flows:** All workspace members accessing `GET /api/v1/content/?workspace_id=...`; any role-based content access restrictions are not enforced on listing
- **Blast Radius:** Isolated to the `list_content` endpoint, but this is the primary content discovery endpoint and returns the most data

---

## Recommended Solution

### Step 1: Add the `@require_permissions` decorator to `list_content`

```python
# File: src/api/routes/content/modules/content_retrieval.py
# Replace lines 20-21 with:
@router.get("/")
@require_permissions("content.read", workspace_scoped=True)
@db_transaction_handler("list content", auto_commit=False)
async def list_content(
```

The `@require_permissions` decorator must be placed **after** the `@router.get("/")` decorator and **before** the `@db_transaction_handler` decorator. This ordering is consistent with every other protected endpoint in the codebase (see `get_content` at line 70-72, `save_content` in publish_content.py at lines 101-103, and all sites.py endpoints).

The decorator is already imported at line 7 of the file:
```python
from src.utils.route_decorators import db_transaction_handler, require_permissions
```

No additional imports are needed.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/routes/content/modules/content_retrieval.py` | `71` | `get_content` correctly has `@require_permissions` — use as reference pattern |
| `src/api/routes/content/modules/publish_content.py` | `103, 151, 223, 303, 351` | All 5 endpoints correctly have `@require_permissions` |
| `src/api/routes/content/modules/sites.py` | `27, 50, 98, 124, 159, 186, 212, 238` | All 8 endpoints correctly have `@require_permissions` |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Create a workspace with two roles: "admin" (has `content.read`) and "restricted" (does NOT have `content.read`)
2. Assign a user the "restricted" role in the workspace
3. As the restricted user, call `GET /api/v1/content/?workspace_id=<workspace_id>`
4. **Current behavior:** The request succeeds and returns content items (authorization bypass)
5. As the restricted user, call `GET /api/v1/content/<content_id>?workspace_id=<workspace_id>`
6. **Current behavior:** The request is correctly denied with 403 Forbidden

### After Fix (Verify the Solution):
1. Using the same restricted user, call `GET /api/v1/content/?workspace_id=<workspace_id>`
2. **Expected behavior:** Request is denied with 403 Forbidden
3. Using an admin user, call `GET /api/v1/content/?workspace_id=<workspace_id>`
4. **Expected behavior:** Request succeeds and returns content items

### Run Existing Tests:
```bash
cd rext-backend
pytest tests/unit/services/test_content_service.py -v
```

---

## Acceptance Criteria

- [ ] `@require_permissions("content.read", workspace_scoped=True)` is added to the `list_content` endpoint
- [ ] The decorator is placed after `@router.get("/")` and before `@db_transaction_handler`
- [ ] Users without `content.read` permission receive 403 when calling `GET /api/v1/content/`
- [ ] Users with `content.read` permission can still list content successfully
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [FastAPI Security Dependencies](https://fastapi.tiangolo.com/tutorial/security/)
- **Security Advisory:** [OWASP API1:2023 - Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
- **Migration Guide:** N/A
- **Best Practice Reference:** [OWASP Access Control Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Access_Control_Cheat_Sheet.html)
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-008 (B1 - Commented-Out Workspace Validation in Route Decorators), TASK-073 (B3 - No `@require_permissions` on Onboarding Endpoints)
