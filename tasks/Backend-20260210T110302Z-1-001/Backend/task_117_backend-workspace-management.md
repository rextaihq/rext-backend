# Task 117: Remove Unused Import `error` from `response_utils` in Workspace Core Route

## Metadata
- **Task ID:** TASK-117
- **Source:** B4 - Workspace Management (Finding #29 under P3 Low)
- **Audit Report:** `audit-reports/backend-workspace-management.md`
- **Priority:** P3 Low
- **Category:** code-quality
- **Effort Estimate:** small (< 1 hour)

---

## Description

In `rext-backend/src/api/routes/workspaces/workspace_core.py` at line 6, the statement `from src.utils.response_utils import success, error` imports both `success` and `error` from the response utilities module. However, only `success` is used in the file — the `error` function is never called anywhere in `workspace_core.py`.

A grep for `\berror\b` in the file shows only two matches: the import line itself (line 6) and `logger.error(...)` on line 327, which is a completely different `error` — it's the `error` method on the `logger` object, not the imported `error` function from `response_utils`.

The `workspace_core.py` file uses the `@db_transaction_handler` decorator on all its route handlers, which handles error responses automatically. When an exception occurs, the decorator catches it, rolls back the transaction, and generates a standardized error response using the `error()` function internally. This means route handlers never need to call `error()` directly — the decorator handles it.

The `error` function from `response_utils` creates a `JSONResponse` with a structured error body including error codes, severity, and request tracking. It is used in other parts of the codebase where the `@db_transaction_handler` is not applied, but in `workspace_core.py` where every handler uses the decorator, it is entirely unnecessary.

---

## Current Code

```python
# File: rext-backend/src/api/routes/workspaces/workspace_core.py
# Lines: 1-16
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from src.utils.logger import logger
from src.utils.response_utils import success, error
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.auth_utils import verify_current_user
from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
)
from src.services.workspace_service import WorkspaceService

router = APIRouter()
```

---

## Why This Matters (Context & Reasoning)

The `workspace_core.py` file is the modern RESTful workspace route module that provides path-parameter-based endpoints (`GET /{workspace_id}`, `PUT /{workspace_id}`, `DELETE /{workspace_id}`, etc.). All route handlers in this file use the `@db_transaction_handler` decorator, which automatically handles error responses when exceptions occur.

The `error` import was likely present from an earlier version of the code before the `@db_transaction_handler` decorator was introduced. When the decorator was adopted, the manual error response construction was removed from the route handlers, but the import was left behind.

The `success` function is also partially redundant in this file because `@db_transaction_handler` auto-wraps raw dict returns into success responses. However, `success` is explicitly called in at least one place (the health check route on line 25), so it is a legitimate import. Only the `error` function is completely unused.

Removing the unused `error` import:
- Eliminates F401 linting warnings
- Reduces confusion about the module's dependencies
- Makes it clear that error handling is fully delegated to the decorator

---

## Impact

- **Severity:** No functional impact. Code quality issue only.
- **Affected Users/Flows:** None. No user-facing behavior changes.
- **Blast Radius:** Isolated to a single import in one file.

---

## Recommended Solution

### Step 1: Remove `error` from the import statement

```python
# File: rext-backend/src/api/routes/workspaces/workspace_core.py
# Replace line 6:
# Before:
from src.utils.response_utils import success, error
# After:
from src.utils.response_utils import success
```

---

## Other Affected Locations

No other files in the workspace routes directory import `error` from `response_utils` without using it. A codebase-wide search for `import error` in the routes directory returned no additional results.

| File | Line(s) | Description |
|------|---------|-------------|
| None identified | — | No other workspace route files have this same unused import pattern for `error`. |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Open `rext-backend/src/api/routes/workspaces/workspace_core.py`.
2. Confirm line 6 contains `from src.utils.response_utils import success, error`.
3. Search the file for any call to `error(` (not `logger.error`) — confirm none exists.

### After Fix (Verify the Solution):
1. Confirm line 6 now reads `from src.utils.response_utils import success`.
2. Start the FastAPI application and verify workspace core endpoints still load:
   - `GET /workspaces/` (health check)
   - `GET /workspaces/all` (list workspaces)
   - `GET /workspaces/detail?workspace_id=...`
   - `PUT /workspaces/{workspace_id}`
   - `DELETE /workspaces/{workspace_id}`
3. Trigger an error scenario (e.g., request a non-existent workspace ID) and verify the error response is still properly formatted by the `@db_transaction_handler` decorator.

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "workspace" -v
```

---

## Acceptance Criteria

- [ ] Line 6 of `rext-backend/src/api/routes/workspaces/workspace_core.py` reads `from src.utils.response_utils import success`
- [ ] The `error` function is no longer imported in the file
- [ ] All workspace core endpoints still function correctly (including error responses via the decorator)
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** N/A — this is a dead import removal
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [PEP 8 — Imports](https://peps.python.org/pep-0008/#imports) — unused imports should be removed
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-115 (B4: Unused Import `Auth` from `langgraph_sdk`), TASK-116 (B4: Unused Import `os`) — same cleanup pattern in other workspace route files within this audit report.
