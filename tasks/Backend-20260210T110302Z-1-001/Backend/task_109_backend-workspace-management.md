# Task 109: Move Late Import of RextAuthorizationException to Top-Level Imports

## Metadata
- **Task ID:** TASK-109
- **Source:** B4 - Workspace Management (Finding #15 under P2 Medium)
- **Audit Report:** `audit-reports/backend-workspace-management.md`
- **Priority:** P2 Medium
- **Category:** code-quality
- **Effort Estimate:** small (< 1 hour)

---

## Description

In `src/services/workspace_service.py`, the `RextAuthorizationException` class is imported inside the body of the `verify_user_is_workspace_owner()` method at line 702, rather than at the top of the file with the other imports. This is inconsistent because `RextAuthenticationException`, which comes from the exact same module (`src.api.middleware.exceptions`), is already imported at the top of the file on line 46. The import block at lines 42-47 already imports four other exceptions from that module: `ResourceNotFoundException`, `RextValidationException`, `DuplicateResourceException`, and `RextAuthenticationException`.

Late imports (also called deferred imports or inline imports) are contrary to PEP 8 which states: "Imports are always put at the top of the file, just after any module comments and docstrings, and before module globals and constants." The accepted exceptions are circular import resolution, platform-conditional imports, and optional dependencies — none of which apply here. The `RextAuthorizationException` class is a core part of the application's exception hierarchy and is always available.

This late import hides the dependency, making it harder for developers to understand what the module depends on at a glance. It also delays the discovery of `ImportError` issues from startup to runtime — if the exception class were ever renamed or moved, the error would only surface when `verify_user_is_workspace_owner()` is called with a non-owner user, rather than at application startup.

There is a second late import at line 879 (`from datetime import datetime`), but `datetime` is already imported at line 21, so that import is entirely redundant and should also be removed.

---

## Current Code

```python
# File: rext-backend/src/services/workspace_service.py
# Lines: 42-47 (top-level imports)
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    RextValidationException,
    DuplicateResourceException,
    RextAuthenticationException,
)
```

```python
# File: rext-backend/src/services/workspace_service.py
# Lines: 700-708 (late import inside method body)
        if not user_role:
            from src.api.middleware.exceptions import RextAuthorizationException

            raise RextAuthorizationException(
                message="Only workspace owners can perform this action"
            )

        return True
```

```python
# File: rext-backend/src/services/workspace_service.py
# Line: 879 (redundant late import)
        from datetime import datetime
```

---

## Why This Matters (Context & Reasoning)

The `verify_user_is_workspace_owner()` method is a critical authorization gate that ensures only workspace owners can perform destructive or administrative actions on their workspace (e.g., deleting the workspace, transferring ownership). The method is called from `delete_workspace()` on line 882. Hiding its dependency on `RextAuthorizationException` behind a late import makes the code harder to reason about and inconsistent with the rest of the exception imports that are all at the top of the file.

Maintaining consistent import patterns is important in a large codebase because developers use the import section as a quick reference for understanding a module's dependencies. When one exception is imported at the top and another from the same module is imported inline, it signals uncertainty or accidental oversight.

---

## Impact

- **Severity:** If not fixed, the code will continue to work but remains inconsistent and violates PEP 8. The late import hides a dependency and delays import error discovery to runtime.
- **Affected Users/Flows:** No user-facing impact — this is a developer experience and code quality issue.
- **Blast Radius:** Isolated to `src/services/workspace_service.py`.

---

## Recommended Solution

### Step 1: Add `RextAuthorizationException` to the top-level import block

```python
# File: rext-backend/src/services/workspace_service.py
# Replace lines 42-47 with:
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    RextValidationException,
    DuplicateResourceException,
    RextAuthenticationException,
    RextAuthorizationException,
)
```

### Step 2: Remove the late import at line 702

```python
# File: rext-backend/src/services/workspace_service.py
# Replace lines 701-706 with (remove the import line):
        if not user_role:
            raise RextAuthorizationException(
                message="Only workspace owners can perform this action"
            )
```

### Step 3: Remove the redundant late import of datetime at line 879

```python
# File: rext-backend/src/services/workspace_service.py
# Delete line 879:
#         from datetime import datetime    <-- remove this line
```

The `datetime` module is already imported at line 21: `from datetime import datetime, timezone`. The late re-import on line 879 is redundant.

---

## Other Affected Locations

Late imports from `src.api.middleware.exceptions` exist in other service files across the codebase. While those are separate audit findings, they represent the same anti-pattern.

| File | Line(s) | Description |
|------|---------|-------------|
| `src/services/user_service.py` | `392, 467` | Late import of `RextValidationException` inside method bodies |
| `src/services/workspace_pipeline.py` | `469-470` | Late import of `sqlalchemy.delete` and `Persona` model inside `_persist_personas()` |
| `src/services/notification_helper.py` | `131` | Late import of `Notification` model |
| `src/services/knowledge_service.py` | `660-663` | Late imports of multiple models inside method body |

---

## Testing Instructions

### Before Fix (Confirm the Issue):
1. Open `rext-backend/src/services/workspace_service.py`
2. Verify that `RextAuthorizationException` is NOT in the top-level imports (lines 42-47)
3. Verify the late import exists at line 702 inside `verify_user_is_workspace_owner()`

### After Fix (Verify the Solution):
1. Verify `RextAuthorizationException` is in the top-level import block alongside the other four exceptions
2. Verify the late import at line 702 has been removed
3. Verify the redundant `from datetime import datetime` at line 879 has been removed
4. Start the application and verify no `ImportError` occurs

### Run Existing Tests:
```bash
cd rext-backend
python -m pytest tests/ -x -q
```

---

## Acceptance Criteria

- [ ] `RextAuthorizationException` is imported at the top of `workspace_service.py` alongside other exceptions from `src.api.middleware.exceptions`
- [ ] The late import on line 702 is removed
- [ ] The redundant `from datetime import datetime` on line 879 is removed
- [ ] `verify_user_is_workspace_owner()` still correctly raises `RextAuthorizationException` for non-owners
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [PEP 8 — Imports](https://peps.python.org/pep-0008/#imports) — "Imports are always put at the top of the file"
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [PEP 690 — Lazy Imports](https://peps.python.org/pep-0690/) — the proper mechanism for deferred imports when needed, rather than inline imports
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-087 (Unused `import os` in Multiple Files — B3), TASK-026 (Unused Import `os` in Auth Routes — B1)
