# Task 087: Remove Unused `import os` from auth.py and management.py

## Metadata
- **Task ID:** TASK-087
- **Source:** B3 - User Management (Finding #29 under P3 Low)
- **Audit Report:** `audit-reports/backend-user-management.md`
- **Priority:** P3 Low
- **Category:** code-quality
- **Effort Estimate:** small (< 1 hour)

---

## Description

Two files in the user management routes have `import os` statements that are never used:

1. **`src/api/routes/users/auth.py` at line 22:** `import os` — the `os` module is not referenced anywhere in the file. Note that line 489 contains `user_agent.os.family`, but this is the `.os` attribute of the `user_agents` library's parsed user-agent object (from the `user-agents` package imported at line 20 as `from user_agents import parse as parse_user_agent`), not the Python `os` stdlib module.

2. **`src/api/routes/users/management.py` at line 5:** `import os` — a codebase search confirms that `os.` is never referenced anywhere in this file. The module was likely imported during initial development for environment variable access (`os.environ`, `os.getenv`) but the code was later refactored to use the `get_settings()` configuration pattern instead.

These unused imports add noise to the top of each file and can confuse developers into thinking the `os` module is needed. They may also trigger linter warnings (e.g., `F401 'os' imported but unused` from flake8 or ruff).

---

## Current Code

```python
# File: rext-backend/src/api/routes/users/auth.py
# Line: 22
import os
```

```python
# File: rext-backend/src/api/routes/users/management.py
# Lines: 1-6
from fastapi import APIRouter, Depends, Request, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
import uuid
import os
from datetime import datetime
```

---

## Why This Matters (Context & Reasoning)

Both `auth.py` and `management.py` are critical route files handling authentication and user management operations. Clean imports make these files easier to understand and maintain. The `auth.py` file is particularly large (1,046 lines), and every unnecessary line of boilerplate increases the cognitive overhead for developers working on it.

The project uses `src/api/config.py` with `get_settings()` for configuration management rather than direct `os.environ` or `os.getenv` calls, so the `os` module is genuinely unnecessary in these route files. Removing unused imports is a standard Python best practice recommended by PEP 8 and enforced by most linters.

---

## Impact

- **Severity:** No runtime impact. Code quality issue only.
- **Affected Users/Flows:** None directly. Affects developer experience and linter compliance.
- **Blast Radius:** Isolated to two import lines across two files.

---

## Recommended Solution

### Step 1: Remove `import os` from auth.py

```python
# File: rext-backend/src/api/routes/users/auth.py
# Delete line 22 entirely:
# import os  <-- remove this line
```

The surrounding lines (19-23) should go from:
```python
from src.services.notification_helper import schedule_if_allowed
from user_agents import parse as parse_user_agent
from src.api.models.user_models.notification_preferences import NotificationPreferences
import os
from src.api.middleware.rate_limiter import (
```

To:
```python
from src.services.notification_helper import schedule_if_allowed
from user_agents import parse as parse_user_agent
from src.api.models.user_models.notification_preferences import NotificationPreferences
from src.api.middleware.rate_limiter import (
```

### Step 2: Remove `import os` from management.py

```python
# File: rext-backend/src/api/routes/users/management.py
# Delete line 5 entirely:
# import os  <-- remove this line
```

The top of the file should go from:
```python
from fastapi import APIRouter, Depends, Request, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
import uuid
import os
from datetime import datetime
```

To:
```python
from fastapi import APIRouter, Depends, Request, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
import uuid
from datetime import datetime
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/api/routes/users/password.py` | `5` | Also has `import os` that appears unused (no `os.` references found in the file). Consider removing in the same cleanup pass. |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Verify unused imports exist:
   ```bash
   cd rext-backend && grep -n "^import os$" src/api/routes/users/auth.py src/api/routes/users/management.py
   ```
   Expected output: both files listed with their line numbers.
2. Verify `os.` is not used in management.py:
   ```bash
   cd rext-backend && grep "os\." src/api/routes/users/management.py
   ```
   Expected: no output.
3. Verify `os.` in auth.py is only `user_agent.os.family` (not stdlib `os`):
   ```bash
   cd rext-backend && grep "os\." src/api/routes/users/auth.py
   ```
   Expected: only `user_agent.os.family` matches.

### After Fix (Verify the Solution):
1. Confirm `import os` is removed from both files.
2. Verify both files still compile without errors:
   ```bash
   cd rext-backend && python -m py_compile src/api/routes/users/auth.py && python -m py_compile src/api/routes/users/management.py
   ```
3. Start the application and test that auth and user management endpoints work:
   ```bash
   # Test login
   curl -X POST -H "Content-Type: application/json" \
     -d '{"email": "test@example.com", "password": "testpass123"}' \
     http://localhost:8000/api/auth/login
   # Test user list (admin)
   curl -H "Authorization: Bearer <admin-token>" http://localhost:8000/api/users
   ```

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "auth or management" -v
```

---

## Acceptance Criteria

- [ ] `import os` removed from `src/api/routes/users/auth.py`
- [ ] `import os` removed from `src/api/routes/users/management.py`
- [ ] Both files compile without errors (`python -m py_compile`)
- [ ] No runtime errors on auth or user management endpoints
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [PEP 8 - Imports](https://peps.python.org/pep-0008/#imports) — Python style guide; unused imports should be removed
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [Flake8 F401](https://www.flake8rules.com/rules/F401.html) — documents the `F401` rule for detecting unused imports
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-026 (Unused Import `os` in Auth Routes — from B1 audit, same `auth.py` file, same finding); TASK-085 (Unused `LoginWithInvitation` import in same `auth.py` file — consider combining both import cleanups)
