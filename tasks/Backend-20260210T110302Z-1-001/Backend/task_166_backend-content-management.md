# Task 166: Frontend Calls Non-Existent Endpoint — POST /api/v1/content/ (Create)

## Metadata
- **Task ID:** TASK-166
- **Source:** B6 - Content Management (Finding #13 under P1 High)
- **Audit Report:** `audit-reports/backend-content-management.md`
- **Priority:** P1 High
- **Category:** broken-functionality
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The frontend API client at `rext-admin/lib/api-client/content.ts` defines a `create` method (lines 56-64) that sends a `POST` request to `/api/v1/content/?workspace_id=...`. This endpoint does not exist in the backend. The backend content router (`rext-backend/src/api/routes/content/modules/`) defines the following `POST` endpoints:

- `POST /api/v1/content/save` — saves content as draft (defined in `publish_content.py:101`)
- `POST /api/v1/content/publish` — saves and publishes content (defined in `publish_content.py:149`)
- `POST /api/v1/content/{content_id}/publish` — publishes existing content (defined in `publish_content.py:221`)

There is no generic `POST /api/v1/content/` endpoint. FastAPI/Starlette will return HTTP 404 Not Found for this request.

The frontend `create` method is defined as:
```typescript
create: async (workspaceId: string, data: CreateContentRequest) => {
  return client.request<ContentResponse>(
    `/api/v1/content/?workspace_id=${encodeURIComponent(workspaceId)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    },
  );
},
```

The frontend also already has separate `save` (lines 112-121) and `publish` (lines 126-135) methods that correctly target the existing backend endpoints (`/api/v1/content/save` and `/api/v1/content/publish` respectively). This means the `create` method is either:
1. A vestige from a previous API design that was never updated when the backend split the endpoint into `save` and `publish`, or
2. An intended generic create endpoint that was never implemented on the backend.

Additionally, the frontend has a `retry` method (lines 100-107) that calls `POST /api/v1/content/{contentId}/retry?workspace_id=...` — this endpoint also does not exist in the backend. The retry method is actively used in the content detail page (`rext-admin/app/w/[workspaceSlug]/content/[id]/page.tsx:159`), where `handleRetry()` calls `apiClient.content.retry(workspaceId, id)`. This will always fail with a 404 error, and the UI shows a misleading error toast "Failed to retry generation. Please try again."

---

## Current Code

```typescript
// File: rext-admin/lib/api-client/content.ts
// Lines: 53-65 (create method — calls non-existent endpoint)
    /**
     * Create new content
     */
    create: async (workspaceId: string, data: CreateContentRequest) => {
      return client.request<ContentResponse>(
        `/api/v1/content/?workspace_id=${encodeURIComponent(workspaceId)}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(data),
        },
      );
    },
```

```typescript
// File: rext-admin/lib/api-client/content.ts
// Lines: 97-107 (retry method — calls non-existent endpoint)
    /**
     * Retry content generation
     */
    retry: async (workspaceId: string, contentId: string) => {
      return client.request<{ content_id: string; status: string }>(
        `/api/v1/content/${contentId}/retry?workspace_id=${encodeURIComponent(workspaceId)}`,
        {
          method: "POST",
        },
      );
    },
```

```typescript
// File: rext-admin/app/w/[workspaceSlug]/content/[id]/page.tsx
// Lines: 152-172 (retry handler — actively calls the non-existent retry endpoint)
  const handleRetry = async () => {
    if (!workspaceId) return;

    setIsRetrying(true);
    try {
      contentLogger.info("Retrying content generation", { contentId: id });

      await apiClient.content.retry(workspaceId, id);

      toast.success("Content generation restarted!");

      // Reset state and refetch
      setCurrentProgress(0);
      await refetchContent();
    } catch (error) {
      contentLogger.error("Failed to retry content generation", { error });
      toast.error("Failed to retry generation. Please try again.");
    } finally {
      setIsRetrying(false);
    }
  };
```

Backend routes (confirmed — no `POST /` or `POST /{id}/retry`):
```python
# File: rext-backend/src/api/routes/content/modules/publish_content.py
@router.post("/save", response_model=ContentResponse)        # Line 101
@router.post("/publish")                                      # Line 149
@router.post("/{content_id}/publish")                         # Line 221
@router.patch("/{content_id}", response_model=ContentResponse) # Line 301
@router.delete("/{content_id}")                               # Line 349

# File: rext-backend/src/api/routes/content/modules/content_retrieval.py
@router.get("/")                                              # Line 20
@router.get("/{content_id}")                                  # Line 70
```

---

## Why This Matters (Context & Reasoning)

The frontend-backend contract is broken in two places:

1. **`create` method:** While the frontend has separate `save` and `publish` methods that work correctly, the `create` method appears to be intended as a convenience wrapper for "create content without specifying whether to save or publish." Any UI component or flow that calls `apiClient.content.create()` instead of `apiClient.content.save()` will fail silently with a 404 error.

2. **`retry` method:** This is actively used in the content detail page. When content generation fails (e.g., the LangGraph AI workflow fails), users see a "Retry" button that calls this endpoint. Clicking retry will always fail with a 404, leaving users unable to recover from failed content generation — a critical user-facing bug.

The content generation workflow is a core feature of Rext AI. If a user's AI-generated content fails mid-generation, the retry mechanism is their only way to recover without creating a new content item from scratch.

---

## Impact

- **Severity:** The `retry` endpoint being non-existent is a user-facing bug — users cannot retry failed content generation. The `create` endpoint mismatch may not be actively triggered if UI components use `save`/`publish` directly, but it's a latent bug.
- **Affected Users/Flows:** (1) All users who attempt to retry failed content generation — completely broken. (2) Any UI component that uses the generic `create()` method instead of `save()`.
- **Blast Radius:** The retry issue affects the content detail page (`/w/{workspaceSlug}/content/{id}`). The create issue affects any content creation flow that uses `apiClient.content.create()` instead of `apiClient.content.save()`.

---

## Recommended Solution

This requires changes on both the frontend and backend to resolve the mismatch. The recommended approach is to implement the missing endpoints on the backend, as the frontend correctly models the desired functionality.

### Step 1: Implement the retry endpoint on the backend

The retry endpoint should reset a failed content's status back to a state that allows re-triggering the AI generation workflow (likely via LangGraph).

```python
# File: rext-backend/src/api/routes/content/modules/publish_content.py
# Add after the delete endpoint (after line 373):

# -------------------------
# 6. Retry Content Generation
# -------------------------
@router.post("/{content_id}/retry")
@db_transaction_handler("retry content generation", "Content generation restarted")
@require_permissions("content.create", workspace_scoped=True)
async def retry_content_generation(
    content_id: UUID,
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Retry content generation for failed content.

    Resets content status to 'generating' and re-triggers the AI workflow.
    Only works for content in 'failed' or 'draft' status.
    """
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    service = ContentService(db)
    content = await service._get_content_or_404(content_id, workspace.id)

    # Validate the content is in a retryable state
    retryable_statuses = {"draft", "generating"}
    if content.status not in retryable_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Content in '{content.status}' status cannot be retried. "
                   f"Only content in {retryable_statuses} status can be retried."
        )

    # Reset status to generating
    content.status = "generating"
    content.updated_at = datetime.now(timezone.utc)

    # TODO: Re-trigger LangGraph workflow here
    # This should create a new LangGraph thread or resume the existing one
    # Example: await langgraph_service.trigger_generation(content.id, content.langgraph_thread_id)

    return {
        "content_id": str(content.id),
        "status": content.status,
        "message": "Content generation restarted"
    }
```

**Note:** The actual LangGraph re-trigger logic depends on how the AI workflow is implemented (likely in `src/services/` or the LangGraph graph definitions). The TODO comment marks where this integration should be added. Consult with the team on the specific LangGraph re-trigger mechanism.

### Step 2: Decide on the generic create endpoint

For the `create` method, there are two options:

**Option A (Recommended): Update the frontend `create` method to call `/save`**

Since the frontend already has `save` and `publish` methods, update `create` to delegate to `/save`:

```typescript
// File: rext-admin/lib/api-client/content.ts
// Replace lines 56-64 with:
    /**
     * Create new content (saves as draft)
     */
    create: async (workspaceId: string, data: CreateContentRequest) => {
      return client.request<ContentResponse>(
        `/api/v1/content/save?workspace_id=${encodeURIComponent(workspaceId)}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(data),
        },
      );
    },
