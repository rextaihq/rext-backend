# Task 093: Broken Callback Registration (Indentation Bug)

## Metadata
- **Task ID:** TASK-093
- **Source:** B4 - Workspace Management (Finding #3 under P0 Critical)
- **Audit Report:** `audit-reports/backend-workspace-management.md`
- **Priority:** P0 Critical
- **Category:** bug
- **Effort Estimate:** small (< 1 hour)

---

## Description

In `src/services/workspace_service.py` (lines 164-179), the `task.add_done_callback(handle_completion)` call on line 179 is incorrectly indented **inside** the `handle_completion` function body, specifically inside the `with trace(name="Worksapce Completion")` context manager block. This means the callback is **never registered** on the background task. Instead, `task.add_done_callback(handle_completion)` would only be called if `handle_completion` were somehow invoked — which it never is, because the callback was never registered in the first place. This is a classic Python indentation bug that creates a circular dependency: the callback registers itself inside the function that would only run if it were already registered.

As a result, the `handle_completion` function (which logs errors and results from the workspace pipeline background task) never executes. If the background pipeline fails — for example, if web scraping fails, LLM extraction fails, or the database connection drops — the error is silently swallowed. The `logger.error("Workspace pipeline task raised exception", ...)` on lines 169-177 never fires, making pipeline failures invisible in production monitoring and logs.

Additionally, the trace name on line 165 contains a typo: `"Worksapce Completion"` should be `"Workspace Completion"`. This would cause incorrect trace names in LangSmith monitoring.

The `create_task(run_pipeline())` on line 162 creates the asyncio task correctly, and the `run_pipeline` coroutine has its own try/except with error logging (lines 149-158). However, the `handle_completion` callback serves a different purpose — it catches exceptions that propagate out of the coroutine after the inner try/except, and it runs in a callback context that can clean up task references. Without the callback, the task's exception may go unretrieved, potentially triggering Python's "Task exception was never retrieved" warning.

---

## Current Code

```python
# File: src/services/workspace_service.py
# Lines: 162-179
        task = create_task(run_pipeline())

        def handle_completion(pipeline_task) -> None:
            with trace(name="Worksapce Completion"):     # <-- Typo: "Worksapce"
                try:
                    pipeline_task.result()
                except Exception as exc:
                    logger.error(
                        "Workspace pipeline task raised exception",
                        extra={
                            "operation_id": operation_id,
                            "workspace_id": str(workspace.id),
                            "error": str(exc),
                        },
                        exc_info=True,
                    )

            task.add_done_callback(handle_completion)    # <-- WRONG: Inside handle_completion body
```

The correct structure should be:

```
        task = create_task(run_pipeline())

        def handle_completion(pipeline_task) -> None:
            ...

        task.add_done_callback(handle_completion)  # <-- Outside handle_completion, at same indent level as `def`
```

---

## Why This Matters (Context & Reasoning)

The workspace creation pipeline is a critical background process that runs after each new workspace is created. It scrapes the user's website, extracts brand voice characteristics using an LLM, generates personas, and stores the results in the database. This pipeline involves multiple external API calls (web scraping, LLM inference) and database operations, any of which can fail.

Without the completion callback, pipeline failures are silent in the callback path. While the inner `run_pipeline()` coroutine has its own try/except logging, the callback was designed as a safety net to catch any exceptions that might slip through — including those raised by the `break` statement after the `async for bg_db in get_async_db()` loop, or exceptions in the task infrastructure itself.

Additionally, without calling `task.result()` in the callback, asyncio may log a warning: "Task exception was never retrieved" — a noisy message that appears in production logs without actionable context.

The typo `"Worksapce"` in the trace name would cause incorrect grouping in LangSmith monitoring, making it harder to filter and analyze workspace creation traces.

---

## Impact

- **Severity:** Background pipeline failures (LLM errors, web scraping failures, DB errors) are silently lost through the callback path. Production monitoring has a blind spot for workspace creation pipeline health.
- **Affected Users/Flows:** All workspace creation operations. Pipeline failures won't be caught by the callback error handler, reducing observability.
- **Blast Radius:** Workspace creation pipeline monitoring only. The pipeline itself still runs (the task is created correctly), but errors in the completion callback path are never logged.

---

## Recommended Solution

### Step 1: Fix the indentation and typo

```python
# File: src/services/workspace_service.py
# Replace lines 162-179 with:
        task = create_task(run_pipeline())

        def handle_completion(pipeline_task) -> None:
            with trace(name="Workspace Completion"):
                try:
                    pipeline_task.result()
                    logger.info(
                        "Workspace pipeline completed successfully",
                        extra={
                            "operation_id": operation_id,
                            "workspace_id": str(workspace.id),
                        },
                    )
                except Exception as exc:
                    logger.error(
                        "Workspace pipeline task raised exception",
                        extra={
                            "operation_id": operation_id,
                            "workspace_id": str(workspace.id),
                            "error": str(exc),
                        },
                        exc_info=True,
                    )

        task.add_done_callback(handle_completion)
```

### Step 2: (Optional) Consider adding task reference management

To prevent potential garbage collection of the background task, maintain a strong reference per Python asyncio best practices:

```python
# File: src/services/workspace_service.py
# Add at module level (after imports, before class definition):
import weakref

# Track background pipeline tasks to prevent garbage collection
_background_tasks: set = set()
```

Then in `create_workspace_for_user`, after creating the task:

```python
        task = create_task(run_pipeline())
        _background_tasks.add(task)

        def handle_completion(pipeline_task) -> None:
            _background_tasks.discard(pipeline_task)
            with trace(name="Workspace Completion"):
                try:
                    pipeline_task.result()
                    logger.info(
                        "Workspace pipeline completed successfully",
                        extra={
                            "operation_id": operation_id,
                            "workspace_id": str(workspace.id),
                        },
                    )
                except Exception as exc:
                    logger.error(
                        "Workspace pipeline task raised exception",
                        extra={
                            "operation_id": operation_id,
                            "workspace_id": str(workspace.id),
                            "error": str(exc),
                        },
                        exc_info=True,
                    )

        task.add_done_callback(handle_completion)
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/services/workspace_service.py` | `191-260` | `refresh_brand_voice_for_user()` — verify if it also uses a similar background task pattern with callbacks |
| `src/services/workspace_pipeline.py` | `1-608` | The pipeline code itself — no changes needed, but verify error propagation works correctly with the fixed callback |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Add a temporary `print("CALLBACK REGISTERED")` line right after `task.add_done_callback(handle_completion)` at the **current** (wrong) indentation level
2. Create a new workspace via the API
3. Observe that `"CALLBACK REGISTERED"` is never printed (because the line is inside `handle_completion` which is never called)
4. Introduce a deliberate failure in the pipeline (e.g., invalid URL) — observe that the callback error handler never logs

### After Fix (Verify the Solution):
1. Create a new workspace with a valid URL
2. Wait for the pipeline to complete
3. Check logs for `"Workspace pipeline completed successfully"` message — should appear
4. Create a workspace with an invalid/unreachable URL to trigger a pipeline error
5. Check logs for `"Workspace pipeline task raised exception"` message — should appear with error details
6. Check LangSmith traces for `"Workspace Completion"` trace name (correctly spelled)

### Run Existing Tests:
```bash
cd rext-backend
pytest tests/ -v -k "workspace and create"
```

---

## Acceptance Criteria

- [ ] `task.add_done_callback(handle_completion)` is at the correct indentation level (same as `def handle_completion`)
- [ ] Typo `"Worksapce"` is corrected to `"Workspace"` in the trace name
- [ ] Pipeline completion is logged on success
- [ ] Pipeline errors are logged on failure via the callback
- [ ] Background task reference is maintained to prevent garbage collection
- [ ] No "Task exception was never retrieved" warnings in asyncio
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Python asyncio — Task.add_done_callback()](https://docs.python.org/3/library/asyncio-task.html#asyncio.Task.add_done_callback)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [Python asyncio — Creating Tasks (fire-and-forget pattern)](https://docs.python.org/3/library/asyncio-task.html#creating-tasks)
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** None
