# Task 114: Fix Typo "Worksapce" in LangSmith Trace Name

## Metadata
- **Task ID:** TASK-114
- **Source:** B4 - Workspace Management (Finding #26 under P2 Medium)
- **Audit Report:** `audit-reports/backend-workspace-management.md`
- **Priority:** P2 Medium
- **Category:** code-quality
- **Effort Estimate:** small (< 1 hour)

---

## Description

In `rext-backend/src/services/workspace_service.py` at line 165, the `trace()` context manager from the `langsmith` library is invoked with the name `"Worksapce Completion"` — a misspelling of "Workspace" (the letters "a" and "c" are transposed). This trace name is sent to LangSmith's monitoring platform, where it appears in the trace UI as a span name. Because LangSmith uses trace names for filtering, grouping, and searching traces, this typo means that:

1. Searching for "Workspace Completion" in the LangSmith dashboard will return zero results for this trace.
2. Any dashboards, alerts, or monitoring rules keyed on the correct spelling will miss these traces entirely.
3. Developers looking at trace hierarchies will see the misspelled name, causing confusion about what operation is being traced.

The `handle_completion` callback is registered on the background pipeline task and is called when the workspace creation pipeline finishes (successfully or with an error). The trace wraps the `pipeline_task.result()` call and the associated error logging. Note that there is also a separate critical bug (Finding #3 / TASK-093) where `task.add_done_callback(handle_completion)` is indented inside `handle_completion` itself, meaning the callback is never actually registered. Once TASK-093 is fixed and the callback starts firing, this misspelled trace name will appear in LangSmith.

The fix is a single-character transposition: change `"Worksapce Completion"` to `"Workspace Completion"`.

---

## Current Code

```python
# File: rext-backend/src/services/workspace_service.py
# Lines: 164-179
def handle_completion(pipeline_task) -> None:
    with trace(name="Worksapce Completion"):
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

        task.add_done_callback(handle_completion)
```

---

## Why This Matters (Context & Reasoning)

The `handle_completion` callback is part of the workspace creation flow. When a user creates a workspace, the backend spawns a background pipeline task (`workspace_pipeline.py`) that scrapes the provided URL, extracts brand voice data via LLM, and persists personas. The `handle_completion` callback is supposed to be called when this pipeline finishes, and the LangSmith trace captures the completion event for observability.

LangSmith is the project's observability platform for tracing LLM and pipeline operations. Trace names are used to:
- Filter and search for specific operations in the LangSmith UI
- Build dashboards that track operation success/failure rates
- Set up alerts on specific trace names
- Group related traces for performance analysis

A misspelled trace name breaks all of these capabilities for this specific operation. Once the callback registration bug (TASK-093) is fixed and traces start flowing, the typo will actively hinder production monitoring.

---

## Impact

- **Severity:** LangSmith traces for workspace pipeline completion will be filed under a misspelled name, making them unfindable via normal search and incompatible with any monitoring rules using the correct spelling.
- **Affected Users/Flows:** DevOps/engineering team monitoring workspace creation pipeline health in LangSmith.
- **Blast Radius:** Isolated to this single trace span. No user-facing impact. Only affects observability tooling.

---

## Recommended Solution

### Step 1: Fix the typo in `workspace_service.py`

```python
# File: rext-backend/src/services/workspace_service.py
# Replace line 165:
# Before:
#     with trace(name="Worksapce Completion"):
# After:
        with trace(name="Workspace Completion"):
```

Change `"Worksapce Completion"` to `"Workspace Completion"` on line 165 of `rext-backend/src/services/workspace_service.py`.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/services/workspace_service.py` | `179` | The `task.add_done_callback(handle_completion)` line is incorrectly indented inside `handle_completion` — see TASK-093. This typo fix should be coordinated with TASK-093 since both affect the same code block. |

No other occurrences of "Worksapce" were found in the codebase (confirmed via codebase-wide search).

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Open `rext-backend/src/services/workspace_service.py` and inspect line 165.
2. Confirm the trace name reads `"Worksapce Completion"` (misspelled).

### After Fix (Verify the Solution):
1. Open `rext-backend/src/services/workspace_service.py` and confirm line 165 now reads `with trace(name="Workspace Completion"):`.
2. Search the entire codebase for "Worksapce" (case-sensitive) — should return zero results.
3. If TASK-093 (callback indentation fix) is also applied, trigger a workspace creation and verify the trace appears in LangSmith under "Workspace Completion".

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "workspace" -v
```

---

## Acceptance Criteria

- [ ] Line 165 of `rext-backend/src/services/workspace_service.py` reads `with trace(name="Workspace Completion"):`
- [ ] No occurrences of "Worksapce" remain anywhere in the codebase
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [LangSmith Tracing Documentation](https://docs.smith.langchain.com/observability/how_to_guides/tracing)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** N/A — this is a simple typo fix
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-093 (Broken Callback Registration — same code block, lines 164-179). These two tasks modify the same function and should ideally be addressed together.
