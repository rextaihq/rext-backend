# Task 167: Frontend Calls Non-Existent Content Retry Endpoint

## Metadata
- **Task ID:** TASK-167
- **Source:** Content Management Audit (Finding #14 under P1 High)
- **Audit Report:** `audit-reports/backend-content-management.md`
- **Priority:** P1 High
- **Category:** bug
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The frontend application defines a `retry` method in the content API client at `rext-admin/lib/api-client/content.ts:100-106` that sends a `POST` request to `/api/v1/content/{contentId}/retry?workspace_id=...`. This endpoint does not exist anywhere in the backend. The backend content routes, defined across `src/api/routes/content/modules/content_retrieval.py`, `src/api/routes/content/modules/publish_content.py`, and `src/api/routes/content/modules/sites.py`, include endpoints for listing, getting, saving, publishing, updating, and deleting content, but there is no `/{content_id}/retry` route registered.

The frontend actively calls this non-existent endpoint. At `rext-admin/app/w/[workspaceSlug]/content/[id]/page.tsx:159`, the `handleRetry` function invokes `await apiClient.content.retry(workspaceId, id)` when a user clicks a retry button after content generation fails. The content generation workflow uses LangGraph (tracked via `langgraph_thread_id` on the Content model), and when generation fails (status becomes `"failed"`), the user expects to be able to retry the operation. Instead, they receive a 404 error, a toast notification saying "Failed to retry generation. Please try again.", and are left with no way to recover failed content generation through the UI.

The backend status state machine at `src/services/content_service.py:232` does not include a `"failed"` status at all — the allowed statuses are `generating`, `draft`, `ready`, `published`, and `archived`. However, the frontend defines `ContentStatus` in `rext-admin/types/content.ts:4-12` with `"failed"` as a valid status. This means the retry flow is doubly broken: the backend cannot transition content to "failed" status (so the retry trigger condition may never properly occur on the backend side), and even if it did, there's no endpoint to handle the retry.

According to LangGraph documentation, retry workflows can either resume from the last checkpoint using the same `thread_id`, or start a completely new thread. Since the Content model already stores `langgraph_thread_id`, the recommended approach is to implement a backend endpoint that either resumes the existing LangGraph thread or creates a new one, resets the content status to `"generating"`, and triggers the content generation workflow again.

---

## Current Code

```typescript
// File: rext-admin/lib/api-client/content.ts
// Lines: 97-107
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
// Lines: 151-172
  // Handle retry
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

```python
# File: src/services/content_service.py
# Lines: 231-233
    async def _validate_status_transition(self, current: str, new: str) -> None:
        ALLOWED = {"generating": ["ready", "archived", "draft"], "draft": ["ready", "archived", "generating"], "ready": ["published", "draft", "archived", "generating"], "published": ["archived", "ready"], "archived": []}
        if new not in ALLOWED.get(current, []): raise RextValidationException(message=f"Invalid transition: {current} -> {new}")
```

---

## Why This Matters (Context & Reasoning)

Content generation in Rext AI is a core feature — users create content outlines and the system uses LangGraph-based AI workflows to generate full articles. These workflows can fail due to LLM API rate limits, timeouts, or internal errors. When generation fails, the user's only recourse should be a "Retry" button that re-triggers the generation. Without a working retry endpoint, users with failed content are stuck: they must delete the failed content and start over from scratch, losing any configuration, SEO data, or partial progress. This creates a poor user experience and increases churn risk, especially for users generating high volumes of content who are more likely to encounter transient failures.

---

## Impact

- **Severity:** Users cannot recover from failed content generation — the retry button always returns a 404 error. Users must delete and re-create content from scratch.
- **Affected Users/Flows:** Any user who experiences a content generation failure and clicks the "Retry" button on the content detail page.
- **Blast Radius:** Isolated to the content generation retry flow, but this is a critical user journey for the core product feature.

---

## Recommended Solution

The fix requires adding a backend endpoint and updating the status state machine to support the `"failed"` status and the retry transition.

### Step 1: Add `"failed"` Status to Backend State Machine

```python
# File: src/services/content_service.py
# Replace lines 231-233 with:
    async def _validate_status_transition(self, current: str, new: str) -> None:
        ALLOWED = {
            "generating": ["ready", "archived", "draft", "failed"],
            "draft": ["ready", "archived", "generating"],
            "ready": ["published", "draft", "archived", "generating"],
            "published": ["archived", "ready"],
            "archived": [],
            "failed": ["generating", "draft", "archived"],
        }
        if new not in ALLOWED.get(current, []):
            raise RextValidationException(
                message=f"Invalid status transition: '{current}' -> '{new}'"
            )
```

### Step 2: Add `retry_content_generation` Method to ContentService

```python
# File: src/services/content_service.py
# Add after the publish_content method (after line 208):

    async def retry_content_generation(
        self, content_id: UUID, workspace_id: UUID, user_id: UUID
    ) -> Content:
        """
        Retry content generation for failed content.

        Resets content status to 'generating' and clears the previous
        LangGraph thread ID so a new workflow can be started.
        """
        content = await self._get_content_or_404(content_id, workspace_id)

        if content.status not in ("failed", "draft"):
            raise RextValidationException(
                message=f"Content must be in 'failed' or 'draft' status to retry generation. Current status: '{content.status}'"
            )

        # Reset status to generating
        content.status = "generating"
        # Clear previous thread so a new generation workflow starts
        content.langgraph_thread_id = None
        content.updated_at = datetime.now(timezone.utc)

        await self.db.flush()
        logger.info(f"Content generation retry initiated: content_id={content_id}, user_id={user_id}")
        return content
```

### Step 3: Add the Retry Endpoint to Routes

```python
# File: src/api/routes/content/modules/publish_content.py
# Add after the delete_content endpoint (after line 373):

# -------------------------
# 6. Retry Content Generation
# -------------------------
@router.post("/{content_id}/retry")
@db_transaction_handler("retry content generation", "Content generation retry initiated")
@require_permissions("content.update", workspace_scoped=True)
async def retry_content_generation(
    content_id: UUID,
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Retry content generation for failed or draft content.

    Resets the content status to 'generating' and clears the
    LangGraph thread ID so a new generation workflow can be started.
    """
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    service = ContentService(db)
    content = await service.retry_content_generation(
        content_id=content_id,
        workspace_id=workspace.id,
        user_id=UUID(user_id)
    )

    return {
        "content_id": str(content.id),
        "status": content.status,
        "message": "Content generation retry initiated"
    }
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-admin/types/content.ts` | `4-12` | Frontend `ContentStatus` type includes `"failed"` — this is correct and should be kept |
| `rext-admin/types/content.ts` | `46-55` | Frontend `CONTENT_STATUS_CONFIG` already has config for `"failed"` status — correct |
| `src/api/models/content_models/content.py` | `31` | `langgraph_thread_id` field exists on Content model — used by retry to reset thread |
| `src/services/content_service.py` | `231-233` | Status state machine needs `"failed"` status added |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Navigate to any content detail page in the frontend where content generation has completed or is in draft state
2. Open browser developer tools Network tab
3. Trigger the retry action (if a retry button is visible, or simulate by calling `apiClient.content.retry(workspaceId, contentId)` in the console)
4. Observe that the request to `POST /api/v1/content/{contentId}/retry` returns a 404 Not Found error

### After Fix (Verify the Solution):
1. Create a content item and set its status to `"failed"` (or use a content item that failed during generation)
2. Call the retry endpoint: `POST /api/v1/content/{content_id}/retry?workspace_id={workspace_id}`
3. Verify the response contains `{"content_id": "...", "status": "generating", "message": "Content generation retry initiated"}`
4. Verify the content's `langgraph_thread_id` has been cleared (set to null)
5. Verify the content's status is now `"generating"`
6. Verify that calling retry on content with status `"published"` returns a validation error
7. Test the frontend flow: navigate to a failed content item, click Retry, and confirm the toast shows "Content generation restarted!"

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/unit/services/test_content_service.py -v
```

---

## Acceptance Criteria

- [ ] Backend endpoint `POST /api/v1/content/{content_id}/retry` exists and is accessible
- [ ] The endpoint requires authentication and `content.update` permission
- [ ] The endpoint resets content status to `"generating"` and clears `langgraph_thread_id`
- [ ] The endpoint returns 400 if content is not in `"failed"` or `"draft"` status
- [ ] The status state machine includes `"failed"` as a valid status with appropriate transitions
- [ ] Frontend retry button successfully calls the endpoint without 404 errors
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [FastAPI Background Tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/) — patterns for triggering async operations from endpoints
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [LangGraph Error Handling and Retry Policies](https://docs.langchain.com/oss/python/langgraph/thinking-in-langgraph) — guidance on thread-based retry patterns
- **Related Issues/PRs:** None identified

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-161 (Status Enum Mismatch Between Frontend and Backend) — the `"failed"` status alignment is part of both issues; TASK-166 (Frontend Calls Non-Existent POST /content/ Endpoint) — similar frontend-backend endpoint gap
