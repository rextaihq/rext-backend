# Task 115: Remove Unused Import `Auth` from `langgraph_sdk` in Workspace Permissions

## Metadata
- **Task ID:** TASK-115
- **Source:** B4 - Workspace Management (Finding #27 under P3 Low)
- **Audit Report:** `audit-reports/backend-workspace-management.md`
- **Priority:** P3 Low
- **Category:** code-quality
- **Effort Estimate:** small (< 1 hour)

---

## Description

In `rext-backend/src/api/routes/workspaces/workspace_permissions.py` at line 13, the statement `from langgraph_sdk import Auth` imports the `Auth` class from the `langgraph_sdk` package, but `Auth` is never referenced anywhere else in the file. A codebase-wide grep for `Auth` usage in this file confirms that the only occurrence is the import line itself.

The `Auth` class from `langgraph_sdk` is used in other parts of the codebase — specifically in `src/api/security/dependencies.py` (line 10), `src/api/security/auth.py` (line 1), and `src/api/routes/users/onboarding.py` (line 8) — where it serves as part of the LangGraph authentication integration. However, in `workspace_permissions.py`, the file handles workspace-scoped RBAC permission checks using the project's own `check_permission`, `get_user_permissions`, and `get_user_roles` utilities from `rbac_utils`, and does not interact with LangGraph's auth layer at all.

This dead import:
1. Adds an unnecessary dependency on `langgraph_sdk` at module load time for this route file.
2. Slightly increases memory footprint by importing a class that is never used.
3. Confuses developers who may assume `Auth` is used somewhere in the file's logic.
4. Triggers linting warnings from tools like `flake8` (F401), `ruff` (F401), or `pyright` unused import checks.

---

## Current Code

```python
# File: rext-backend/src/api/routes/workspaces/workspace_permissions.py
# Lines: 1-27
"""
Workspace Permission Routes

Provides endpoints for checking and retrieving user permissions within specific workspaces.
These endpoints are critical for frontend permission checks in a multi-tenant environment.
"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from langgraph_sdk import Auth

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.services.workspace_permission_service import WorkspacePermissionService
from src.utils.rbac_utils import (
    check_permission,
    get_user_permissions,
    get_user_roles
)
from src.utils.response_utils import success
from src.utils.workspace_utils import async_get_workspace_id_from_identifier
from src.utils.logger import logger
from src.utils.route_decorators import require_permissions
```

---

## Why This Matters (Context & Reasoning)

The workspace permissions route file handles RBAC permission checks for the multi-tenant workspace system. It uses the project's own `rbac_utils` module for permission verification, not LangGraph's `Auth` class. The `Auth` import was likely added during an earlier development phase when LangGraph authentication was being integrated across route files, but was never actually used in this particular file.

Removing unused imports is a standard code hygiene practice that:
- Keeps the dependency graph clean and honest
- Prevents confusion about what a module actually depends on
- Satisfies linting rules that many CI pipelines enforce
- Marginally reduces import time and memory usage

---

## Impact

- **Severity:** No functional impact. This is a code quality issue only. The import has zero runtime effect beyond a marginal increase in memory and import time.
- **Affected Users/Flows:** None. No user-facing behavior changes.
- **Blast Radius:** Isolated to a single import line in one file.

---

## Recommended Solution

### Step 1: Remove the unused `Auth` import

```python
# File: rext-backend/src/api/routes/workspaces/workspace_permissions.py
# Remove line 13 entirely:
# from langgraph_sdk import Auth
```

The imports section (lines 8-27) should become:

```python
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.services.workspace_permission_service import WorkspacePermissionService
from src.utils.rbac_utils import (
    check_permission,
    get_user_permissions,
    get_user_roles
)
from src.utils.response_utils import success
from src.utils.workspace_utils import async_get_workspace_id_from_identifier
from src.utils.logger import logger
from src.utils.route_decorators import require_permissions
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/api/security/dependencies.py` | `10` | Uses `Auth` from `langgraph_sdk` — this is a legitimate usage, do not remove. |
| `rext-backend/src/api/security/auth.py` | `1` | Uses `Auth` from `langgraph_sdk` — legitimate usage. |
| `rext-backend/src/api/routes/users/onboarding.py` | `8` | Imports `Auth` from `langgraph_sdk` — verify if actually used in that file (flagged in TASK-088 from B3 audit). |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Open `rext-backend/src/api/routes/workspaces/workspace_permissions.py`.
2. Confirm line 13 contains `from langgraph_sdk import Auth`.
3. Search the file for any usage of `Auth` beyond the import — confirm none exists.

### After Fix (Verify the Solution):
1. Confirm line 13 (`from langgraph_sdk import Auth`) has been removed.
2. Search the file for `Auth` — should return zero results.
3. Start the FastAPI application and verify the workspace permissions endpoints still load:
   - `GET /workspaces/{workspace_id}/permissions/me`
   - `GET /workspaces/{workspace_id}/permissions/check`
4. Run a permission check request to verify functionality is unaffected.

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "permission" -v
```

---

## Acceptance Criteria

- [ ] `from langgraph_sdk import Auth` is removed from `rext-backend/src/api/routes/workspaces/workspace_permissions.py`
- [ ] No references to `Auth` remain in the file
- [ ] Workspace permission endpoints still function correctly
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** N/A — this is a dead import removal
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [PEP 8 — Imports](https://peps.python.org/pep-0008/#imports) — "Wildcard imports should be avoided" and imports should be kept clean
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-088 (B3: `from langgraph_sdk import Auth` Unnecessary Import in `onboarding.py`) — same pattern in a different file. TASK-026 (B1: Unused Import `os` in Auth Routes) — similar unused import issue.