```

**Option B: Add a generic POST endpoint to the backend**

If you prefer to keep the frontend unchanged, add a backend endpoint that accepts `POST /api/v1/content/` and delegates to the save logic. However, this adds redundancy with the existing `/save` endpoint.

### Step 3: Verify all frontend content API calls match backend endpoints

After changes, verify the complete mapping:

| Frontend Method | Frontend Endpoint | Backend Route | Status |
|-----------------|------------------|---------------|--------|
| `list` | `GET /api/v1/content/` | `GET /` (content_retrieval.py:20) | OK |
| `get` | `GET /api/v1/content/{id}` | `GET /{content_id}` (content_retrieval.py:70) | OK |
| `create` | `POST /api/v1/content/save` | `POST /save` (publish_content.py:101) | After fix |
| `update` | `PATCH /api/v1/content/{id}` | `PATCH /{content_id}` (publish_content.py:301) | OK |
| `delete` | `DELETE /api/v1/content/{id}` | `DELETE /{content_id}` (publish_content.py:349) | OK |
| `retry` | `POST /api/v1/content/{id}/retry` | `POST /{content_id}/retry` (new) | After fix |
| `save` | `POST /api/v1/content/save` | `POST /save` (publish_content.py:101) | OK |
| `publish` | `POST /api/v1/content/publish` | `POST /publish` (publish_content.py:149) | OK |

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-admin/app/w/[workspaceSlug]/content/[id]/page.tsx` | `152-172` | `handleRetry()` function that calls the non-existent retry endpoint — actively broken |
| `rext-admin/services/content-api.ts` | `158-204` | Legacy `createContent()` also calls a non-existent URL pattern — see TASK-165 |
| `rext-admin/types/content.ts` | `4-12` | Content status enum includes `failed` status which triggers the retry UI |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Start the backend server
2. In the frontend, navigate to a content item that is in "generating" or "failed" status (or any status that shows the retry button)
3. Click the "Retry" button
4. Open browser DevTools Network tab — observe a 404 response for `POST /api/v1/content/{id}/retry`
5. The UI shows "Failed to retry generation. Please try again."

