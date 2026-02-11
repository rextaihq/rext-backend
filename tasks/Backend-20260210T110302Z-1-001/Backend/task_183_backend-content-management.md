# Task 183: Remove or Implement Unused Query Parameters in content_retrieval

## Metadata
- **Task ID:** TASK-183
- **Source:** Backend Content Management Audit (Finding #21 under P2 Medium)
- **Audit Report:** `audit-reports/backend-content-management.md`
- **Priority:** P2 Medium
- **Category:** code-quality
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `list_content()` endpoint in `src/api/routes/content/modules/content_retrieval.py` declares two query parameters — `include_metadata` (line 26) and `include_seo` (line 27) — that are accepted from the client but never used in the function body. These parameters are passed through FastAPI's `Query()` declaration, which means they automatically appear in the auto-generated OpenAPI/Swagger documentation, misleading API consumers into believing they control response behavior.

When a client sends `?include_metadata=true&include_seo=true`, the API accepts the parameters without error but silently ignores them — the response always includes the same data regardless of these parameter values. The `list_content` route on line 50 calls `ContentService.list_content()` passing only `workspace_id`, `status`, `limit`, and `offset` — neither `include_metadata` nor `include_seo` are forwarded.

Similarly, the `get_content()` endpoint at lines 77-78 declares the same two parameters with default values of `True` (instead of `False` on the list endpoint), but also never uses them. The `get_content` route on line 90 calls `ContentService.get_content()` passing only `content_id` and `workspace_id`.

According to OpenAPI specification best practices and FastAPI documentation, every declared parameter should be functional. Declaring unused parameters in an API endpoint violates the principle of least surprise and pollutes the API contract. The recommended approach is to either implement the filtering functionality or remove the parameters entirely until they are needed.

---

## Current Code

```python
# File: src/api/routes/content/modules/content_retrieval.py
# Lines: 20-64 (list_content endpoint)
@router.get("/")
@db_transaction_handler("list content", auto_commit=False)
async def list_content(
    request: Request,
    workspace_id: str,
    status: Optional[str] = Query(None, description="Filter by status"),
    include_metadata: bool = Query(False, description="Include metadata in response"),  # UNUSED
    include_seo: bool = Query(False, description="Include SEO data in response"),        # UNUSED
    limit: int = Query(100, le=500, description="Maximum number of items to return"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    # ... workspace verification ...
    service = ContentService(db)
    result = await service.list_content(
        workspace_id=workspace.id,
        status=status,
        limit=limit,
        offset=offset
        # include_metadata and include_seo are NOT passed
    )
    # ...
```

```python
# File: src/api/routes/content/modules/content_retrieval.py
# Lines: 70-96 (get_content endpoint)
@router.get("/{content_id}")
@require_permissions("content.read", workspace_scoped=True)
@db_transaction_handler("get content", "Content retrieved successfully", auto_commit=False)
async def get_content(
    content_id: UUID,
    request: Request,
    workspace_id: str,
    include_metadata: bool = Query(True, description="Include metadata in response"),   # UNUSED
    include_seo: bool = Query(True, description="Include SEO data in response"),         # UNUSED
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    # ... workspace verification ...
    service = ContentService(db)
    content_data = await service.get_content(
        content_id=content_id,
        workspace_id=workspace.id
        # include_metadata and include_seo are NOT passed
    )
    return {"content": content_data}
```

---

## Why This Matters (Context & Reasoning)

The content retrieval endpoints are the primary way the frontend fetches content data. Having non-functional query parameters in the API contract is misleading: a frontend developer or third-party integrator might try to use `include_seo=false` to reduce payload size and be confused when the response still contains SEO data. It also bloats the Swagger documentation with parameters that have no effect. Removing them keeps the API honest and the documentation accurate. If selective field inclusion is needed later, it can be added as a proper feature with actual implementation.

---

## Impact

- **Severity:** API consumers are misled by non-functional documented parameters. No runtime crash or security issue.
- **Affected Users/Flows:** Any consumer of `GET /api/v1/content/` and `GET /api/v1/content/{content_id}` — frontend and potential API integrations.
- **Blast Radius:** Isolated to two endpoints in content_retrieval.py. Removing unused parameters is a non-breaking change since no client logic can depend on parameters that do nothing.

---

## Recommended Solution

The recommended approach is to **remove the unused parameters** since there is no implementation behind them. If selective field inclusion is desired in the future, it should be implemented properly as a new feature with actual service-layer support.

### Step 1: Remove unused parameters from `list_content`

```python
# File: src/api/routes/content/modules/content_retrieval.py
# Replace lines 20-32 with:
@router.get("/")
@db_transaction_handler("list content", auto_commit=False)
async def list_content(
    request: Request,
    workspace_id: str,
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(100, le=500, description="Maximum number of items to return"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
```

### Step 2: Remove unused parameters from `get_content`

```python
# File: src/api/routes/content/modules/content_retrieval.py
# Replace lines 70-81 with:
@router.get("/{content_id}")
@require_permissions("content.read", workspace_scoped=True)
@db_transaction_handler("get content", "Content retrieved successfully", auto_commit=False)
async def get_content(
    content_id: UUID,
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-admin/lib/api-client/content.ts` | Various | Check if the frontend passes `include_metadata` or `include_seo` query params — if so, those references should also be removed |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Start the backend server and open the Swagger UI at `/docs`
2. Navigate to the `GET /api/v1/content/` endpoint
3. Observe that `include_metadata` and `include_seo` appear as documented query parameters
4. Send a request with `include_seo=true` and another with `include_seo=false`
5. Confirm that both responses contain identical data — the parameter has no effect

### After Fix (Verify the Solution):
1. Restart the backend server and open Swagger UI at `/docs`
2. Navigate to `GET /api/v1/content/`
3. Confirm `include_metadata` and `include_seo` no longer appear in the parameter list
4. Send a normal request and confirm content is returned correctly
5. Repeat for `GET /api/v1/content/{content_id}`

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/unit/services/test_content_service.py -v
cd rext-backend && python -m pytest tests/ -k "content" -v
```

---

## Acceptance Criteria

- [ ] `include_metadata` parameter removed from `list_content` endpoint signature
- [ ] `include_seo` parameter removed from `list_content` endpoint signature
- [ ] `include_metadata` parameter removed from `get_content` endpoint signature
- [ ] `include_seo` parameter removed from `get_content` endpoint signature
- [ ] Swagger/OpenAPI docs no longer show these parameters
- [ ] Both endpoints still return correct data
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [FastAPI Query Parameters and String Validations](https://fastapi.tiangolo.com/tutorial/query-params-str-validations/) — documentation on declaring query parameters in FastAPI
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [OpenAPI Specification v3.1.0 — Describing Parameters](https://spec.openapis.org/oas/v3.1.0) — every declared parameter should be functional; use `deprecated: true` for parameters being phased out
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** None
