# Task 106: Improve Vector Cleanup Error Handling to Prevent Orphaned Data

## Metadata
- **Task ID:** TASK-106
- **Source:** Backend Workspace Management Audit (Finding #16 under P2 Medium)
- **Audit Report:** `audit-reports/backend-workspace-management.md`
- **Priority:** P2 Medium
- **Category:** bug
- **Effort Estimate:** medium (1-4 hours)

---

## Description

In `src/services/workspace_service.py` at lines 1088-1095, the `_delete_vectors_safe()` method catches all exceptions during vector store cleanup and silently logs them at `WARNING` level without propagating the error or recording the failure for later retry. This method is called on line 272 during workspace deletion (`delete_workspace_for_user()`), where the calling code proceeds to soft-delete the workspace regardless of whether vector cleanup succeeded.

The current implementation:

```python
def _delete_vectors_safe(self, workspace_id: UUID) -> None:
    try:
        delete_vectors(vector_id=str(workspace_id))
    except Exception as err:
        logger.warning(
            "Vector cleanup failed",
            extra={"workspace_id": str(workspace_id), "error": str(err)},
        )
```

While the "safe" suffix correctly communicates that this method is designed to not block the calling operation, there are several problems: (1) Logging at `WARNING` level instead of `ERROR` means this issue may be overlooked in production monitoring since WARNING-level logs are often not alerted on, (2) there is no mechanism to track or retry the failed cleanup, so orphaned vectors accumulate silently in the vector store over time, (3) the method is synchronous (`def`, not `async def`) and calls `delete_vectors()` which appears to be a synchronous function — this means if called from an async context, it blocks the event loop, and (4) there are no metrics or counters to track the rate of vector cleanup failures for operational visibility.

The `delete_vectors()` function in `src/utils/vector_store.py` (line 214) performs the actual vector store deletion. It is also called directly (without the "safe" wrapper) in `src/services/knowledge_service.py` at lines 229, 459, and 582 for individual knowledge item deletion, where failures are propagated to the caller.

The concern is that over time, orphaned vectors from deleted workspaces will consume storage in the vector database and potentially pollute search results if the workspace IDs are ever reused or if there are bugs in vector filtering.

---

## Current Code

```python
# File: src/services/workspace_service.py
# Lines: 1088-1095
    def _delete_vectors_safe(self, workspace_id: UUID) -> None:
        try:
            delete_vectors(vector_id=str(workspace_id))
        except Exception as err:  # noqa: BLE001
            logger.warning(
                "Vector cleanup failed",
                extra={"workspace_id": str(workspace_id), "error": str(err)},
            )
```

```python
# File: src/services/workspace_service.py
# Lines: 266-273 (calling context)
    async def delete_workspace_for_user(
        self, workspace_id: UUID, user_id: UUID
    ) -> None:
        """Delete workspace after verifying membership and cleanup."""
        await self._ensure_active_user(user_id)
        workspace = await self._ensure_membership(workspace_id, user_id)
        self._delete_vectors_safe(workspace.id)
        await self.delete_workspace(workspace_id, user_id)
```

---

## Why This Matters (Context & Reasoning)

Workspace deletion is a significant operation that involves cleaning up multiple associated resources including vector embeddings in the vector store. The vector store is used for semantic search over workspace content (web pages, documents, text knowledge). When a workspace is deleted, its vectors should be removed to: (1) free storage, (2) prevent stale data from appearing in any system-wide operations, and (3) maintain data hygiene.

The current "fire and forget" approach means that if the vector store is temporarily unavailable (network issue, service downtime) or if there's a bug in the deletion logic, the vectors remain permanently orphaned with no way to detect or clean them up. Over time, this leads to storage waste and potentially degraded search performance.

The risk of not fixing this is gradual accumulation of orphaned vector data that is costly to identify and clean up after the fact, since the only record of the failure is a WARNING log line that is likely rotated out within days.

---

## Impact

- **Severity:** Orphaned vector data accumulates silently in the vector store. No alerting, no retry mechanism, and no way to identify affected workspaces after logs are rotated.
- **Affected Users/Flows:** Workspace deletion flow. All users who delete workspaces.
- **Blast Radius:** Isolated to workspace deletion, but the accumulated orphaned data affects the vector store infrastructure globally.

---

## Recommended Solution

### Step 1: Upgrade logging from WARNING to ERROR level

This ensures vector cleanup failures appear in error monitoring dashboards and trigger alerts.

```python
# File: src/services/workspace_service.py
# Replace lines 1088-1095 with:
    def _delete_vectors_safe(self, workspace_id: UUID) -> None:
        """
        Attempt to delete vectors for a workspace. Logs errors but does not
        propagate exceptions, allowing workspace deletion to proceed.
        """
        try:
            delete_vectors(vector_id=str(workspace_id))
            logger.info(
                "Vector cleanup completed",
                extra={"workspace_id": str(workspace_id)},
            )
        except Exception as err:  # noqa: BLE001
            logger.error(
                "Vector cleanup failed — orphaned vectors may remain",
                extra={
                    "workspace_id": str(workspace_id),
                    "error": str(err),
                    "error_type": type(err).__name__,
                    "action_required": "manual_vector_cleanup",
                },
                exc_info=True,
            )
```

### Step 2: Record failed cleanups for future retry

Create a lightweight mechanism to track failed vector cleanups so they can be retried by a background job.

```python
# File: src/services/workspace_service.py
# Replace the entire _delete_vectors_safe method with:
    def _delete_vectors_safe(self, workspace_id: UUID) -> None:
        """
        Attempt to delete vectors for a workspace. Logs errors but does not
        propagate exceptions, allowing workspace deletion to proceed.
        Failed cleanups are recorded for later retry.
        """
        try:
            delete_vectors(vector_id=str(workspace_id))
            logger.info(
                "Vector cleanup completed",
                extra={"workspace_id": str(workspace_id)},
            )
        except Exception as err:  # noqa: BLE001
            logger.error(
                "Vector cleanup failed — orphaned vectors may remain",
                extra={
                    "workspace_id": str(workspace_id),
                    "error": str(err),
                    "error_type": type(err).__name__,
                    "action_required": "manual_vector_cleanup",
                },
                exc_info=True,
            )
            # Record for later retry — store in Redis if available
            try:
                import json
                from src.api.cache.redis_client import get_redis_client
                redis_client = get_redis_client()
                if redis_client:
                    redis_client.lpush(
                        "vector_cleanup_failures",
                        json.dumps({
                            "workspace_id": str(workspace_id),
                            "error": str(err),
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })
                    )
            except Exception:  # noqa: BLE001
                pass  # If Redis is unavailable, the error log is sufficient
```

### Step 3 (Optional): Create a background cleanup task

For a more robust solution, create a periodic task that retries failed vector cleanups. This can be added later as a separate task.

```python
# File: src/tasks/vector_cleanup_task.py (new file — optional, can be deferred)
"""
Periodic task to retry failed vector cleanups.
Check Redis list 'vector_cleanup_failures' and retry each entry.
"""
import json
from src.utils.vector_store import delete_vectors
from src.api.cache.redis_client import get_redis_client
from src.utils.logger import logger


async def retry_failed_vector_cleanups() -> int:
    """Retry all recorded vector cleanup failures. Returns count of successful retries."""
    redis_client = get_redis_client()
    if not redis_client:
        return 0

    retried = 0
    while True:
        item = redis_client.rpop("vector_cleanup_failures")
        if not item:
            break

        try:
            data = json.loads(item)
            workspace_id = data["workspace_id"]
            delete_vectors(vector_id=workspace_id)
            logger.info(
                "Vector cleanup retry succeeded",
                extra={"workspace_id": workspace_id},
            )
            retried += 1
        except Exception as err:  # noqa: BLE001
            logger.error(
                "Vector cleanup retry failed — will try again later",
                extra={"data": data, "error": str(err)},
            )
            # Push back to the list for next retry cycle
            redis_client.lpush("vector_cleanup_failures", item)
            break  # Stop retrying on first failure to avoid infinite loop

    return retried
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/services/knowledge_service.py` | 229, 459, 582 | Direct calls to `delete_vectors()` without the "safe" wrapper — failures propagate to callers. Consider adding similar error handling or retry logic here. |
| `src/utils/vector_store.py` | 214+ | The `delete_vectors()` function itself — may need review for proper error handling and logging |
| `src/api/routes/workspaces/members/members_routes.py` | 10 | Imports `delete_vectors` — may have similar silent failure patterns |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Temporarily make the vector store unavailable (e.g., misconfigure the connection)
2. Delete a workspace via `DELETE /api/v1/workspaces/{workspace_id}`
3. Observe that the workspace is soft-deleted successfully
4. Check logs — only a WARNING-level message appears, not ERROR
5. No record of the failure exists for later cleanup

### After Fix (Verify the Solution):
1. With vector store unavailable, delete a workspace
2. Workspace soft-deletion should still succeed (non-blocking)
3. Check logs — an ERROR-level message appears with full stack trace and `action_required: manual_vector_cleanup`
4. If Redis is available, check `LRANGE vector_cleanup_failures 0 -1` — should contain the workspace ID

### Edge Cases:
- Vector store available: cleanup succeeds silently with INFO log
- Vector store unavailable AND Redis unavailable: only ERROR log, no crash
- Multiple failed cleanups: all are queued in Redis

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "workspace" -v
```

---

## Acceptance Criteria

- [ ] Vector cleanup failures are logged at ERROR level (not WARNING)
- [ ] Error logs include full stack trace (`exc_info=True`) and `error_type` field
- [ ] Failed vector cleanups are recorded in Redis for later retry (if Redis is available)
- [ ] Workspace deletion still succeeds even when vector cleanup fails
- [ ] Successful vector cleanups are logged at INFO level for observability
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Python logging best practices](https://docs.python.org/3/howto/logging.html#when-to-use-logging) — documents when to use WARNING vs ERROR level: ERROR is for "a more serious problem" and WARNING for "an indication that something unexpected happened"
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [The Twelve-Factor App — Logs](https://12factor.net/logs) — recommends treating logs as event streams; ERROR-level events should trigger alerts
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-089 (B4: Integration Credentials Stored in Plaintext — same service file), TASK-090 (B4: Missing Soft-Delete Filter — related to workspace deletion correctness)