### After Fix (Verify the Solution):
1. Start the backend server with the new retry endpoint
2. Navigate to a content item in a retryable status
3. Click the "Retry" button
4. Observe a successful response in Network tab
5. Content status should change to "generating"
6. The UI should show "Content generation restarted!"

### For the create method:
1. Find any UI flow that calls `apiClient.content.create()` (search for `.content.create(`)
2. Test that content creation via that flow succeeds
3. Verify the content appears in the content list

### Run Existing Tests:
```bash
# Backend
cd rext-backend
python -m pytest tests/unit/services/test_content_service.py -v

# Frontend
cd rext-admin
npm run test
npm run build
```

---

## Acceptance Criteria

- [ ] Backend has a `POST /{content_id}/retry` endpoint that resets content status for re-generation
- [ ] The retry endpoint validates that content is in a retryable state before resetting
- [ ] Frontend `create` method targets an existing backend endpoint (either `/save` or a new generic endpoint)
- [ ] Frontend `retry` method successfully calls the new backend retry endpoint
- [ ] The "Retry" button on the content detail page works correctly for failed content
- [ ] All frontend-to-backend content API method mappings are verified and correct
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [FastAPI — Path Operation Decorators](https://fastapi.tiangolo.com/tutorial/first-steps/#define-a-path-operation-decorator) — How to define new endpoints
- **Official Docs:** [FastAPI — Automatic OpenAPI Schema Generation](https://fastapi.tiangolo.com/how-to/extending-openapi/) — Can be used to auto-generate frontend clients from backend schema
- **Official Docs:** [MDN — HTTP 404 Not Found](https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/404) — The error returned for non-existent endpoints
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [OpenAPI TypeScript Client Generation](https://openapi-ts.dev/) — The project uses `@hey-api/openapi-ts` (in devDependencies) which can auto-generate type-safe API clients from FastAPI's OpenAPI schema, preventing endpoint mismatches
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-165 (Legacy frontend API client also has endpoint mismatches), TASK-161 (Status enum mismatch — the retry feature depends on the "failed" status being properly handled)
